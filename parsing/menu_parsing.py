import requests
import hashlib

from llm_client import OpenaiCaller


class CustomException(Exception):
    error_message = None
    error_code = None


class WebsiteUrlError(NotImplementedError, CustomException):
    error_message = "Oops! Website based menus not supported yet. Coming soon!"
    error_code = "WEBSITE_MENU"


class InvalidMenuContentsError(CustomException):
    error_message = "Oops, it seems the provided source is not a valid menu."
    error_code = "INVALID_MENU"


class MenuParsingInProgress(CustomException):
    error_message = (
        "The provided source is currently being parsed. Come back in a few minutes!"
    )
    error_code = "PARSING_IN_PROGRESS"


def validate_menu_contents(contents: str) -> bool:
    system_prompt = "Please tell me whether the following text corresponds to a restaurant or bar menu. Respond with a single { 'is_menu' : boolean } object."
    deployment_name = "recepcionista"
    output_schema = {
        "name": "boolean_response",
        "schema": {
            "type": "object",
            "properties": {"is_menu": {"type": "boolean"}},
            "required": ["is_menu"],
            "additionalProperties": False,
        },
    }

    llm_caller = OpenaiCaller(
        system_prompt=system_prompt,
        deployment_name=deployment_name,
        output_schema=output_schema,
    )
    n_retries = 3
    for _ in range(n_retries):
        try:
            raw_resp = llm_caller(contents)
            resp = json.loads(raw_resp)
            return resp.get("is_menu")
        except json.JSONDecodeError:
            print(
                f"JSON decoding failed for menu content validation. Retring (max={n_retries}"
            )
            pass

    return False


def _hash_local_pdf(filename: str) -> str:
    with open(filename, "rb") as file:
        pdf_bytes = file.read()
    content_hashed = hashlib.sha256(pdf_bytes).hexdigest()
    return content_hashed


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


from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
import json
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


import requests
from datetime import datetime


class MenuParser:
    def __init__(self, menu_source_identifier) -> None:
        self.is_pdf = _is_pdf(menu_source_identifier)
        self.menu_source_identifier = menu_source_identifier
        print(f"PARSING {self.menu_source_identifier}")

    def _get_contents_jina(self) -> str:
        print("Getting menu contents with jina...")
        jina_url = "https://r.jina.ai/" + self.menu_source_identifier
        response = requests.get(jina_url)
        response.raise_for_status()
        return response.text

    def _parse_pdf(self) -> dict:
        jina_contents = self._get_contents_jina()
        return {"menu_items": jina_contents}

    def _parse_website(self) -> dict:
        raise WebsiteUrlError("Website menu not supported yet")

    def _validate_contents(self, contents: dict) -> bool:
        contents_str = contents["menu_items"]
        if isinstance(type(contents_str), dict):
            contents_str = json.loads(contents_str, indent=2)

        is_valid_menu = validate_menu_contents(contents=contents_str)
        if is_valid_menu:
            print("Contents valid!")
        else:
            print("Contents NOT VALID")

        return is_valid_menu

    def parse(self) -> tuple[dict, bool]:
        if self.is_pdf:
            contents = self._parse_pdf()
        else:
            contents = self._parse_website()

        print("Contents parsed!")
        valid_contents = self._validate_contents(contents)

        return contents, valid_contents


CONTAINER_NAME = "dammian-mask-menus"


def _delete_menu_metadata(menu_source_identifier: str) -> None:
    menu_hash = hash_menu_contents(menu_source_identifier=menu_source_identifier)
    container = _get_container_client(container_name=CONTAINER_NAME)
    blob = container.get_blob_client(blob=menu_hash + ".json")
    blob.delete_blob()
    print(f"Deleted data for {menu_source_identifier}")


def _get_menu_contents_metadata(menu_source_identifier: str, overwrite: bool) -> dict:
    menu_hash = hash_menu_contents(menu_source_identifier=menu_source_identifier)
    menu_id = get_menu_id(menu_source_identifier=menu_source_identifier)

    container = _get_container_client(container_name=CONTAINER_NAME)
    blob = container.get_blob_client(blob=menu_id + ".json")

    menu_exists = blob.exists()

    if menu_exists:
        print(f"Menu contents for {menu_source_identifier} found!!")
        if not overwrite:
            print("Retrieving from DB")
            data = json.loads(blob.download_blob().readall().decode("utf-8"))
            return data
        print("Overwrite is set to True. Overwritting.")

    # WE DO THIS TO AVOID SIMULTANEOUS PARSING OF THE SAME DATA
    pre_parsing_menu_contents_metadata = {
        "menu_content": None,
        "timestamp": None,
        "menu_source_identifier": menu_source_identifier,
        "menu_hash": menu_hash,
        "is_valid_menu": None,
        "status": "PARSING",
        "menu_id": menu_id,
    }
    blob.upload_blob(
        data=json.dumps(pre_parsing_menu_contents_metadata, indent=4), overwrite=True
    )

    menu_parser = MenuParser(menu_source_identifier=menu_source_identifier)
    menu_contents, contents_are_valid = menu_parser.parse()
    menu_contents_metadata = {
        "menu_content": menu_contents,
        "timestamp": str(datetime.now()),
        "menu_source_identifier": menu_source_identifier,
        "menu_hash": menu_hash,
        "is_valid_menu": contents_are_valid,
        "status": "COMPLETED",
        "menu_id": menu_id,
    }
    blob.upload_blob(data=json.dumps(menu_contents_metadata, indent=4), overwrite=True)
    print(f"Uploaded contents for {menu_source_identifier}")
    return menu_contents_metadata


def _get_menu_contents(menu_source_identifier: str, overwrite: bool) -> dict:
    menu_contents_metadata = _get_menu_contents_metadata(
        menu_source_identifier=menu_source_identifier, overwrite=overwrite
    )
    if menu_contents_metadata["status"] == "PARSING":
        raise MenuParsingInProgress

    if not menu_contents_metadata["is_valid_menu"]:
        raise InvalidMenuContentsError

    return menu_contents_metadata["menu_content"]


def get_menu_contents_main(
    menu_source_identifier: str, overwrite: bool = False
) -> dict:
    if not _is_pdf(menu_source_identifier=menu_source_identifier):
        raise WebsiteUrlError("Website menu not supported yet")
    contents = _get_menu_contents(
        menu_source_identifier=menu_source_identifier, overwrite=overwrite
    )
    return contents


from dotenv import load_dotenv
from IPython import embed

if __name__ == "__main__":
    load_dotenv(".env")

    pdfurl = "https://www.restaurantestevet.com/wp-content/uploads/CartaESTEVEThivern24web.pdf"
    menu_url = "https://www.restaurantestevet.com/en/menu/"
    wurl = "https://dl.dropboxusercontent.com/scl/fi/l8lkbhnzk480zglfaemye/Carta_ramenyahiro.pdf?rlkey=cpqvk6vptk65l0377o37d81im&st=32ln77tt&"
    pandas_url = "https://pandas.pydata.org/Pandas_Cheat_Sheet.pdf"

    try:
        contents = get_menu_contents_main(pdfurl, overwrite=False)
    except CustomException as e:
        print(e.error_message)
    embed()
