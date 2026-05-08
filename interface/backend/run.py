from dotenv import load_dotenv

load_dotenv()  # take environment variables from .env file
from app import create_app
import os

app = create_app()

debug = os.environ.get("ENV") == "development"

if __name__ == "__main__":
    app.run(debug=debug)
