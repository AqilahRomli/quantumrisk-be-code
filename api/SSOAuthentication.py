# Purpose: handles OV-QR SSO authentication

import hashlib
import jwt
from fastapi import APIRouter, HTTPException
from psycopg2.extras import RealDictCursor
from core.db import get_db
from helper.tokenManagement import create_access_token

router = APIRouter()

# OV token configuration
OV_SECRET_KEY = "OV_SECRET_KEY_12345"
ALGORITHM = "HS256"

# OV to QR SSO Login
@router.post("/sso-login")
def sso_login(data: dict):

    # Receive OV token
    ov_token = data.get("token")

    if not ov_token:
        raise HTTPException(
            status_code=400,
            detail="OV token is missing"
        )

    # Validate OV token
    try:
        ov_user = jwt.decode(
            ov_token,
            OV_SECRET_KEY,
            algorithms=[ALGORITHM]
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="OV token has expired"
        )

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid OV token"
        )

    # Read identity from OV token
    employee_id = ov_user.get("employee_id")
    ov_name = ov_user.get("name")
    ov_email = ov_user.get("email")
    ov_department = ov_user.get("department")
    ov_role = ov_user.get("role")
    ov_system = ov_user.get("system")

    if not employee_id:
        raise HTTPException(
            status_code=401,
            detail="employee_id is missing from OV token"
        )

    if ov_system != "OV":
        raise HTTPException(
            status_code=401,
            detail="Invalid source system"
        )

    # Find existing QR user
    with get_db("r") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            cursor.execute(
                """
                SELECT
                    id,
                    username,
                    user_role,
                    access
                FROM risk_user_table
                WHERE username = %s
                """,
                (employee_id,)
            )

            qr_user = cursor.fetchone()

        finally:
            cursor.close()

    # Reject unprovisioned user
    if not qr_user:
        raise HTTPException(
            status_code=403,
            detail=(
                f"QR account not found for employee_id '{employee_id}'. "
                "Please ask QR Admin to create the account first."
            )
        )

    # Get role and access from QR DB
    qr_username = qr_user["username"]
    qr_role = qr_user["user_role"]
    qr_access = qr_user["access"]

    # Generate QR token
    qr_token = create_access_token(
        data={
            "sub": qr_username,
            "role": qr_role,
            "access": qr_access
        }
    )

    # Return QR authentication result
    return {
        "success": True,
        "message": "SSO login successful",
        "username": qr_username,
        "user_id": qr_user["id"],
        "role": qr_role,
        "access": qr_access,
        "access_token": qr_token,
        "token_type": "bearer"
    }
