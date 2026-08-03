from dotenv import load_dotenv
import os

def load_environment():
    app_env = os.getenv("APP_ENV")

    if app_env:
        env_path = f"env/.env.{app_env}"
    else:
        env_path = "env/.env"

    print(f"🔁 Loading env from {env_path}")
    load_dotenv(env_path)

# Load immediately when imported
load_environment()

class Settings:
    DB_HOST = os.getenv("DB_HOST")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_NAME = os.getenv("DB_NAME")
    DB_PORT_RW = os.getenv("DB_PORT_RW")
    DB_PORT_R = os.getenv("DB_PORT_R")

    SECRET_KEY = os.getenv("SECRET_KEY")
    FERNET_KEY = os.getenv("FERNET_KEY")

    TENANT_ID = os.getenv("TENANT_ID")
    CLIENT_ID = os.getenv("CLIENT_ID")

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

settings = Settings()