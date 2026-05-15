from __future__ import annotations

from contextlib import AbstractAsyncContextManager
import os
from typing import Dict, Any, Union
import json
import requests

from datetime import datetime
from storage_utils import _get_container_client

import hashlib
import base64

from PIL import Image
from io import BytesIO
from pdf2image import convert_from_bytes


class OpenaiCaller:
    def __init__(
        self,
        deployment_name: str,
        system_prompt: str,
        output_schema: dict | None = None,
    ) -> None:
        self.deployment_name = deployment_name
        self.system_prompt = system_prompt
        self.output_schema = output_schema

        self.ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
        self.API_KEY = os.environ["AZURE_OPENAI_API_KEY"]
        self.API_VERSION = os.environ["AZURE_OPENAI_API_VERSION"]

    def __call__(self, messages: list) -> str:
        full_messages = [{"role": "system", "content": self.system_prompt}] + messages

        payload_args = {"messages": full_messages}
        if self.output_schema:
            payload_args["response_format"] = {
                "type": "json_schema",
                "json_schema": self.output_schema,
            }

        payload = {**payload_args}

        url = f"{self.ENDPOINT}/openai/deployments/{self.deployment_name}/chat/completions?api-version={self.API_VERSION}"
        r = requests.post(
            url,
            headers={"Content-Type": "application/json", "api-key": self.API_KEY},
            json=payload,
            timeout=60,
        )
        r.raise_for_status()
        response = r.json()
        response_message_raw = response["choices"][0]["message"]["content"]
        return response_message_raw


def image_to_data_url(image: Image.Image) -> str:
    buf = BytesIO()
    image.save(buf, format="PNG")
    image_bytes = buf.getvalue()
    mime_type = "image/png"
    base64_encoded_data = base64.b64encode(image_bytes).decode("utf-8")
    # Construct the data URL
    return f"data:{mime_type};base64,{base64_encoded_data}"


def convert_pdf_to_images(
    pdf_source_url: str, resize_factor: float = 1.0
) -> list[Image.Image]:
    print("Image resizing factor:", resize_factor)
    resp = requests.get(pdf_source_url)
    resp.raise_for_status()
    pdf_bytes = resp.content
    imgs = convert_from_bytes(pdf_bytes, fmt="PNG")
    print("PDF converted to images")

    if resize_factor == 1.0:
        return imgs

    resized = []
    for img in imgs:
        w, h = img.size
        resized_img = img.resize(
            (int(w * resize_factor), int(h * resize_factor)),
            Image.Resampling.LANCZOS,
        )
        resized.append(resized_img)

    return resized


class PromptUser:
    system_prompt: str
    prompt_hash: str
    prompt_storage_location: str
    subdir_name: str
    container_name: str = "dammian-mask-system-prompts"

    def save_prompt(self) -> None:
        system_prompt_hashed = hashlib.sha256(
            self.system_prompt.encode("utf-8")
        ).hexdigest()
        container = _get_container_client(container_name=self.container_name)
        blob_name = self.subdir_name + "/" + system_prompt_hashed + ".json"

        self.prompt_hash = system_prompt_hashed
        self.prompt_storage_location = blob_name

        blob = container.get_blob_client(blob=blob_name)
        if blob.exists():
            print(f"Prompt already exists for {self.subdir_name}.")
            return

        data = {
            "prompt": self.system_prompt,
            "prompt_hash": system_prompt_hashed,
            "timestamp": str(datetime.now()),
        }

        blob.upload_blob(data=json.dumps(data, indent=2), overwrite=True)


class UiOptionsGenerator(PromptUser):
    system_prompt = "You're part of a system designed to extract information from a restaurant menu in order to use it in a digital menu app. The chat interface will have 3 default message options that will help communicate to the user how to use the chat. Your specific task consists on, given the contents of a restaurant menu, come up with the default questions I just described, in multiple languages. Try to keep them short and concise, and, to the best possible extent, related and personalised to the contents of the menu. It's very important that the generated prompts can be safely answered with the information present in the menu."
    output_schema = {
        "name": "language_options_response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "languages": {
                    "type": "array",
                    "minItems": 10,
                    "maxItems": 10,
                    "items": {
                        "type": "object",
                        "properties": {
                            "language_code": {
                                "type": "string",
                                "enum": [
                                    "en",
                                    "es",
                                    "fr",
                                    "de",
                                    "it",
                                    "zh",
                                    "ja",
                                    "ru",
                                    "pt",
                                    "nl",
                                ],
                            },
                            "options": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 3,
                                "maxItems": 3,
                            },
                        },
                        "required": ["language_code", "options"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["languages"],
            "additionalProperties": False,
        },
    }
    subdir_name = "options-generator"

    def __init__(self) -> None:
        self.deployment = "recepcionista"
        self.llm_caller = OpenaiCaller(
            deployment_name=self.deployment,
            system_prompt=self.system_prompt,
            output_schema=self.output_schema,
        )
        self.n_retries = 4

    def generate(self, contents: str) -> tuple[str | None, dict]:
        self.save_prompt()
        print("Extracting UI options...")

        call_metadata = {
            "prompt_hash": self.prompt_hash,
            "prompt_storage_location": self.prompt_storage_location,
            "deployment": self.deployment,
        }
        for _ in range(self.n_retries):
            try:
                messages = [{"role": "user", "content": contents}]
                raw_resp = self.llm_caller(messages)
                r = json.loads(raw_resp)
                return r["languages"], call_metadata
            except json.JSONDecodeError:
                print(
                    f"JSON decoding failed for ui options generation. Retrying (max={self.n_retries}"
                )
                pass

        return None, call_metadata


class ContentValidator(PromptUser):
    system_prompt = "Please tell me whether the following text corresponds to a restaurant or bar menu. Respond with a single { 'is_menu' : boolean } object."
    subdir_name = "content-validator"

    def __init__(self) -> None:
        self.deployment = "recepcionista"
        self.output_schema = {
            "name": "boolean_response",
            "schema": {
                "type": "object",
                "properties": {"is_menu": {"type": "boolean"}},
                "required": ["is_menu"],
                "additionalProperties": False,
            },
        }

        self.llm_caller = OpenaiCaller(
            system_prompt=self.system_prompt,
            deployment_name=self.deployment,
            output_schema=self.output_schema,
        )
        self.n_retries = 3

    def validate_contents(self, contents: str) -> tuple[bool, dict]:
        self.save_prompt()
        print("Validating contents...")
        call_metadata = {
            "prompt_hash": self.prompt_hash,
            "prompt_storage_location": self.prompt_storage_location,
            "deployment": self.deployment,
        }
        for _ in range(self.n_retries):
            try:
                messages = [{"role": "user", "content": contents}]
                raw_resp = self.llm_caller(messages)
                resp = json.loads(raw_resp)
                return resp.get("is_menu"), call_metadata
            except json.JSONDecodeError:
                print(
                    f"JSON decoding failed for menu content validation. Retrying (max={self.n_retries}"
                )
                pass

        return False, call_metadata


class PdfMenuParser(PromptUser):
    system_prompt = "Eres un experto en parsear imagenes de menus de restaurante. A partir del siguiente menu, extrae toda la información que consideres relevante para el comensal del restaurante, en formato JSON. Responde solo con el JSON en cuestión, no añadas texto irrelevante a la tarea. Bajo ningún concepto te inventes información que no aparece claramente en el documento proporcionado. Debes asegurarte que cualquier información acerca de los contenidos del plato (eg gluten-free, vegan-friendly, etc.) queda bién representada en tu respuesta"
    deployment = "gpt-5.4"
    subdir_name = "pdf-parser"

    def __init__(self, pdf_source_url: str) -> None:
        self.pdf_source_url = pdf_source_url
        self.llm_caller = OpenaiCaller(
            deployment_name=self.deployment, system_prompt=self.system_prompt
        )

    def parse_menu_contents(self) -> tuple[str, dict]:
        self.save_prompt()

        content = []
        pdf_images = convert_pdf_to_images(
            pdf_source_url=self.pdf_source_url, resize_factor=0.8
        )
        for image in pdf_images:
            image_base64_encoded = image_to_data_url(image=image)
            content.append({"type": "image_url", "image_url": image_base64_encoded})

        messages = [
            {
                "role": "user",
                "content": content,
            },
        ]

        resp = self.llm_caller(messages)

        return resp, {
            "prompt_hash": self.prompt_hash,
            "prompt_storage_location": self.prompt_storage_location,
            "deployment": self.deployment,
        }
