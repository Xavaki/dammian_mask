from __future__ import annotations
from typing import final
from flask import (
    jsonify,
    make_response,
    request,
    Blueprint,
    Response,
    stream_with_context,
)
import os
import json
import json
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from .llm_utils import OpenaiCaller

from datetime import datetime

import requests
import hashlib

from .storage_utils import language_code_to_default_chat_options

from pathlib import Path


dirpath = Path(__file__).parent

# import logging
# logging.basicConfig(level=logging.INFO)
# logging.getLogger("azure.identity").setLevel(logging.DEBUG)

credential = DefaultAzureCredential()
storage_account_url = os.getenv("STORAGE_ACCOUNT_RESOURCE_URL")
storage_account = BlobServiceClient(
    account_url=storage_account_url, credential=credential
)


# UTILS
#
def _get_container_client(container_name: str):
    service = storage_account
    container = service.get_container_client(container_name)
    if not container.exists():
        print(f"Container {container_name} does not exist. Creating it.")
        container.create_container()
    return container


def hash_pdf(pdf_url: str) -> str:
    response = requests.get(pdf_url)
    response.raise_for_status()
    pdf_bytes = response.content
    content_hashed = hashlib.sha256(pdf_bytes).hexdigest()
    return content_hashed


def hash_website(website_url: str) -> str:
    response = requests.get(website_url)
    response.raise_for_status()
    html = response.text.encode("utf-8")
    html_hashed = hashlib.sha256(html).hexdigest()
    return html_hashed


def _is_pdf(menu_source_identifier: str) -> bool:
    return menu_source_identifier.endswith(".pdf")


def hash_menu(menu_source_identifier: str) -> str:
    if _is_pdf(menu_source_identifier=menu_source_identifier):
        return hash_pdf(pdf_url=menu_source_identifier)

    return hash_website(website_url=menu_source_identifier)


def hash_menu_contents(menu_source_identifier: str) -> str:
    return hash_menu(menu_source_identifier=menu_source_identifier)


def get_menu_id(menu_source_identifier: str) -> str:
    return menu_source_identifier.replace("/", "***")


bp = Blueprint("v1", __name__, url_prefix="/api")

# @bp.route("/hello_world", methods=["GET"])
# def hello_world():
#     container = storage_account.get_container_client("api-misc")
#     return jsonify({"message": "Hello, World!"})
#
#
#
#


class SystemPromptManager:
    CONTAINER_NAME = "dammian-mask-system-prompts"
    subdir_name = "menu-speak"
    prompt_hash: str
    system_prompt: str
    prompt_location: str

    def __init__(self, prompt_hash: str | None = None) -> None:
        self.container = _get_container_client(container_name=self.CONTAINER_NAME)

        if not prompt_hash:
            self._load_default_current_system_prompt()
        else:
            self.prompt_hash = prompt_hash

        self.prompt_location = self.subdir_name + "/" + self.prompt_hash + ".json"
        blob = self.container.get_blob_client(blob=self.prompt_location)
        if not blob.exists():
            self._load_default_current_system_prompt()
            self.save_prompt()
        else:
            data = blob.download_blob().readall().decode("utf-8")
            data = json.loads(data)
            self.system_prompt = data.get("prompt")

    def _load_default_current_system_prompt(self) -> None:
        with open(dirpath / "system_prompt_current.txt", "r") as file:
            sp = file.read()
        self.system_prompt = sp
        self.prompt_hash = self._hash_string(to_hash=self.system_prompt)

    def _hash_string(self, to_hash: str) -> str:
        hashed = hashlib.sha256(to_hash.encode("utf-8")).hexdigest()
        return hashed

    def save_prompt(self) -> None:
        data = self.get_prompt_data()
        data["creation_timestamp"] = str(datetime.now())
        blob = self.container.get_blob_client(blob=self.prompt_location)
        blob.upload_blob(data=json.dumps(data, indent=2), overwrite=True)

    def get_prompt_data(self) -> dict:
        data = {
            "prompt": self.system_prompt,
            "prompt_hash": self.prompt_hash,
        }
        return data


# TODO THINK PROPERLY
class SessionConversationManager:
    CONTAINER_NAME = "dammian-mask-sessions"
    container = _get_container_client(container_name=CONTAINER_NAME)

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._load_session()

    def _load_session(self) -> None:
        blob = self.get_blob_client(self.session_id)
        assert blob.exists()
        data = json.loads(blob.download_blob().readall().decode("utf-8"))

        self.creation_timestamp = data.get("creation_timestamp")
        self.prompt_data = data.get("prompt_data")
        self.messages = data.get("messages")
        self.menu_hash = data.get("menu_hash")

    @classmethod
    def get_blob_client(cls, session_id):
        blob_name = session_id + ".json"
        blob = cls.container.get_blob_client(blob=blob_name)
        return blob

    @classmethod
    def create_new(cls, session_id: str, menu_hash: str) -> SessionConversationManager:
        messages = []
        prompt_manager = SystemPromptManager()
        creation_timestamp = str(datetime.now())
        data = {
            "session_id": session_id,
            "creation_timestamp": creation_timestamp,
            "prompt_data": prompt_manager.get_prompt_data(),
            "messages": messages,
            "menu_hash": menu_hash,
        }
        blob_name = session_id + ".json"
        blob = cls.container.get_blob_client(blob=blob_name)
        blob.upload_blob(data=json.dumps(data, indent=2), overwrite=True)
        print(f"New session with session id {session_id} created!")
        return cls(session_id)

    def append_message(self, message: dict) -> None:
        message_timestamp = str(datetime.now())
        message["message_timestamp"] = message_timestamp
        self.messages.append(message)

    def _get_data(self) -> dict:
        return {
            "creation_timestamp": self.creation_timestamp,
            "prompt_data": self.prompt_data,
            "messages": self.messages,
            "menu_hash": self.menu_hash,
        }

    def save(self):
        data = self._get_data()
        blob = self.get_blob_client(self.session_id)
        blob.upload_blob(json.dumps(data, indent=2), overwrite=True)
        print(f"Session {self.session_id} saved!")

    def get_session_system_prompt(self) -> str:
        return self.prompt_data.get("prompt")

    def get_messages(self, llm_format: str, n_history_messages: int) -> list[dict]:
        messages = self.messages[-n_history_messages * 2 :]
        if llm_format == "azure":
            return [{"role": m["role"], "content": m["content"]} for m in messages]
        else:
            raise NotImplementedError


@bp.route("/get-menu-contents-status", methods=["GET"])
def get_menu_contents_status():
    session_id = request.args.get("session_id")

    if not session_id:
        return make_response(
            jsonify({"error": "Missing 'session_id' query parameter"}),
            400,
        )

    menu_hash = request.args.get("menu_hash")

    if not menu_hash:
        print("Generating menu hash...")
        menu_source = request.args.get("menu_source")
        if not menu_source:
            return make_response(
                jsonify(
                    {"error": "Missing 'menu_source' or 'menu_hash' query parameter"}
                ),
                400,
            )

        menu_hash = hash_menu_contents(menu_source_identifier=menu_source)

    headers = request.headers
    browser_language = request.accept_languages.best
    browser_language_code = browser_language.split("-")[0] if browser_language else "es"

    CONTAINER_NAME = "dammian-mask-menus"
    container = _get_container_client(container_name=CONTAINER_NAME)
    blob_name = menu_hash + "/contents.json"
    blob = container.get_blob_client(blob=blob_name)

    response_data = {"status": "UNKNOWN", "menu_hash": menu_hash, "ui": None}
    if not blob.exists():
        # TODO: launch parsing job
        status = "PARSING"
    else:
        menu_data = json.loads(blob.download_blob().readall().decode("utf-8"))
        is_valid_menu = menu_data.get("is_valid_menu")
        ui_options = menu_data.get("menu_data", {}).get("ui_options")
        language_ui_options = [
            x for x in ui_options if x.get("language_code") == browser_language_code
        ]
        language_ui_options = (
            language_ui_options[0]
            if language_ui_options
            else {"language_code": browser_language_code}
        )
        language_ui_options["placeholders"] = language_code_to_default_chat_options[
            browser_language_code
        ]
        response_data["ui"] = language_ui_options
        if is_valid_menu:
            status = "COMPLETED"
            SessionConversationManager.create_new(
                session_id=session_id, menu_hash=menu_hash
            )
        else:
            status = "INVALID_MENU"

    response_data["status"] = status

    return jsonify(response_data)


@bp.route("/menu-speak")
def menu_speak():
    user_message = request.args.get("user_message")
    menu_hash = request.args.get("menu_hash")
    session_id = request.args.get("session_id")

    required_args = ["user_message", "menu_hash", "session_id"]

    for a in required_args:
        if not a:
            return make_response(jsonify({"error": "Missing parameters"}), 400)

    CONTAINER_NAME = "dammian-mask-menus"
    container = _get_container_client(container_name=CONTAINER_NAME)
    blob_name = menu_hash + "/contents.json"
    blob = container.get_blob_client(blob=blob_name)
    assert blob.exists()

    menu_contents = (
        json.loads(blob.download_blob().readall().decode("utf-8"))
        .get("menu_data", {})
        .get("menu_content")
    )
    session_manager = SessionConversationManager(session_id=session_id)
    system_prompt = session_manager.get_session_system_prompt()
    full_system_prompt = (
        system_prompt + f"\nAquí tienes el menú del restaurante:\n\n{menu_contents}"
    )

    oc = OpenaiCaller(deployment_name="recepcionista", system_prompt=full_system_prompt)
    messages = session_manager.get_messages(llm_format="azure", n_history_messages=5)
    messages += [{"role": "user", "content": user_message}]

    @stream_with_context
    def speak_wrapper():
        count = 0
        llm_response_agg = ""
        try:
            for response_chunk in oc.stream(messages=messages):
                payload = {"id": count, "message_chunk": response_chunk}
                yield json.dumps(payload) + "\n"
                llm_response_agg += response_chunk
                count += 1
            yield json.dumps({"id": "END", "message_chunk": None}) + "\n"
        except:
            yield json.dumps({"id": "BACKEND-ERROR", "message_chunk": None}) + "\n"

        session_manager.append_message({"role": "user", "content": user_message})
        session_manager.append_message(
            {"role": "assistant", "content": llm_response_agg}
        )
        session_manager.save()

    return Response(speak_wrapper(), mimetype="application/x-ndjson")
