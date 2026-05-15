from __future__ import annotations

import os
from typing import Dict, Any, Union
import json
import requests


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

        payload_args = {
            "messages": full_messages,
        }
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

    def stream(self, messages: list) -> str:
        full_messages = [
            {"role": "system", "content": self.system_prompt},
        ] + messages

        payload_args = {"messages": full_messages, "stream": True}
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
            # timeout=60,
            stream=True,
        )
        r.raise_for_status()

        for line in r.iter_lines():
            if line:
                decoded = line.decode("utf-8")

                if decoded.startswith("data: "):
                    data = decoded[6:]

                    if data == "[DONE]":
                        break

                    chunk = json.loads(data)

                    choices = chunk.get("choices", [])
                    if choices:
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content")

                        if content:
                            yield content


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    oc = OpenaiCaller(
        deployment_name="recepcionista",
        system_prompt="Eres un asistente virtual. Ayuda al usuario en todo lo que te pida",
    )
    for content_chunk in oc.stream(
        message="Hola! Cuentame un dato curioso en 200 palabras."
    ):
        print(content_chunk, end="", flush=True)
