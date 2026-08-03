from cryptography.fernet import Fernet
from core.config import settings

if not settings.FERNET_KEY:
    raise ValueError("FERNET_KEY not set")

cipher = Fernet(settings.FERNET_KEY.encode())

def encrypt(value: str) -> str:
    return cipher.encrypt(value.encode()).decode()

def decrypt(value: str) -> str:
    return cipher.decrypt(value.encode()).decode()