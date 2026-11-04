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

    # AI search: restricted read-only DB user (optional, falls back to DB_USER)
    DB_SEARCH_USER = os.getenv("DB_SEARCH_USER")
    DB_SEARCH_PASSWORD = os.getenv("DB_SEARCH_PASSWORD")
    # AI search: time limit per query (0 = no limit) and maximum rows returned
    DB_SEARCH_TIMEOUT_SECONDS = int(os.getenv("DB_SEARCH_TIMEOUT_SECONDS") or 15)
    DB_SEARCH_MAX_ROWS = int(os.getenv("DB_SEARCH_MAX_ROWS") or 200)

    # Username + password login. Off unless the env file turns it on (local only);
    # every other environment signs in with Entra ID.
    PASSWORD_LOGIN_ENABLED = (os.getenv("PASSWORD_LOGIN_ENABLED") or "").strip().lower() in ("1", "true", "yes", "on")
    # Wrong passwords allowed in a row, and how long the username is then blocked
    LOGIN_MAX_FAILED_ATTEMPTS = int(os.getenv("LOGIN_MAX_FAILED_ATTEMPTS") or 5)
    LOGIN_LOCKOUT_MINUTES = int(os.getenv("LOGIN_LOCKOUT_MINUTES") or 15)

    SECRET_KEY = os.getenv("SECRET_KEY")
    FERNET_KEY = os.getenv("FERNET_KEY")

    TENANT_ID = os.getenv("TENANT_ID")
    CLIENT_ID = os.getenv("CLIENT_ID")

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

settings = Settings()