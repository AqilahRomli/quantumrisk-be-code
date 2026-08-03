# ==============================
# Standard Library
# ==============================
from datetime import datetime, timedelta

# ==============================
# Third-Party Libraries
# ==============================
import jwt

from fastapi import (
    HTTPException,
)

# ==============================
# Internal Modules
# ==============================
from core.config import settings

# ==============================
# Security & Config Setup
# ==============================
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 300

# ==========================================================================


def decode_access_token(token: str):
    try:
        # Decode the token using the secret key and algorithm
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload

    except jwt.ExpiredSignatureError:
        # Token is well-formed but has expired
        raise HTTPException(
            status_code=401,
            detail="Token has expired"
        )
    
    except jwt.PyJWTError:
        # Token is invalid (tampered, wrong key, backend restart, etc.)
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )
 

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    # print(f"Token expiration time: {expire}")

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
