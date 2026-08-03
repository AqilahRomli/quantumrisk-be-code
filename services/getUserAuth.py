# ==============================
# Standard Library
# ==============================
import json
import hashlib
from datetime import datetime, timedelta

# ==============================
# Third-Party Libraries
# ==============================
from psycopg2.extras import RealDictCursor

import pandas as pd

import jwt
from jwt import decode as jwt_decode
from jwt.algorithms import RSAAlgorithm

from passlib.context import CryptContext

from cryptography.fernet import InvalidToken

from fastapi import (
    HTTPException,
    Request,
)
from fastapi.responses import JSONResponse

# ==============================
# Internal Modules
# ==============================
from core.config import settings
from core.db import get_db
from core.security import encrypt, decrypt
from helper.tokenManagement import create_access_token

# ==============================
# Security & Config Setup
# ==============================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 300

tenant_id = settings.TENANT_ID
client_id = settings.CLIENT_ID

# ==============================
# JWKS Setup (Offline EntraID)
# ==============================
with open("config/jwks.json") as f:
    jwks_data = json.load(f)

keys = jwks_data.get("keys", [])

# ==========================================================================

# EntraID
def get_signing_key(token: str):
    """
    Find the matching signing key from local jwks.json
    """
    try:
        kid = jwt.get_unverified_header(token)["kid"]
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token header: {e}")

    for key in keys:
        if key["kid"] == kid:
            return RSAAlgorithm.from_jwk(json.dumps(key))

    raise HTTPException(status_code=401, detail="No matching JWK found for token")


#------------ User Registration ------------------
# Insert New User Details
def insert_newuser_details(
    cursor,
    requestor_email,
    requestor_id,
    requestor_ip,
    fullname,
    username,
    email,
    staff_id,
    division,
    user_role,
    user_access
):
    password = 'Quantumrisk123'

    user_data = {
        "username": username,
        "password": pwd_context.hash(password),
        "email": encrypt(email),
        "staff_id": encrypt(staff_id),
        "fullname": encrypt(fullname),
        "division": division,
        "user_role": user_role,
        "user_access": user_access,
        "email_hash": hashlib.sha256(email.encode()).hexdigest()
    }

    # ✅ Check duplicate
    cursor.execute("""
        SELECT 1 FROM risk_user_table 
        WHERE username = %s OR email_hash = %s
    """, (user_data["username"], user_data["email_hash"]))

    if cursor.fetchone():
        raise ValueError("DUPLICATE_USER")

    # ✅ Insert
    cursor.execute("""
        INSERT INTO risk_user_table 
        (username, password, user_role, email, staff_id, division, access, name, email_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        user_data["username"],
        user_data["password"],
        user_data["user_role"],
        user_data["email"],
        user_data["staff_id"],
        user_data["division"],
        user_data["user_access"],
        user_data["fullname"],
        user_data["email_hash"]
    ))

    # ✅ Logging
    if user_role not in ["Admin", "SC-Admin"]:
        message = f"Success Created new user: '{email}' with Admin privilege"
    else:
        message = f"Success Created new user: '{email}' with '{user_role}'"

    if requestor_email:
        post_event_log(
            cursor.connection,
            requestor_email,
            requestor_id,
            requestor_ip,
            message,
            "Success",
            "User_Creation"
        )

# Function to register a new user
def register_user(username_requestor: str, requestor_ip:str, fullname:str, username: str, email: str, staff_id: str, division: str, user_role: str, user_access: str):
    requestor_email = None
    requestor_id = None

    with get_db("rw") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            # Check requestor detail
            cursor.execute("""
                SELECT * FROM risk_user_table 
                WHERE username = %s
            """, (username_requestor,))
            requestor = cursor.fetchone()
            if not requestor:
                raise HTTPException(status_code=404, detail=f"Requestor '{username_requestor}' not found")

            requestor_email = decrypt(requestor["email"])
            requestor_id = requestor["id"]

            insert_newuser_details(cursor,
                requestor_email, requestor_id, requestor_ip,
                fullname, username, email,
                staff_id, division,
                user_role, user_access
            )

            conn.commit()

            return {"success": True, "message": "User registered successfully"}

        except ValueError as e:
            conn.rollback()
            if str(e) == "DUPLICATE_USER":
                raise HTTPException(status_code=400, detail="Username or Email already exists")
            raise

        except Exception as e:
            conn.rollback()
            if requestor_email:
                post_event_log(cursor.connection, requestor_email, requestor_id, requestor_ip, f"Failed to Create new user, '{email}'", "Failed", "User_Creation")
            raise HTTPException(status_code=500, detail=f"Failed to register user: {str(e)}")
        
        finally:
            cursor.close()

#Process Bulk Register User
def bulk_register_process(file, username_requestor: str, requestor_ip: str):
    with get_db("rw") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        success_count = 0
        duplicate_records = []
        failed_records = []

        try:
            # Validate requestor
            cursor.execute("""
                SELECT * FROM risk_user_table WHERE username = %s
            """, (username_requestor,))
            requestor = cursor.fetchone()

            if not requestor:
                raise HTTPException(status_code=404, detail="Requestor not found")

            requestor_email = decrypt(requestor["email"])
            requestor_id = requestor["id"]

            # ✅ Read Excel
            df = pd.read_excel(file.file)

            required_columns = [
                "fullname", "username", "email",
                "staff_id", "division", "user_role", "user_access"
            ]

            for col in required_columns:
                if col not in df.columns:
                    raise HTTPException(status_code=400, detail=f"Missing column: {col}")

            # ✅ Loop rows
            for index, row in df.iterrows():
                try:
                    insert_newuser_details(
                        cursor,
                        requestor_email,
                        requestor_id,
                        requestor_ip,
                        row["fullname"],
                        row["username"],
                        row["email"],
                        str(row["staff_id"]),
                        row["division"],
                        row["user_role"],
                        row["user_access"]
                    )
                    success_count += 1

                except Exception as e:
                    if str(e) == "DUPLICATE_USER":
                        duplicate_records.append({
                            "row": index + 1,
                            "email": row.get("email"),
                            "staff_id": row.get("staff_id"),
                            "reason": "Already exists"
                        })
                    else:
                        failed_records.append({
                            "row": index + 1,
                            "email": row.get("email"),
                            "error": str(e)
                        })

            conn.commit()

            return {
                "success": True,
                "inserted": success_count,
                "duplicates": len(duplicate_records),
                "failed": len(failed_records),
                "duplicate_details": duplicate_records,
                "failed_details": failed_records
            }

        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))

        finally:
            cursor.close()               
        

#---------------- Login ---------------------
# Function to authenticate a user during login
def login_user(username: str, password: str):
    with get_db("rw") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            # Check if the user exists
            cursor.execute("SELECT * FROM risk_user_table WHERE username = %s", (username,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=400, detail="Invalid username or password")
            
            # Verify the password
            if not pwd_context.verify(password, user["password"]):
                raise HTTPException(status_code=400, detail="Invalid username or password")
            
            # Set expiration time
            expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            expire_time = datetime.utcnow() + expires_delta

            user_id = user["id"]
            user_role = user["user_role"]

            # Generate JWT token
            access_token = create_access_token(data={"sub": user["username"], "role": user["user_role"], "access": user["access"]})
        
            # Return the response with the token
            return {
                "success": True,
                "username": username,
                "message": "Login successful",
                "user_id": user_id,
                "role": user_role,
                "access": user["access"],
                "access_token": access_token,
                "token_type": "bearer",
                "expires_at": expire_time.isoformat()  # Include expiration time
            }
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to login user: {str(e)}")
        finally:
            cursor.close()

# Function to authenticate a user during login
def login_EntraID(id_token: str, user_ip:str):
    try:
        signing_key = get_signing_key(id_token)
        # signing_key = jwk_client.get_signing_key_from_jwt(id_token).key

        claims = jwt_decode(
            id_token,
            signing_key,
            algorithms=["RS256"],
            audience= client_id,
            options={"verify_exp": True},
            # id_token,
            # signing_key,
            # algorithms=["RS256"],
            # audience=client_id,
            issuer=f"https://login.microsoftonline.com/{tenant_id}/v2.0",
            # options={"verify_exp": True}
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid ID token: {str(e)}")

    email = claims.get("email")
    email_hash = hashlib.sha256(email.encode()).hexdigest()

    with get_db("rw") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            # Check if the user exists
            cursor.execute("SELECT * FROM risk_user_table WHERE email_hash = %s", (email_hash,))
            user = cursor.fetchone()
            if not user:
                post_event_log(cursor.connection, email, None, user_ip, "Unprovisioned user login attempt", "Failed", "Login")
                raise HTTPException(status_code=400, detail="User not provisioned")
            
            # Set expiration time
            expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            expire_time = datetime.utcnow() + expires_delta

            # Generate JWT token
            access_token = create_access_token(data={"sub": user["username"], "role": user["user_role"], "access": user["access"]})
        
            # ✅ Upsert login info (insert if not exists, else update login_time)
            cursor.execute("""
                INSERT INTO user_login_track (username, email)
                VALUES (%s, %s)
                ON CONFLICT (username)
                DO UPDATE SET 
                    login_time = EXCLUDED.login_time
            """, (
                user["username"],
                email
            ))
            post_event_log(cursor.connection, email, user["id"], user_ip, f"User '{email}' logged in successfully", "Success", "Login")

            conn.commit()

            # Return the response with the token
            return {
                "success": True,
                "username": user["username"],
                "message": "Login successful",
                "user_id": user["id"],
                "role": user["user_role"],
                "access": user["access"],
                "access_token": access_token,
                "token_type": "bearer",
                "expires_at": expire_time.isoformat()  # Include expiration time
            }
        except Exception as e:
            conn.rollback()
            post_event_log(cursor.connection, email, None, user_ip, f"Failed login attempt for user '{email}'", "Failed", "Login")
            raise HTTPException(status_code=500, detail=f"Failed to login user: {str(e)}")
        finally:
            cursor.close()


#---------------- Individual User -----------------
#get user detail
def get_user_detail(user_id: str, username: str):
    try:
        with get_db("r") as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Step 1: Get user data
            cursor.execute("""
                SELECT id, username, user_role, email, staff_id
                FROM risk_user_table
                WHERE id = %s AND username = %s
            """, (user_id, username))
            user_data = cursor.fetchall()

            for row in user_data:
                try:
                    if row.get("email"):
                        row["email"] = decrypt(row["email"])
                    if row.get("staff_id"):
                        row["staff_id"] = decrypt(row["staff_id"])
                except InvalidToken:
                    # Skip if the value is not encrypted
                    pass

            cursor.close()

            return user_data

    except Exception as e:
        raise Exception(f"Database error during delete: {str(e)}")

#Change password
def change_password(user_id: str, password: str, newpassword: str, username: str):
    with get_db("rw") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            # 1. Check if user exists
            cursor.execute("SELECT * FROM risk_user_table WHERE username = %s AND id = %s", (username, user_id))
            user = cursor.fetchone()

            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # 2. Verify current password
            if not pwd_context.verify(password, user["password"]):
                raise HTTPException(status_code=400, detail="Invalid current password")

            # 3. Hash new password
            hashed_new_password = pwd_context.hash(newpassword)

            # 4. Update password in DB
            cursor.execute("UPDATE risk_user_table SET password = %s WHERE id = %s", (hashed_new_password, user_id))
            conn.commit()

            return True

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to change password: {str(e)}")

        finally:
            cursor.close()


#--------------- Admin Page --------------------
#get All Users
def get_all_user():
    try:
        with get_db("r") as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Step 1: Get user data
            cursor.execute("""
                SELECT id, username, user_role, name, email, staff_id, division
                FROM risk_user_table
            """)
            user_data = cursor.fetchall()

            for row in user_data:
                try:
                    if row.get("name"):
                        row["name"] = decrypt(row["name"])
                    if row.get("email"):
                        row["email"] = decrypt(row["email"])
                    if row.get("staff_id"):
                        row["staff_id"] = decrypt(row["staff_id"])
                except InvalidToken:
                    # Skip if the value is not encrypted
                    pass

            cursor.close()

            return user_data

    except Exception as e:
        raise Exception(f"Database error during delete: {str(e)}")

# Function to update user role
def update_user_role(requestor_ip: str, username_requestor:str, username: str, id:str, new_role:str):
    with get_db("rw") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            #Get Requestor Details
            cursor.execute("""
                SELECT * FROM risk_user_table 
                WHERE username = %s
            """, (username_requestor,))
            requestor = cursor.fetchone()
            if not requestor:
                raise HTTPException(status_code=404, detail=f"Requestor '{username_requestor}' not found")
            
            print(requestor["email"])

            requestor_email = decrypt(requestor["email"])
            requestor_id = requestor["id"]

            # Check if the user exists
            cursor.execute("""
                SELECT * FROM risk_user_table 
                WHERE username = %s AND id = %s
            """, (username, id))
            user = cursor.fetchone()
            old_role = user["user_role"]
            
            email = decrypt(user["email"])
            print(email)

            if not user:
                return None  # User not found
            
            # ✅ Update the user's role
            cursor.execute("""
                UPDATE risk_user_table
                SET user_role = %s
                WHERE username = %s AND id = %s
            """, (new_role, username, id))

            if (old_role in ["Admin", "SC-Admin"]) and (new_role not in ["Admin", "SC-Admin"]):
                # Case 1: Admin privileges revoked
                message = f"Revoked admin privileges from user '{email}' from '{old_role}' to '{new_role}'"
                
            elif (old_role not in ["Admin", "SC-Admin"]) and (new_role in ["Admin", "SC-Admin"]):
                # Case 2: Admin privileges granted
                message = f"Granted admin privileges to user '{email}' from '{old_role}' to '{new_role}'"
                
            else:
                # Case 3: Other role change (non-admin related)
                message = f"Changed role for user '{email}' from '{old_role}' to '{new_role}'"
                
            post_event_log(cursor.connection, requestor_email, requestor_id, requestor_ip,
                            message,
                            "Success", "privilege_change")

            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            post_event_log(cursor.connection, requestor_email, requestor_id, requestor_ip,
                            f"Failed to change user role for '{email}'",
                            "Failed", "privilege_change")
            raise HTTPException(status_code=500, detail=f"Failed to update user role: {str(e)}")
        finally:
            cursor.close()

# Function to remove user from the database
def remove_user(username: str, id:str):
    with get_db("rw") as conn:
        cursor = conn.cursor()
        try:
            # Check if the user exists
            cursor.execute("""
                DELETE FROM risk_user_table 
                WHERE username = %s AND id = %s
            """, (username, id))
            deleted_main = cursor.rowcount
            
            conn.commit()
            return deleted_main > 0
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to update user role: {str(e)}")
        finally:
            cursor.close()

#Admin Change password
def Admin_change_password(username: str, id: str, newpassword: str):
    with get_db("rw") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            # 1. Check if user exists
            cursor.execute("SELECT * FROM risk_user_table WHERE username = %s AND id = %s", (username, id))
            user = cursor.fetchone()

            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # 2. Hash new password
            hashed_new_password = pwd_context.hash(newpassword)

            # 3. Update password in DB
            cursor.execute("UPDATE risk_user_table SET password = %s WHERE id = %s AND username = %s", (hashed_new_password, id, username))
            conn.commit()

            return True

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to change password: {str(e)}")

        finally:
            cursor.close()

# Developer access change their own role
def change_own_role(username: str, id:str, new_role:str):
    with get_db("rw") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            # Check if the user exists
            cursor.execute("""
                SELECT * FROM risk_user_table 
                WHERE username = %s AND id = %s
            """, (username, id))
            user = cursor.fetchone()

            if not user:
                return None  # User not found
            
            # ✅ Update the user's role
            cursor.execute("""
                UPDATE risk_user_table
                SET user_role = %s
                WHERE username = %s AND id = %s
            """, (new_role, username, id))

            # get latest data after update role
            cursor.execute("""
                SELECT * FROM risk_user_table 
                WHERE username = %s AND id = %s
            """, (username, id))
            latest_user = cursor.fetchone()

            conn.commit()

            # Set expiration time
            expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            expire_time = datetime.utcnow() + expires_delta

            # Generate JWT token
            access_token = create_access_token(data={"sub": latest_user["username"], "role": latest_user["user_role"], "access": latest_user["access"]})
        
            # Return the response with the token
            return {
                "success": True,
                "username": latest_user["username"],
                "message": "successful update role",
                "user_id": latest_user["id"],
                "role": latest_user["user_role"],
                "access": latest_user["access"],
                "access_token": access_token,
                "token_type": "bearer",
                "expires_at": expire_time.isoformat()  # Include expiration time
            }
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to update user role: {str(e)}")
        finally:
            cursor.close()


def update_user_name(user_id: int, fullname: str):
    # Encrypt the new fullname
    # encrypted_fullname = cipher.encrypt(fullname.encode()).decode()

    with get_db("rw") as conn:
        cursor = conn.cursor()
        try:
            # Check if user exists
            cursor.execute("SELECT id FROM risk_user_table WHERE id = %s", (user_id,))
            existing_user = cursor.fetchone()
            if not existing_user:
                raise HTTPException(status_code=404, detail="User not found")

            # Update the name column
            cursor.execute("""
                UPDATE risk_user_table
                SET user_role = %s
                WHERE id = %s
            """, (fullname, user_id))

            conn.commit()
            return {"success": True, "message": "User role updated successfully"}
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to update user name: {str(e)}")
        finally:
            cursor.close()

# Function to update user role
def user_log_event(user_ip: str, username:str, activity:str, status:str):
    with get_db("rw") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            #Get Requestor Details
            cursor.execute("""
                SELECT * FROM risk_user_table 
                WHERE username = %s
            """, (username,))
            requestor = cursor.fetchone()
            if not requestor:
                raise HTTPException(status_code=404, detail=f"User '{username}' not found")

            user_email = decrypt(requestor["email"])
            user_id = requestor["id"]

            post_event_log(cursor.connection, user_email, user_id, user_ip,
                            f"User '{user_email}' {activity}",
                            f"{status}", "user activity")

            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to update user role: {str(e)}")
        finally:
            cursor.close()

#get All Roles
def get_roles():
    try:
        with get_db("r") as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Step 1: Get user data
            cursor.execute("""
                SELECT 
                    r.id AS role_id,
                    r.name AS role_name,
                    r.guard_name,
                    r.created_at AS role_created_at,
                    r.updated_at AS role_updated_at,
                    p.id AS permission_id,
                    p.name AS permission_name,
                    p.guard_name AS permission_guard_name,
                    p.created_at AS permission_created_at,
                    p.updated_at AS permission_updated_at,
                    p."group" AS permission_group,
                    p.description AS permission_description
                from roles r 
                LEFT JOIN role_has_permissions rhp ON r.id = rhp.role_id
                LEFT JOIN permissions p ON rhp.permission_id = p.id
            """)
            roles_data = cursor.fetchall()

            grouped_roles = {}

            for row in roles_data:
                role_id = row["role_id"]
                if role_id not in grouped_roles:
                    grouped_roles[role_id] = {
                        "id": role_id,
                        "name": row["role_name"],
                        "guard_name": row["guard_name"],
                        "created_at": row["role_created_at"],
                        "updated_at": row["role_updated_at"],
                        "permissions": [],
                    }
                if row["permission_id"] is not None:
                    grouped_roles[role_id]["permissions"].append({
                        "id": row["permission_id"],
                        "name": row["permission_name"],
                        "guard_name": row["permission_guard_name"],
                        "created_at": row["permission_created_at"],
                        "updated_at": row["permission_updated_at"],
                        "group": row["permission_group"],
                        "description": row["permission_description"],
                    })

            cursor.close()

            return list(grouped_roles.values())

    except Exception as e:
        raise Exception(f"Database error during delete: {str(e)}")

#get All Roles
def get_permissions():
    try:
        with get_db("r") as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Step 1: Get user data
            cursor.execute("""
                SELECT *
                FROM permissions p 
            """)
            roles_data = cursor.fetchall()

            cursor.close()

            return roles_data

    except Exception as e:
        raise Exception(f"Database error during delete: {str(e)}")


## Audit Purpose ##
# Log Event
def post_event_log(conn, email: str, user_id: int, user_ip: str,
                   event_message: str, status: str, action_type: str):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO audit_logs_event 
                (email, user_id, user_ip, event_message, status, action_type)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (email, user_id, user_ip, event_message, status, action_type))

    except Exception as e:
        print(f"⚠️ Failed to log event: {str(e)}")

