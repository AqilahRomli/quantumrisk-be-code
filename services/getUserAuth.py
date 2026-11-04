# ==============================
# Standard Library
# ==============================
import json
import re
import hashlib
import secrets
from datetime import datetime, timedelta

# ==============================
# Third-Party Libraries
# ==============================
from psycopg2.extras import RealDictCursor
from psycopg2 import errors as pg_errors


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
from helper.loginAttempts import check_login_allowed, record_failed_login, clear_failed_logins
from helper.permissions import forget_permissions, ADMIN_ROLE, AccountInactive

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


#------------ Roles: one source of truth ------------------
# A user has exactly one role. It is stored in two places that must always agree:
#   - model_has_roles          (role id, used by the role / permission screens)
#   - risk_user_table.user_role (role name, used by the login token and the reports;
#     access is decided by permissions, see helper/permissions.py)
# Always change a user's role through set_user_role(), never one of them alone.

MODEL_TYPE = "App\\Models\\User"

# Roles counted as "admin privileges" in the activity log messages only
# (what a role may do is decided by its permissions)
PRIVILEGED_ROLES = {"Admin", "SC-Admin", "PM-Admin"}


# Log message for a role change
def role_change_message(email, old_role, new_role):
    if old_role in PRIVILEGED_ROLES and new_role not in PRIVILEGED_ROLES:
        return f"Revoked admin privileges from user '{email}' from '{old_role}' to '{new_role}'"
    if old_role not in PRIVILEGED_ROLES and new_role in PRIVILEGED_ROLES:
        return f"Granted admin privileges to user '{email}' from '{old_role}' to '{new_role}'"
    return f"Changed role for user '{email}' from '{old_role}' to '{new_role}'"


# Find a role by id or by name (name match ignores upper / lower case)
def find_role(cursor, role_id=None, role_name=None):
    if role_id is not None:
        cursor.execute("SELECT id, name FROM roles WHERE id = %s", (role_id,))
    else:
        cursor.execute("SELECT id, name FROM roles WHERE LOWER(name) = LOWER(%s)", ((role_name or "").strip(),))
    role = cursor.fetchone()

    if not role:
        wanted = role_id if role_id is not None else role_name
        raise HTTPException(status_code=400, detail=f"Role '{wanted}' does not exist. Add it in Role Management first.")
    return role


# Give a user one role, in both places. Must run inside the caller's transaction.
def set_user_role(cursor, user_id, role):
    cursor.execute("DELETE FROM model_has_roles WHERE model_id = %s AND model_type = %s", (user_id, MODEL_TYPE))
    cursor.execute(
        "INSERT INTO model_has_roles (role_id, model_id, model_type) VALUES (%s, %s, %s)",
        (role["id"], user_id, MODEL_TYPE)
    )
    cursor.execute("UPDATE risk_user_table SET user_role = %s WHERE id = %s", (role["name"], user_id))
    forget_permissions()


# Replace a user's extra (direct) permissions. Role permissions are not touched.
# Must run inside the caller's transaction.
def set_user_direct_permissions(cursor, user_id, permission_ids):
    unique_permission_ids = list(set(permission_ids))
    if unique_permission_ids:
        cursor.execute("SELECT id FROM permissions WHERE id = ANY(%s)", (unique_permission_ids,))
        found_ids = {row["id"] for row in cursor.fetchall()}
        missing_ids = sorted(set(unique_permission_ids) - found_ids)
        if missing_ids:
            raise HTTPException(status_code=400, detail=f"Invalid permission IDs: {missing_ids}")

    cursor.execute("DELETE FROM model_has_permissions WHERE model_id = %s AND model_type = %s", (user_id, MODEL_TYPE))
    forget_permissions()
    for permission_id in unique_permission_ids:
        cursor.execute(
            "INSERT INTO model_has_permissions (permission_id, model_id, model_type) VALUES (%s, %s, %s)",
            (permission_id, user_id, MODEL_TYPE)
        )


# A user's permission names: their role's permissions + their extra permissions.
# The Admin role gets every permission. Sent to the frontend at login and switch
# role (the frontend keeps it in localStorage to show / hide menus and buttons);
# the backend itself always checks permissions from the database (helper/permissions.py).
def load_user_permissions(cursor, user_id):
    cursor.execute(
        """
        SELECT r.name
        FROM model_has_roles m
        JOIN roles r ON r.id = m.role_id
        WHERE m.model_id = %s AND m.model_type = %s
        LIMIT 1
        """,
        (user_id, MODEL_TYPE)
    )
    role = cursor.fetchone()

    if role and role["name"] == ADMIN_ROLE:
        cursor.execute("SELECT name FROM permissions")
    else:
        cursor.execute(
            """
            SELECT p.name
            FROM permissions p
            WHERE p.id IN (
                SELECT rhp.permission_id
                FROM role_has_permissions rhp
                JOIN model_has_roles m ON m.role_id = rhp.role_id
                WHERE m.model_id = %s AND m.model_type = %s
                UNION
                SELECT mhp.permission_id
                FROM model_has_permissions mhp
                WHERE mhp.model_id = %s AND mhp.model_type = %s
            )
            """,
            (user_id, MODEL_TYPE, user_id, MODEL_TYPE)
        )
    return sorted(row["name"] for row in cursor.fetchall())


#------------ User Registration ------------------
# Insert New User Details
# Emails are matched ignoring upper / lower case and surrounding spaces: the
# lookup hash (email_hash) is of the lower-case email. The email itself is
# stored as typed (encrypted).
def hash_email(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


# The hash as it was made before (case-sensitive). Rows not yet updated by
# tools/rehash_emails.py still have it; login updates a row when it finds one.
def legacy_hash_email(email: str) -> str:
    return hashlib.sha256(email.strip().encode()).hexdigest()


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
    # Users sign in with Entra ID. The account gets a random password that nobody
    # knows, so it cannot be used with username + password login until an admin
    # sets one (admin change password).
    password = secrets.token_urlsafe(32)

    user_data = {
        "username": username,
        "password": pwd_context.hash(password),
        "email": encrypt(email),
        "staff_id": encrypt(staff_id),
        "fullname": encrypt(fullname),
        "division": division,
        "user_role": user_role,
        "user_access": user_access,
        "email_hash": hash_email(email)
    }

    # ✅ Check duplicate (the email in any upper / lower case)
    cursor.execute("""
        SELECT is_active FROM risk_user_table
        WHERE username = %s OR email_hash = ANY(%s)
    """, (user_data["username"], [user_data["email_hash"], legacy_hash_email(email)]))

    existing = cursor.fetchall()
    if existing:
        # an inactive user should be reactivated, not registered again
        raise ValueError("INACTIVE_USER" if not any(row["is_active"] for row in existing) else "DUPLICATE_USER")

    # ✅ The role must exist (checked before anything is written)
    role = find_role(cursor, role_name=user_role)
    user_data["user_role"] = role["name"]

    # ✅ Insert
    cursor.execute("""
        INSERT INTO risk_user_table 
        (username, password, user_role, email, staff_id, division, access, name, email_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
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
    new_user_id = cursor.fetchone()["id"]

    # ✅ Role in both places (model_has_roles + user_role)
    set_user_role(cursor, new_user_id, role)

    # ✅ Logging
    if role["name"] in PRIVILEGED_ROLES:
        message = f"Success Created new user: '{email}' with Admin privilege ('{role['name']}')"
    else:
        message = f"Success Created new user: '{email}' with '{role['name']}'"

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

# User access values a new user can get
USER_ACCESS_OPTIONS = ("User", "Developer")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
NEW_USER_FIELDS = {
    "fullname": "Full Name",
    "username": "Username",
    "email": "Email",
    "staffId": "Staff ID",
    "division": "Division",
    "user_role": "Role",
    "user_access": "User Access",
}


# Problem with one new user's details, or None. `seen` holds the usernames and
# emails earlier in the same request, so a list cannot register someone twice.
def check_new_user(user: dict, seen: set):
    missing = [label for field, label in NEW_USER_FIELDS.items() if not user[field]]
    if missing:
        return f"Missing: {', '.join(missing)}"
    if not EMAIL_PATTERN.match(user["email"]):
        return "Email is not valid"
    if user["user_access"] not in USER_ACCESS_OPTIONS:
        return f"User Access must be one of: {', '.join(USER_ACCESS_OPTIONS)}"
    for key in ("username:" + user["username"].lower(), "email:" + user["email"].lower()):
        if key in seen:
            return f"{'Username' if key.startswith('username') else 'Email'} appears more than once in the list"
    return None


# Register one or more users: the individual form sends a list of one, bulk
# register sends the uploaded rows. Each user is saved in its own transaction,
# so one bad row does not stop the others. Returns one result per user, in order:
#   status "registered" | "duplicate" (already in the system) | "invalid" | "failed"
def register_users(username_requestor: str, requestor_ip: str, users: list):
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
            conn.commit()  # end the read, each user below gets its own transaction

            results = []
            seen = set()
            for index, raw in enumerate(users):
                user = {field: str(raw.get(field) or "").strip() for field in NEW_USER_FIELDS}
                result = {"index": index, "username": user["username"], "email": user["email"]}

                problem = check_new_user(user, seen)
                seen.update({"username:" + user["username"].lower(), "email:" + user["email"].lower()})
                if problem:
                    results.append({**result, "status": "invalid", "message": problem})
                    continue

                try:
                    insert_newuser_details(cursor,
                        requestor_email, requestor_id, requestor_ip,
                        user["fullname"], user["username"], user["email"],
                        user["staffId"], user["division"],
                        user["user_role"], user["user_access"]
                    )
                    conn.commit()
                    results.append({**result, "status": "registered", "message": "Registered"})

                except ValueError as e:
                    conn.rollback()
                    if str(e) == "DUPLICATE_USER":
                        message = "Username or Email already exists"
                    elif str(e) == "INACTIVE_USER":
                        message = "This user already exists but is inactive. Reactivate them in User Management."
                    else:
                        raise
                    results.append({**result, "status": "duplicate", "message": message})

                except HTTPException as e:
                    conn.rollback()  # e.g. role does not exist (400)
                    results.append({**result, "status": "invalid", "message": e.detail})

                except Exception as e:
                    conn.rollback()
                    post_event_log(conn, requestor_email, requestor_id, requestor_ip,
                                   f"Failed to Create new user, '{user['email']}'", "Failed", "User_Creation")
                    conn.commit()  # keep the failed-attempt log
                    results.append({**result, "status": "failed", "message": f"Failed to register user: {str(e)}"})

            registered = sum(1 for r in results if r["status"] == "registered")
            return {
                "success": True,
                "message": f"{registered} of {len(results)} user(s) registered",
                "registered": registered,
                "not_registered": len(results) - registered,
                "results": results,
            }

        except HTTPException:
            conn.rollback()
            raise  # expected error (404), keep its own status code

        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to register users: {str(e)}")

        finally:
            cursor.close()


#---------------- Login ---------------------
# Function to authenticate a user during login
def login_user(username: str, password: str):
    with get_db("rw") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            # Blocked after too many wrong passwords? (raises 429)
            check_login_allowed(username)

            # Check if the user exists
            cursor.execute("SELECT * FROM risk_user_table WHERE username = %s", (username,))
            user = cursor.fetchone()
            if not user:
                record_failed_login(username)
                raise HTTPException(status_code=400, detail="Invalid username or password")
            
            # Verify the password
            if not pwd_context.verify(password, user["password"]):
                record_failed_login(username)
                raise HTTPException(status_code=400, detail="Invalid username or password")

            clear_failed_logins(username)

            # Deactivated users cannot log in (checked after the password, so a
            # wrong guess does not reveal that the account exists)
            if not user["is_active"]:
                raise AccountInactive()

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
                "permissions": load_user_permissions(cursor, user_id),
                "access_token": access_token,
                "token_type": "bearer",
                "expires_at": expire_time.isoformat()  # Include expiration time
            }
        except HTTPException:
            conn.rollback()
            raise  # expected error (400 / 404), keep its own status code
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
    if not email:
        raise HTTPException(status_code=401, detail="Invalid ID token: no email")
    email_hash = hash_email(email)

    with get_db("rw") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            # Check if the user exists (email in any upper / lower case). A row whose
            # hash is still the old case-sensitive one is found too, and updated.
            cursor.execute("""
                SELECT * FROM risk_user_table
                WHERE email_hash = ANY(%s)
                ORDER BY (email_hash = %s) DESC
                LIMIT 1
            """, ([email_hash, legacy_hash_email(email)], email_hash))
            user = cursor.fetchone()
            if not user:
                post_event_log(cursor.connection, email, None, user_ip, "Unprovisioned user login attempt", "Failed", "Login")
                conn.commit()  # keep the failed-attempt log
                raise HTTPException(status_code=400, detail="User not provisioned")
            if user["email_hash"] != email_hash:
                cursor.execute("UPDATE risk_user_table SET email_hash = %s WHERE id = %s", (email_hash, user["id"]))
            if not user["is_active"]:
                post_event_log(cursor.connection, email, user["id"], user_ip, "Inactive user login attempt", "Failed", "Login")
                conn.commit()  # keep the failed-attempt log
                raise AccountInactive()

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
                "permissions": load_user_permissions(cursor, user["id"]),
                "access_token": access_token,
                "token_type": "bearer",
                "expires_at": expire_time.isoformat()  # Include expiration time
            }
        except HTTPException:
            conn.rollback()
            raise  # expected error (400 / 404), keep its own status code
        except Exception as e:
            conn.rollback()
            post_event_log(cursor.connection, email, None, user_ip, f"Failed login attempt for user '{email}'", "Failed", "Login")
            conn.commit()  # keep the failed-attempt log
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
                SELECT id, username, name, user_role, email, staff_id, division, timestamp
                FROM risk_user_table
                WHERE id = %s AND username = %s
            """, (user_id, username))
            user_data = cursor.fetchall()

            for row in user_data:
                for field in ("email", "staff_id", "name"):
                    try:
                        if row.get(field):
                            row[field] = decrypt(row[field])
                    except InvalidToken:
                        # Skip if the value is not encrypted
                        pass

            cursor.close()

            return user_data

    except Exception as e:
        raise Exception(f"Database error during delete: {str(e)}")

#--------------- Admin Page --------------------
# Activate / deactivate a user (users are deactivated, never deleted).
# An inactive user cannot log in and has no permissions; their role, extra
# permissions and history are kept, so reactivating gives back the same access.
def update_user_status(requestor_username: str, requestor_ip: str, user_id: int, is_active: bool):
    with get_db("rw") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            requestor_id, requestor_email = _requestor(cursor, requestor_username)

            cursor.execute("SELECT id, username, email, is_active FROM risk_user_table WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            if not is_active:
                if user["id"] == requestor_id:
                    raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

                # Keep at least one active Admin, so someone can still manage users
                cursor.execute(
                    """
                    SELECT
                        EXISTS (
                            SELECT 1 FROM model_has_roles m JOIN roles r ON r.id = m.role_id
                            WHERE m.model_id = %s AND m.model_type = %s AND r.name = %s
                        ) AS is_admin,
                        (
                            SELECT COUNT(*)
                            FROM risk_user_table u
                            JOIN model_has_roles m ON m.model_id = u.id AND m.model_type = %s
                            JOIN roles r ON r.id = m.role_id
                            WHERE r.name = %s AND u.is_active AND u.id <> %s
                        ) AS other_admins
                    """,
                    (user_id, MODEL_TYPE, ADMIN_ROLE, MODEL_TYPE, ADMIN_ROLE, user_id)
                )
                admins = cursor.fetchone()
                if admins["is_admin"] and admins["other_admins"] == 0:
                    raise HTTPException(status_code=400, detail="This is the last active Admin and cannot be deactivated")

            if user["is_active"] == is_active:
                return {"success": True, "message": f"User is already {'active' if is_active else 'inactive'}",
                        "user_id": user_id, "is_active": is_active}

            cursor.execute("UPDATE risk_user_table SET is_active = %s WHERE id = %s", (is_active, user_id))
            post_event_log(conn, requestor_email, requestor_id, requestor_ip,
                           f"{'Reactivated' if is_active else 'Deactivated'} user '{_user_email(user)}'",
                           "Success", "user_status")
            conn.commit()
            forget_permissions()  # takes effect at once on this server process

            return {"success": True, "message": f"User {'reactivated' if is_active else 'deactivated'}",
                    "user_id": user_id, "is_active": is_active}
        except HTTPException:
            conn.rollback()
            raise  # expected error (400 / 404), keep its own status code
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to update user status: {str(e)}")
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

        except HTTPException:
            conn.rollback()
            raise  # expected error (400 / 404), keep its own status code
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to change password: {str(e)}")

        finally:
            cursor.close()

# Developer access change their own role
# Every switch is written to the audit log (action type "role_switch"), in the
# same transaction as the switch, so a switch is never saved without its log.
SWITCH_ROLE_LOG = "role_switch"


def _user_email(user):
    try:
        return decrypt(user["email"])
    except InvalidToken:
        return user["email"]


def change_own_role(username: str, id:str, new_role:str, requestor_ip: str = None):
    user = None
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

            email = _user_email(user)
            old_role = user["user_role"]
            try:
                role = find_role(cursor, role_name=new_role)
            except HTTPException:
                conn.rollback()
                post_event_log(conn, email, user["id"], requestor_ip,
                               f"Switch own role refused for '{email}': role '{new_role}' does not exist",
                               "Failed", SWITCH_ROLE_LOG)
                conn.commit()  # keep the failed-attempt log
                raise

            # ✅ Update the user's role (model_has_roles + user_role)
            set_user_role(cursor, user["id"], role)
            post_event_log(conn, email, user["id"], requestor_ip,
                           f"Switched own role (Developer access): {role_change_message(email, old_role, role['name'])}",
                           "Success", SWITCH_ROLE_LOG)

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
                "permissions": load_user_permissions(cursor, latest_user["id"]),
                "access_token": access_token,
                "token_type": "bearer",
                "expires_at": expire_time.isoformat()  # Include expiration time
            }
        except HTTPException:
            conn.rollback()
            raise  # expected error (400 / 404), keep its own status code
        except Exception as e:
            conn.rollback()
            if user:
                post_event_log(conn, _user_email(user), user["id"], requestor_ip,
                               f"Failed to switch own role to '{new_role}'", "Failed", SWITCH_ROLE_LOG)
                conn.commit()  # keep the failed-attempt log
            raise HTTPException(status_code=500, detail=f"Failed to update user role: {str(e)}")
        finally:
            cursor.close()


# A Developer asked to switch the role of another account (refused): logged
def log_switch_other_refused(requestor_username: str, requestor_ip: str, target_username: str):
    with get_db("rw") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute("SELECT id, email FROM risk_user_table WHERE username = %s", (requestor_username,))
            requestor = cursor.fetchone()
            if requestor:
                post_event_log(conn, _user_email(requestor), requestor["id"], requestor_ip,
                               f"Switch role refused: tried to switch the role of another user '{target_username}'",
                               "Failed", SWITCH_ROLE_LOG)
                conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"⚠️ Failed to log refused switch role: {str(e)}")
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
        except HTTPException:
            conn.rollback()
            raise  # expected error (400 / 404), keep its own status code
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


#get All Permission
def get_permissions():
    try:
        with get_db("r") as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Step 1: Get user data
            cursor.execute("""
                SELECT 
                    p.id, 
                    p.name,
                    p."group" AS "group",
                    p.description,
                    p.created_at
                from permissions p
                ORDER BY p."group", p.id
            """)
            permission_data = cursor.fetchall()

            cursor.close()

            grouped_permissions = {}

            for row in permission_data:
                group_name = row.get("group") or "ungrouped"
                if group_name not in grouped_permissions:
                    grouped_permissions[group_name] = []

                grouped_permissions[group_name].append({
                    "id": row["id"],
                    "name": row["name"],
                    "group": row.get("group"),
                    "description": row.get("description"),
                    "created_at": row.get("created_at")
                })

            return grouped_permissions

    except Exception as e:
        raise Exception(f"Database error during delete: {str(e)}")


def update_role_detail(role_id: int, role_name: str, permission_ids: list[int]):
    with get_db("rw") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            # Check if role exists
            cursor.execute("SELECT id, name FROM roles WHERE id = %s", (role_id,))
            role = cursor.fetchone()
            if not role:
                raise HTTPException(status_code=404, detail="Role not found")

            # Role names must stay unique: users are linked to a role by its name too
            role_name = (role_name or "").strip()
            if not role_name:
                raise HTTPException(status_code=400, detail="Role name cannot be empty")
            cursor.execute("SELECT 1 FROM roles WHERE LOWER(name) = LOWER(%s) AND id <> %s", (role_name, role_id))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail=f"A role named '{role_name}' already exists")

            # Validate permissions to avoid partial/unclear DB errors
            if permission_ids:
                cursor.execute(
                    "SELECT id FROM permissions WHERE id = ANY(%s)",
                    (permission_ids,)
                )
                found_ids = {row["id"] for row in cursor.fetchall()}
                missing_ids = sorted(set(permission_ids) - found_ids)
                if missing_ids:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid permission IDs: {missing_ids}"
                    )

            # Update role name
            cursor.execute(
                """
                UPDATE roles
                SET name = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (role_name, role_id)
            )

            # Renamed → keep the role name on its users in step
            if role_name != role["name"]:
                cursor.execute(
                    """
                    UPDATE risk_user_table
                    SET user_role = %s
                    WHERE user_role = %s
                       OR id IN (SELECT model_id FROM model_has_roles WHERE role_id = %s)
                    """,
                    (role_name, role["name"], role_id)
                )

            # Reset current role permissions
            cursor.execute("DELETE FROM role_has_permissions WHERE role_id = %s", (role_id,))
            forget_permissions()

            # Insert updated permission mappings
            for permission_id in set(permission_ids):
                cursor.execute(
                    """
                    INSERT INTO role_has_permissions (role_id, permission_id)
                    VALUES (%s, %s)
                    """,
                    (role_id, permission_id)
                )

            conn.commit()

            return {
                "success": True,
                "message": "Role details updated successfully",
                "role_id": role_id,
                "role_name": role_name,
                "permission_count": len(set(permission_ids))
            }
        except HTTPException:
            conn.rollback()
            raise
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to update role details: {str(e)}")
        finally:
            cursor.close()


def create_role_detail(role_name: str, permission_ids: list[int]):
    with get_db("rw") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            normalized_role_name = role_name.strip()
            if not normalized_role_name:
                raise HTTPException(status_code=400, detail="Role name cannot be empty")

            # Role names must stay unique: users are linked to a role by its name too
            cursor.execute("SELECT 1 FROM roles WHERE LOWER(name) = LOWER(%s)", (normalized_role_name,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail=f"A role named '{normalized_role_name}' already exists")

            # Validate permissions before creating role
            unique_permission_ids = list(set(permission_ids))
            if unique_permission_ids:
                cursor.execute(
                    "SELECT id FROM permissions WHERE id = ANY(%s)",
                    (unique_permission_ids,)
                )
                found_ids = {row["id"] for row in cursor.fetchall()}
                missing_ids = sorted(set(unique_permission_ids) - found_ids)
                if missing_ids:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid permission IDs: {missing_ids}"
                    )

            # Create the role
            cursor.execute(
                """
                INSERT INTO roles (name, guard_name, created_at, updated_at)
                VALUES (%s, %s, NOW(), NOW())
                RETURNING id, name, guard_name, created_at, updated_at
                """,
                (normalized_role_name, "web")
            )
            new_role = cursor.fetchone()

            if not new_role:
                raise HTTPException(status_code=500, detail="Failed to create role")

            # Insert role permissions
            for permission_id in unique_permission_ids:
                cursor.execute(
                    """
                    INSERT INTO role_has_permissions (role_id, permission_id)
                    VALUES (%s, %s)
                    """,
                    (new_role["id"], permission_id)
                )

            # Fetch role permissions for response
            cursor.execute(
                """
                SELECT
                    p.id,
                    p.name,
                    p.guard_name,
                    p."group" AS "group",
                    p.description,
                    p.created_at,
                    p.updated_at
                FROM permissions p
                INNER JOIN role_has_permissions rhp ON p.id = rhp.permission_id
                WHERE rhp.role_id = %s
                ORDER BY p.id
                """,
                (new_role["id"],)
            )
            permissions = cursor.fetchall()

            conn.commit()

            return {
                "success": True,
                "role": {
                    "id": new_role["id"],
                    "name": new_role["name"],
                    "guard_name": new_role["guard_name"],
                    "created_at": new_role["created_at"],
                    "updated_at": new_role["updated_at"],
                    "permissions": permissions,
                }
            }
        except HTTPException:
            conn.rollback()
            raise
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to create role: {str(e)}")
        finally:
            cursor.close()


def delete_role_detail(role_id: int):
    with get_db("rw") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            # A role that users still have cannot be deleted
            cursor.execute("SELECT name FROM roles WHERE id = %s", (role_id,))
            role = cursor.fetchone()
            if not role:
                raise HTTPException(status_code=404, detail="Role not found")

            cursor.execute(
                """
                SELECT COUNT(*) AS users
                FROM risk_user_table
                WHERE user_role = %s
                   OR id IN (SELECT model_id FROM model_has_roles WHERE role_id = %s)
                """,
                (role["name"], role_id)
            )
            in_use = cursor.fetchone()["users"]
            if in_use:
                raise HTTPException(
                    status_code=409,
                    detail=f"{in_use} user(s) still have the role '{role['name']}'. Move them to another role first."
                )

            cursor.execute("DELETE FROM roles WHERE id = %s", (role_id,))
            deleted_count = cursor.rowcount

            conn.commit()

            if deleted_count == 0:
                raise HTTPException(status_code=404, detail="Role not found")

            return {
                "success": True,
                "message": "Role deleted successfully",
                "role_id": role_id
            }
        except HTTPException:
            conn.rollback()
            raise
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to delete role: {str(e)}")
        finally:
            cursor.close()


#------------ Permissions: create / delete ------------------
# A permission is only a name until code checks it (require_permission in the
# backend, data.permissions / the menu in the frontend). Creating one here lets
# it be assigned to roles before the code that uses it is deployed.

GUARD_NAME = "web"  # guard_name of every role / permission

# Lower case words joined by "-" or ".", e.g. "report-export.view"
PERMISSION_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:[-.][a-z0-9]+)*$")
# Lower case words joined by "-", e.g. "management"
PERMISSION_GROUP_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _requestor(cursor, username):
    cursor.execute("SELECT id, email FROM risk_user_table WHERE username = %s", (username,))
    requestor = cursor.fetchone()
    if not requestor:
        raise HTTPException(status_code=404, detail=f"Requestor '{username}' not found")
    try:
        email = decrypt(requestor["email"])
    except InvalidToken:
        email = requestor["email"]
    return requestor["id"], email


def create_permission(requestor_username: str, requestor_ip: str, name: str, group: str, description: str):
    name, group, description = (name or "").strip(), (group or "").strip().lower(), (description or "").strip()

    if not name or not group or not description:
        raise HTTPException(status_code=400, detail="Name, group and description are required")
    if len(name) > 255 or not PERMISSION_NAME_PATTERN.match(name):
        raise HTTPException(status_code=400, detail=(
            "Name must be lower case letters and digits, with words joined by '-' or '.' "
            "(for example 'report-export.view'), at most 255 characters"))
    if len(group) > 255 or not PERMISSION_GROUP_PATTERN.match(group):
        raise HTTPException(status_code=400, detail=(
            "Group must be lower case letters and digits, with words joined by '-' (for example 'management')"))

    with get_db("rw") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            requestor_id, requestor_email = _requestor(cursor, requestor_username)

            # Names are unique, ignoring upper / lower case
            cursor.execute("SELECT 1 FROM permissions WHERE LOWER(name) = LOWER(%s)", (name,))
            if cursor.fetchone():
                raise HTTPException(status_code=409, detail=f"Permission '{name}' already exists")

            cursor.execute(
                """
                INSERT INTO permissions (name, guard_name, "group", description, created_at, updated_at)
                VALUES (%s, %s, %s, %s, NOW(), NOW())
                RETURNING id, name, "group", description, created_at
                """,
                (name, GUARD_NAME, group, description)
            )
            permission = cursor.fetchone()

            post_event_log(conn, requestor_email, requestor_id, requestor_ip,
                           f"Created permission '{name}' in group '{group}'", "Success", "permission_change")
            conn.commit()

            return {
                "success": True,
                "message": "Permission created successfully",
                "permission": dict(permission),
            }
        except HTTPException:
            conn.rollback()
            raise  # expected error (400 / 404 / 409), keep its own status code
        except pg_errors.UniqueViolation:
            conn.rollback()  # saved by someone else at the same moment (unique index)
            raise HTTPException(status_code=409, detail=f"Permission '{name}' already exists")
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to create permission: {str(e)}")
        finally:
            cursor.close()


# A permission that a role or a user still has cannot be deleted: code may check
# it, and deleting it would take that access away from them.
def delete_permission(requestor_username: str, requestor_ip: str, permission_id: int):
    with get_db("rw") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            requestor_id, requestor_email = _requestor(cursor, requestor_username)

            cursor.execute("SELECT id, name FROM permissions WHERE id = %s", (permission_id,))
            permission = cursor.fetchone()
            if not permission:
                raise HTTPException(status_code=404, detail="Permission not found")

            cursor.execute(
                """
                SELECT r.name
                FROM role_has_permissions rhp
                JOIN roles r ON r.id = rhp.role_id
                WHERE rhp.permission_id = %s
                ORDER BY r.name
                """,
                (permission_id,)
            )
            roles = [row["name"] for row in cursor.fetchall()]
            cursor.execute(
                "SELECT COUNT(*) AS users FROM model_has_permissions WHERE permission_id = %s",
                (permission_id,)
            )
            users = cursor.fetchone()["users"]

            if roles or users:
                used_by = []
                if roles:
                    used_by.append(f"role(s) {', '.join(roles)}")
                if users:
                    used_by.append(f"{users} user(s) as an extra permission")
                raise HTTPException(
                    status_code=409,
                    detail=f"Permission '{permission['name']}' is still given to {' and '.join(used_by)}. "
                           f"Remove it from them first."
                )

            cursor.execute("DELETE FROM permissions WHERE id = %s", (permission_id,))
            post_event_log(conn, requestor_email, requestor_id, requestor_ip,
                           f"Deleted permission '{permission['name']}'", "Success", "permission_change")
            conn.commit()
            forget_permissions()

            return {
                "success": True,
                "message": "Permission deleted successfully",
                "permission_id": permission_id,
            }
        except HTTPException:
            conn.rollback()
            raise  # expected error (404 / 409), keep its own status code
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to delete permission: {str(e)}")
        finally:
            cursor.close()


def get_users_by_role(role_id: int):
    with get_db("r") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute(
                """
                SELECT
                    ru.id,
                    ru.username,
                    ru.name,
                    ru.email,
                    ru.staff_id,
                    ru.division
                FROM model_has_roles mhr
                INNER JOIN risk_user_table ru ON mhr.model_id = ru.id
                WHERE mhr.role_id = %s
                ORDER BY ru.id
                """,
                (role_id,)
            )
            users_data = cursor.fetchall()

            for row in users_data:
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

            return users_data
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get users by role: {str(e)}")
        finally:
            cursor.close()


def get_all_user_details_v2():
    with get_db("r") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute(
                """
                SELECT
                    ru.id,
                    ru.username,
                    ru.staff_id,
                    ru.email,
                    ru.is_active,
                    ult.login_time AS last_login,
                    r.id AS role_id,
                    r.name AS role_name
                FROM risk_user_table ru
                LEFT JOIN model_has_roles mhr ON ru.id = mhr.model_id
                LEFT JOIN roles r ON mhr.role_id = r.id
                LEFT JOIN (
                    SELECT username, MAX(login_time) AS login_time
                    FROM user_login_track
                    GROUP BY username
                ) ult ON ru.username = ult.username
                ORDER BY ru.id
                """
            )
            rows = cursor.fetchall()

            grouped_users = {}

            for row in rows:
                user_id = row["id"]
                if user_id not in grouped_users:
                    staff_id = row.get("staff_id")
                    email = row.get("email")

                    try:
                        if staff_id:
                            staff_id = decrypt(staff_id)
                    except InvalidToken:
                        pass

                    try:
                        if email:
                            email = decrypt(email)
                    except InvalidToken:
                        pass

                    grouped_users[user_id] = {
                        "id": user_id,
                        "username": row.get("username"),
                        "staff_id": staff_id,
                        "email": email,
                        "last_login": row.get("last_login"),
                        "is_active": row.get("is_active"),
                        "roles": [],
                    }

                if row.get("role_id") is not None:
                    grouped_users[user_id]["roles"].append({
                        "id": row.get("role_id"),
                        "name": row.get("role_name"),
                    })

            return list(grouped_users.values())
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get all user details: {str(e)}")
        finally:
            cursor.close()


def get_user_with_permissions(user_id: int):
    with get_db("r") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute(
                """
                SELECT
                    ru.id,
                    ru.username,
                    ru.name,
                    ru.staff_id,
                    ru.email
                FROM risk_user_table ru
                WHERE ru.id = %s
                """,
                (user_id,)
            )
            user = cursor.fetchone()

            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # Roles assigned to user
            cursor.execute(
                """
                SELECT r.id, r.name
                FROM model_has_roles mhr
                INNER JOIN roles r ON mhr.role_id = r.id
                WHERE mhr.model_id = %s
                ORDER BY r.id
                """,
                (user_id,)
            )
            roles = cursor.fetchall()

            # Permissions from roles
            cursor.execute(
                """
                SELECT
                    p.id,
                    p.name,
                    p."group" AS "group",
                    p.description
                FROM model_has_roles mhr
                INNER JOIN role_has_permissions rhp ON mhr.role_id = rhp.role_id
                INNER JOIN permissions p ON rhp.permission_id = p.id
                WHERE mhr.model_id = %s
                ORDER BY p.id
                """,
                (user_id,)
            )
            role_permission_rows = cursor.fetchall()

            role_permissions_map = {}
            for permission in role_permission_rows:
                permission_id = permission["id"]
                if permission_id not in role_permissions_map:
                    role_permissions_map[permission_id] = {
                        "id": permission_id,
                        "name": permission.get("name"),
                        "group": permission.get("group"),
                        "description": permission.get("description"),
                        "source": "role has permission",
                    }
            role_permissions = list(role_permissions_map.values())

            # Direct permissions (if table exists)
            cursor.execute("SELECT to_regclass('public.model_has_permissions') AS table_name")
            direct_permission_table = cursor.fetchone()

            direct_permissions = []
            if direct_permission_table and direct_permission_table.get("table_name"):
                cursor.execute(
                    """
                    SELECT
                        p.id,
                        p.name,
                        p."group" AS "group",
                        p.description
                    FROM model_has_permissions mhp
                    INNER JOIN permissions p ON mhp.permission_id = p.id
                    WHERE mhp.model_id = %s
                    ORDER BY p.id
                    """,
                    (user_id,)
                )
                direct_permission_rows = cursor.fetchall()

                for permission in direct_permission_rows:
                    direct_permissions.append({
                        "id": permission["id"],
                        "name": permission.get("name"),
                        "group": permission.get("group"),
                        "description": permission.get("description"),
                        "source": "model has permission",
                    })

            # Combined unique permissions
            all_permissions_map = {}
            for permission in role_permissions:
                all_permissions_map[permission["id"]] = {
                    "id": permission["id"],
                    "name": permission.get("name"),
                    "group": permission.get("group"),
                    "description": permission.get("description"),
                }
            for permission in direct_permissions:
                all_permissions_map[permission["id"]] = {
                    "id": permission["id"],
                    "name": permission.get("name"),
                    "group": permission.get("group"),
                    "description": permission.get("description"),
                }

            name = user.get("name")
            staff_id = user.get("staff_id")
            email = user.get("email")

            try:
                if name:
                    name = decrypt(name)
            except InvalidToken:
                pass

            try:
                if staff_id:
                    staff_id = decrypt(staff_id)
            except InvalidToken:
                pass

            try:
                if email:
                    email = decrypt(email)
            except InvalidToken:
                pass

            return {
                "success": True,
                "user": {
                    "id": user["id"],
                    "username": user.get("username"),
                    "name": name,
                    "staff_id": staff_id,
                    "email": email,
                    "roles": [{"id": role["id"], "name": role.get("name")} for role in roles],
                    "permissions": {
                        "from_roles": role_permissions,
                        "direct": direct_permissions,
                        "all": list(all_permissions_map.values()),
                    },
                    "last_login": user.get("last_login"),
                    "created_at": user.get("created_at"),
                    "updated_at": user.get("updated_at"),
                }
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get user permissions detail: {str(e)}")
        finally:
            cursor.close()

# Save a user's role and extra permissions together (User Management drawer).
# One transaction: either both change or nothing changes.
def update_user_access(requestor_username: str, requestor_ip: str, user_id: int, role_id: int, permission_ids: list[int]):
    with get_db("rw") as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute("SELECT id, email FROM risk_user_table WHERE username = %s", (requestor_username,))
            requestor = cursor.fetchone()
            if not requestor:
                raise HTTPException(status_code=404, detail=f"Requestor '{requestor_username}' not found")

            cursor.execute("SELECT id, username, name, email, user_role FROM risk_user_table WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            role = find_role(cursor, role_id=role_id)
            old_role = user["user_role"]

            set_user_role(cursor, user_id, role)
            set_user_direct_permissions(cursor, user_id, permission_ids)

            try:
                requestor_email = decrypt(requestor["email"])
                user_email = decrypt(user["email"])
            except InvalidToken:
                requestor_email, user_email = requestor["email"], user["email"]

            post_event_log(cursor.connection, requestor_email, requestor["id"], requestor_ip,
                           f"{role_change_message(user_email, old_role, role['name'])}, "
                           f"{len(set(permission_ids))} extra permission(s)",
                           "Success", "privilege_change")

            conn.commit()

            name = user.get("name")
            try:
                if name:
                    name = decrypt(name)
            except InvalidToken:
                pass

            return {
                "success": True,
                "message": "User role and permissions updated successfully",
                "user": {
                    "id": user["id"],
                    "username": user["username"],
                    "name": name,
                    "role": {"id": role["id"], "name": role["name"]},
                    "direct_permission_ids": sorted(set(permission_ids)),
                }
            }
        except HTTPException:
            conn.rollback()
            raise  # expected error (400 / 404), keep its own status code
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to update user access: {str(e)}")
        finally:
            cursor.close()


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

