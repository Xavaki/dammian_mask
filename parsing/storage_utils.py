from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
import os

credential = DefaultAzureCredential()


def _blob_service_client() -> BlobServiceClient:
    resource_url = os.getenv("STORAGE_ACCOUNT_RESOURCE_URL")
    assert resource_url is not None, (
        "Storage account must be specified by setting STORAGE_ACCOUNT_RESOURCE_URL environment variable."
    )
    return BlobServiceClient(account_url=resource_url, credential=credential)


def _get_container_client(container_name: str):
    service = _blob_service_client()
    container = service.get_container_client(container_name)
    if not container.exists():
        print(f"Container {container_name} does not exist. Creating it.")
        container.create_container()
    return container
