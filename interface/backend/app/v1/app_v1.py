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
from .llm_client import OpenaiCaller

from datetime import datetime

import requests
import hashlib

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
    container = storage_account.get_container_client(container=container_name)
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


@bp.route("/get-menu-contents-status", methods=["GET"])
def get_menu_contents_status():
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
    for k, v in headers.items():
        print(f"{k}:{v}")
    browser_language = request.accept_languages.best
    browser_language_code = browser_language.split("-")[0] if browser_language else "es"
    print(browser_language_code)

    CONTAINER_NAME = "dammian-mask-menus"
    container = _get_container_client(container_name=CONTAINER_NAME)
    blob_name = menu_hash + "/contents.json"
    blob = container.get_blob_client(blob=blob_name)

    if not blob.exists():
        # TODO: launch parsing job
        response_data = {"status": "PARSING", "menu_hash": menu_hash}
    else:
        blob_data = json.loads(blob.download_blob().readall().decode("utf-8"))
        is_valid_menu = blob_data.get("is_valid_menu")
        if is_valid_menu:
            response_data = {"status": "COMPLETED", "menu_hash": menu_hash}
        else:
            response_data = {"status": "INVALID_MENU", "menu_hash": menu_hash}

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
    blob_name = menu_hash + ".json"
    blob = container.get_blob_client(blob=blob_name)
    assert blob.exists()

    menu_contents = json.loads(blob.download_blob().readall().decode("utf-8")).get(
        "menu_content"
    )

    oc = OpenaiCaller(
        deployment_name="recepcionista",
        system_prompt="Eres un asistente virtual. Ayuda al usuario en todo lo que te pida",
    )

    @stream_with_context
    def speak_wrapper():
        count = 0
        try:
            for response_chunk in oc.stream(message=user_message):
                payload = {"id": count, "message_chunk": response_chunk}
                yield json.dumps(payload) + "\n"
                count += 1
            yield json.dumps({"id": "END", "message_chunk": None}) + "\n"
        except:
            yield json.dumps({"id": "BACKEND-ERROR", "message_chunk": None}) + "\n"

    return Response(speak_wrapper(), mimetype="application/x-ndjson")
