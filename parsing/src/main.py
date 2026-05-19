from azure.storage.queue._shared.policies import base64
from dotenv import load_dotenv
from menu_parsing import get_upload_menu_data, CustomException
import os

from azure.storage.queue import QueueClient
from azure.identity import DefaultAzureCredential

import json

load_dotenv("../.env")

credential = DefaultAzureCredential()


def _get_queue(queue_name: str) -> QueueClient:
    resource_url = os.getenv("QUEUE_URL")
    assert resource_url is not None, (
        "Storage account must be specified by setting STORAGE_ACCOUNT_RESOURCE_URL environment variable."
    )
    queue = QueueClient(
        account_url=resource_url, queue_name=queue_name, credential=credential
    )
    return queue


def decode_message_content(message_content) -> str:
    try:
        decoded = json.loads(message_content)
        return message_content
    except:
        return message_content


from storage_utils import _get_container_client

print(os.getenv("STORAGE_ACCOUNT_RESOURCE_URL"))
debug_container = _get_container_client("dammian-mask-debug-utils")


def _dummy_handle_message_content(message_content: str):
    blob_name = message_content + ".txt"
    blob = debug_container.get_blob_client(blob=blob_name)
    blob.upload_blob(message_content, overwrite=True)
    print(f"Wrote message content {message_content} to debug container.")


def _post_dummy_messages(n_messages: int) -> None:
    queue_name = os.getenv("QUEUE_NAME")
    assert queue_name
    queue = _get_queue(queue_name=queue_name)
    for i, _ in enumerate(range(n_messages)):
        dummy_message = input("Enter dummy message: ")
        queue.send_message(content=dummy_message)


def run_pipeline_watcher():
    queue_name = os.getenv("QUEUE_NAME")
    assert queue_name
    queue = _get_queue(queue_name=queue_name)
    for message in queue.receive_messages(messages_per_page=1):
        content = decode_message_content(message_content=message.content)
        print("raw content", content)
        _dummy_handle_message_content(message_content=content)
        queue.delete_message(message)
        continue
        try:
            payload = json.loads(content)
            menu_source_identifier = payload["menu_source_identifier"]
        except:
            print("Error decoding message payload")
            continue

        try:
            get_upload_menu_data(
                menu_source_identifier=menu_source_identifier, overwrite=False
            )
        except Exception as e:
            print(f"Error in parsing data: {e}")
        queue.delete_message(message)


if __name__ == "__main__":
    # run_pipeline_watcher()
    _post_dummy_messages(4)
