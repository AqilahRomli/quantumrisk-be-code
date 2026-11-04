# ==============================
# Standard Library
# ==============================
import time

# ==============================
# Third-Party Libraries
# ==============================
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# ==============================
# Internal Modules
# ==============================
from core import db
from helper.tokenManagement import decode_access_token

# ==========================================================================
# Permission checks.
#
# A user's permissions = permissions of their role (role_has_permissions)
#                       + their extra permissions (model_has_permissions).
# The Admin role is always allowed everything.
#
# Permissions are always read from the database, never from the token or the
# browser (localStorage can be edited by the user). The answer is remembered
# for CACHE_SECONDS per user, so a change made by an admin applies within that
# time; on the server process that made the change it applies at once.
# ==========================================================================

ADMIN_ROLE = "Admin"
DEVELOPER_ACCESS = "Developer"
MODEL_TYPE = "App\\Models\\User"
CACHE_SECONDS = 60

bearer = HTTPBearer()
_cache = {}  # username -> (expires_at, access)


class PermissionDenied(HTTPException):
    """403 that the frontend can recognise: its body carries code = PERMISSION_DENIED."""
    code = "PERMISSION_DENIED"

    def __init__(self):
        super().__init__(
            status_code=403,
            detail="You do not have permission to do this. Your access may have been changed by an administrator."
        )


class AccountInactive(HTTPException):
    """403 for a deactivated user: its body carries code = ACCOUNT_INACTIVE."""
    code = "ACCOUNT_INACTIVE"

    def __init__(self):
        super().__init__(
            status_code=403,
            detail="Your account is inactive. Please contact the administrator."
        )


# Forget remembered permissions (call after a role, permission or status change)
def forget_permissions():
    _cache.clear()


async def get_user_access(username: str, token_role: str = None, fresh: bool = False) -> dict:
    """{"role": role name or None, "is_admin": bool, "is_developer": bool,
        "inactive": bool, "permissions": set of permission names}

    An inactive user (risk_user_table.is_active = false) has no permissions at all,
    whatever their role; their role and extra permissions are kept for reactivation.

    token_role: the role in the caller's login token. If it differs from the
    remembered role, the user just switched role (switch-role issues a new token),
    possibly on another server process, so the remembered answer is not used.
    fresh: always read the database (skip the remembered answer).
    """
    now = time.time()
    cached = _cache.get(username)
    if (not fresh and cached and cached[0] > now
            and (token_role is None or cached[1]["role"] == token_role)):
        return cached[1]

    # Read-write (main) database: the read port can be a copy that is slightly
    # behind, which right after a role change would return the old role.
    async with db.get_async_db("rw") as conn:
        user = await conn.fetchrow(
            """
            SELECT u.id, u.access, u.is_active, r.name AS role
            FROM risk_user_table u
            LEFT JOIN model_has_roles m ON m.model_id = u.id AND m.model_type = $2
            LEFT JOIN roles r ON r.id = m.role_id
            WHERE u.username = $1
            LIMIT 1
            """,
            username, MODEL_TYPE
        )

        if not user:
            access = {"role": None, "is_admin": False, "is_developer": False, "inactive": False, "permissions": set()}
        elif not user["is_active"]:
            access = {"role": user["role"], "is_admin": False, "is_developer": False, "inactive": True, "permissions": set()}
        elif user["role"] == ADMIN_ROLE:
            rows = await conn.fetch("SELECT name FROM permissions")
            access = {"role": ADMIN_ROLE, "is_admin": True, "permissions": {r["name"] for r in rows}}
        else:
            rows = await conn.fetch(
                """
                SELECT p.name
                FROM permissions p
                WHERE p.id IN (
                    SELECT rhp.permission_id
                    FROM role_has_permissions rhp
                    JOIN model_has_roles m ON m.role_id = rhp.role_id
                    WHERE m.model_id = $1 AND m.model_type = $2
                    UNION
                    SELECT mhp.permission_id
                    FROM model_has_permissions mhp
                    WHERE mhp.model_id = $1 AND mhp.model_type = $2
                )
                """,
                user["id"], MODEL_TYPE
            )
            access = {"role": user["role"], "is_admin": False, "permissions": {r["name"] for r in rows}}

        if user and user["is_active"]:
            # Developer access (risk_user_table.access) lets a user switch their own role
            access["is_developer"] = user["access"] == DEVELOPER_ACCESS
            access["inactive"] = False

    _cache[username] = (now + CACHE_SECONDS, access)
    return access


def has_permission(access: dict, *names: str) -> bool:
    return access["is_admin"] or bool(access["permissions"] & set(names))


# Route dependency: the caller must have at least ONE of the given permissions.
# allow_developer: users with Developer access are also let through.
# Returns the decoded token plus "role", "is_admin", "is_developer" and "permissions".
#   access: dict = Depends(require_permission("history-page"))
def require_permission(*names: str, allow_developer: bool = False):
    async def dependency(auth: HTTPAuthorizationCredentials = Security(bearer)) -> dict:
        decoded_data = decode_access_token(auth.credentials)
        access = await get_user_access(decoded_data["sub"], decoded_data.get("role"))

        if access["inactive"]:
            print(f"[permissions] refused '{decoded_data['sub']}': account is inactive")
            raise AccountInactive()

        if not (has_permission(access, *names) or (allow_developer and access["is_developer"])):
            # logged so a refusal can be explained (which role, which permission was missing)
            print(f"[permissions] refused '{decoded_data['sub']}': needs one of {list(names)}"
                  f"{' or Developer access' if allow_developer else ''}, "
                  f"role in database '{access['role']}', role in token '{decoded_data.get('role')}', "
                  f"has {sorted(access['permissions'])}")
            raise PermissionDenied()

        return {**decoded_data, **access}

    return dependency


# Route dependency for routes that need no permission (own profile, own
# password, activity log): a valid token AND an active account.
#   access: dict = Depends(require_login())
def require_login():
    async def dependency(auth: HTTPAuthorizationCredentials = Security(bearer)) -> dict:
        decoded_data = decode_access_token(auth.credentials)
        access = await get_user_access(decoded_data["sub"], decoded_data.get("role"))

        if access["inactive"]:
            print(f"[permissions] refused '{decoded_data['sub']}': account is inactive")
            raise AccountInactive()

        return {**decoded_data, **access}

    return dependency


# Route dependency: the caller must have Developer access in the database
# (not in the token, which keeps the old value until it expires).
#   access: dict = Depends(require_developer())
def require_developer():
    async def dependency(auth: HTTPAuthorizationCredentials = Security(bearer)) -> dict:
        decoded_data = decode_access_token(auth.credentials)
        access = await get_user_access(decoded_data["sub"], fresh=True)

        if access["inactive"]:
            print(f"[permissions] refused '{decoded_data['sub']}': account is inactive")
            raise AccountInactive()

        if not access["is_developer"]:
            print(f"[permissions] refused '{decoded_data['sub']}': needs Developer access")
            raise PermissionDenied()

        return {**decoded_data, **access}

    return dependency


# Startup check: a role that has users but no permissions would lose all access
async def warn_roles_without_permissions():
    try:
        async with db.get_async_db("r") as conn:
            rows = await conn.fetch(
                """
                SELECT r.name, COUNT(DISTINCT m.model_id) AS users
                FROM roles r
                JOIN model_has_roles m ON m.role_id = r.id
                WHERE r.name <> $1
                  AND NOT EXISTS (SELECT 1 FROM role_has_permissions p WHERE p.role_id = r.id)
                GROUP BY r.name
                ORDER BY r.name
                """,
                ADMIN_ROLE
            )
        for row in rows:
            print(f"⚠️ [permissions] role '{row['name']}' has {row['users']} user(s) but no permissions: "
                  f"they cannot use any protected feature. Assign permissions in Role Management.")
    except Exception as e:
        print(f"⚠️ [permissions] startup check failed: {repr(e)}")
