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


def get_menu_id(menu_source_identifier: str) -> str:
    return menu_source_identifier.replace("/", "***")


bp = Blueprint("v1", __name__, url_prefix="/api")

# @bp.route("/hello_world", methods=["GET"])
# def hello_world():
#     container = storage_account.get_container_client("api-misc")
#     return jsonify({"message": "Hello, World!"})


@bp.route("/get-menu-contents", methods=["GET"])
def get_menu_contents():
    menu_source = request.args.get("menu_source")
    if not menu_source:
        return make_response(
            jsonify({"error": "Missing 'menu_source' query parameter"}), 400
        )

    menu_id = get_menu_id(menu_source_identifier=menu_source)

    CONTAINER_NAME = "dammian-mask-menus"
    container = _get_container_client(container_name=CONTAINER_NAME)
    blob = container.get_blob_client(blob=menu_id + ".json")

    if not blob.exists():
        # TODO: launch parsing job
        response_data = {"status": "PARSING"}
    else:
        blob_data = json.loads(blob.download_blob().readall().decode("utf-8"))
        response_data = blob_data

    return jsonify(response_data)


@bp.route("/menu-speak")
def menu_speak():
    user_message = request.args.get("user_message")
    menu_source = request.args.get("menu_source")

    if (not user_message) or (not menu_source):
        print(user_message, menu_source)
        return make_response(jsonify({"error": "Missing parameters"}), 400)

    oc = OpenaiCaller(
        deployment_name="recepcionista",
        system_prompt="Eres un asistente virtual. Ayuda al usuario en todo lo que te pida",
    )

    @stream_with_context
    def speak_wrapper():
        count = 0
        for response_chunk in oc.stream(message=user_message):
            payload = {"index": count, "message": response_chunk}
            yield json.dumps(payload) + "\n"
            count += 1

    return Response(speak_wrapper(), mimetype="application/x-ndjson")
