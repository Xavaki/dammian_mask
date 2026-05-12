from __future__ import annotations

import os
from typing import Dict, Any, Union
import json
import requests

from storage_utils import _get_container_client

import hashlib


# class OpenaiClient:
#     model_type = "azure_openai"
#     default_inputs = {
#         "stream": False,
#         "temperature": 0.2,
#     }
#
#     def __init__(
#         self,
#         config: Dict,
#         deployment: str,
#         api_key: str,
#         api_version: str,
#         endpoint: str,
#         inputs: Union[str, Dict[str, Any]],
#     ):
#         self.config = config
#         self.deployment = deployment
#         self.API_KEY = api_key
#         self.API_VERSION = api_version
#         self.ENDPOINT = endpoint
#         self.client_name = self.model_type + "." + self.deployment
#         if inputs == "default":
#             self.inputs = self.default_inputs
#         else:
#             self.inputs = inputs
#
#     def call_model(
#         self,
#         user_message: str,
#         system_prompt: SystemPrompt,
#         conversation_history,
#         metadata: Dict,
#     ) -> [str, Dict[str, Any]]:
#         # format conversation history in azure format
#         formatted_conversation_history = [
#             {"role": msg["role"], "content": msg["content"]}
#             for msg in conversation_history
#         ]
#
#         full_system_prompt = system_prompt.full_system_prompt
#         schema = system_prompt.response_schema
#         messages = [
#             {"role": "system", "content": full_system_prompt},
#             *formatted_conversation_history,
#             {"role": "user", "content": user_message},
#         ]
#
#         payload = {
#             **self.inputs,
#             **{
#                 "messages": messages,
#                 "response_format": {"type": "json_schema", "json_schema": schema},
#             },
#         }
#         serializable_payload = {k: v for k, v in payload.items() if k != "messages"}
#         serializable_payload = json.dumps(serializable_payload, indent=2)
#
#         url = f"{self.ENDPOINT}/openai/deployments/{self.deployment}/chat/completions?api-version={self.API_VERSION}"
#         r = requests.post(
#             url,
#             headers={"Content-Type": "application/json", "api-key": self.API_KEY},
#             json=payload,
#             timeout=60,
#         )
#         r.raise_for_status()
#         response = r.json()
#
#         n_tokens = response.get("usage", {}).get("total_tokens", 0)
#
#         response_message_raw = response["choices"][0]["message"]["content"]
#
#         model_session_level_metadata = {
#             "model_type": self.model_type,
#             "url": url,
#             "deployment": self.deployment,
#             "output_schema": schema,
#             "client_name": self.client_name,
#         }
#
#         model_response_level_metadata = {
#             "outputs": response,
#             "nTokens": n_tokens,
#             "inputs": serializable_payload,
#             "chat_history_length": len(conversation_history),
#         }
#
#         metadata["session_level_metadata"]["model"] = model_session_level_metadata
#         metadata["response_level_metadata"]["model"] = model_response_level_metadata
#
#         return response_message_raw, metadata


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

    def __call__(self, message: str) -> str:
        messages = [
            {"role": "system", "content": self.system_prompt},
        ] + [message]

        payload_args = {"messages": messages, "stream": True}
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


class PdfMenuParser:
    system_prompt = """Eres un experto en parsear PDFs. A partir del siguiente menu, extrae toda la información que consideres relevante para el comensal del restaurante, en formato JSON.Responde solo con el JSON en cuestión, no añadas texto irrelevante a la tarea."""
    deployment = "gpt-5.4"

    def __init__(self, pdf_source_url: str) -> None:
        self.pdf_source_url = pdf_source_url
        self.llm_caller = OpenaiCaller(
            deployment_name=self.deployment, system_prompt=self.system_prompt
        )

    def save_prompt(self):
        system_prompt_hashed = hashlib.sha256(self.system_prompt).hexdigest()
        container = _get_container_client(container_name)

    def parse_menu_contents(self) -> str: ...
