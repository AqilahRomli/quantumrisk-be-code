# ==============================
# Third-Party Libraries
# ==============================
from fastapi import APIRouter, Request, HTTPException, Header, Security, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# ==============================
# Internal Modules
# ==============================
from helper.models import User, RegisterUsers, UpdateRole, UpdateUserStatus, AdminChangePassword, UserLog, UpdateRoleDetail, CreateRoleDetail, DeleteRoleDetail, UpdateUserAccess, CreatePermission, DeletePermission
from helper.tokenManagement import decode_access_token
from helper.permissions import require_permission, require_developer, require_login
from core.config import settings

from services.getUserAuth import register_users, login_EntraID, login_user, get_user_detail, update_user_status, Admin_change_password, change_own_role, log_switch_other_refused, get_roles, get_permissions, user_log_event, update_role_detail, create_role_detail, delete_role_detail, get_users_by_role, get_all_user_details_v2, get_user_with_permissions, update_user_access, create_permission, delete_permission


# Bearer token authentication
bearer = HTTPBearer()

router = APIRouter()

# Username + password login is switched on by PASSWORD_LOGIN_ENABLED in the env
# file (local only). Everywhere else users must sign in with Entra ID.
def check_password_login_enabled():
    if not settings.PASSWORD_LOGIN_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Username and password login is disabled. Please sign in with Entra ID."
        )

#==================== User Login ====================
# Email Password Login
@router.post("/login/")
async def login(user: User):
    check_password_login_enabled()
    return login_user(user.username, user.password)

# EntraID Login
@router.post("/loginEntraID/")
async def login(request: Request, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    id_token = authorization.split(" ", 1)[1]
    # Try to get the real client IP
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        user_ip = forwarded_for.split(",")[0].strip()  # first IP is usually the client
    else:
        user_ip = request.client.host
    return login_EntraID(id_token, user_ip)
#====================================================================================

#===================== User Management ====================
# Admin Page - register users: the individual form sends a list of one,
# bulk register sends the rows from the uploaded Excel (at most 500).
# Returns one result per user; one bad row does not stop the others.
@router.post("/register/")
async def register(request: Request, payload: RegisterUsers, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("user-manage.add"))):
    # Requestor is taken from the token, not from the request body
    username_requestor = access["sub"]

    # Try to get the real client IP
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        requestor_ip = forwarded_for.split(",")[0].strip()  # first IP is usually the client
    else:
        requestor_ip = request.client.host

    users = [user.model_dump() for user in payload.users]
    return await run_in_threadpool(register_users, username_requestor, requestor_ip, users)

# Admin Page - user list (User Management table)
@router.get("/getAllUser2/")
async def Get_All_User_2(auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("user-list.view"))):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)

        result = get_all_user_details_v2()

        return {
            "success": True,
            "data": result
        }

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Admin Page - activate / deactivate a user (users are never deleted)
@router.post("/updateUserStatus/")
async def Update_User_Status(request: Request, payload: UpdateUserStatus, access: dict = Depends(require_permission("user-manage.update"))):
    forwarded_for = request.headers.get("X-Forwarded-For")
    requestor_ip = forwarded_for.split(",")[0].strip() if forwarded_for else request.client.host
    return await run_in_threadpool(update_user_status, access["sub"], requestor_ip, payload.user_id, payload.is_active)

# Admin Page - post change password
@router.post("/adminchangePassword/")
async def Admin_Change_Password(userDetail: AdminChangePassword, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("user-manage.update"))):
    try:
        check_password_login_enabled()
        token = auth.credentials
        decoded_data = decode_access_token(token)

        result = Admin_change_password(userDetail.username, userDetail.id, userDetail.newpassword)

        if result:
            return {
                "success": True,
                "message": "Password changed successfully"
            }
        else:
            raise HTTPException(
                status_code=404,
                detail="User not found or password incorrect"
            )

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Header - Developer switches their own role
@router.post("/switchRole/")
async def Switch_Role(request: Request, userRole: UpdateRole, access: dict = Depends(require_developer())):
    try:
        forwarded_for = request.headers.get("X-Forwarded-For")
        requestor_ip = forwarded_for.split(",")[0].strip() if forwarded_for else request.client.host

        # ✅ Only their own account (the body names the user, so check it against the token)
        if userRole.username != access["sub"]:
            await run_in_threadpool(log_switch_other_refused, access["sub"], requestor_ip, userRole.username)
            raise HTTPException(
                status_code=403,
                detail="You can only switch your own role."
            )

        result = await run_in_threadpool(change_own_role, userRole.username, userRole.id, userRole.role, requestor_ip)

        if result:
            return result
        else:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Profile Page -  get user detail [Individual]
@router.get("/getUserDetails/")
async def Get_User_Detail(user_id: str, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_login())):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username
        username = decoded_data["sub"]
        
        result = get_user_detail(user_id, username)

        if result:
            return {
                "success": True,
                "data": result
            }
        else:
            raise HTTPException(
                status_code=404,
                detail="No history data found for the given question ID and user."
            )

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Admin Page - get All Roles
# Also needed by the Register form (user-manage.add) and, for Developers, the Switch Role list
@router.get("/getAllRoles/")
async def Get_All_User(auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("role-manage.view", "user-manage.update", "user-manage.add", allow_developer=True))):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username
        username = decoded_data["sub"]

        result = get_roles()

        if result:
            return {
                "success": True,
                "roles": result
            }
        else:
            raise HTTPException(
                status_code=404,
                detail="No Roles data found."
            )

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/getAllPermissions/")
async def Get_All_Permissions(auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("permission-manage.view", "role-manage.view", "user-manage.update"))):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username
        username = decoded_data["sub"]

        result = get_permissions()

        if result:
            return {
                "success": True,
                "permissions": result
            }
        else:
            raise HTTPException(
                status_code=404,
                detail="No Permissions data found."
            )

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Permission Management - add a permission (a name that code can then check)
@router.post("/createPermission/")
async def Create_Permission(request: Request, payload: CreatePermission, access: dict = Depends(require_permission("permission-manage.add"))):
    forwarded_for = request.headers.get("X-Forwarded-For")
    requestor_ip = forwarded_for.split(",")[0].strip() if forwarded_for else request.client.host
    return await run_in_threadpool(create_permission, access["sub"], requestor_ip, payload.name, payload.group, payload.description)


# Permission Management - delete a permission no role or user has
@router.post("/deletePermission/")
async def Delete_Permission(request: Request, payload: DeletePermission, access: dict = Depends(require_permission("permission-manage.add"))):
    forwarded_for = request.headers.get("X-Forwarded-For")
    requestor_ip = forwarded_for.split(",")[0].strip() if forwarded_for else request.client.host
    return await run_in_threadpool(delete_permission, access["sub"], requestor_ip, payload.permission_id)


@router.post("/updateRoleDetail/")
async def Update_Role_Detail(role_detail: UpdateRoleDetail, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("role-manage.view"))):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)

        result = update_role_detail(
            role_detail.role_id,
            role_detail.role_name,
            role_detail.permission_ids
        )

        return result

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/createRole/")
async def Create_Role(role_detail: CreateRoleDetail, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("role-manage.view"))):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)

        result = create_role_detail(
            role_detail.role_name,
            role_detail.permission_ids
        )

        return result

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deleteRole/")
async def Delete_Role(role_detail: DeleteRoleDetail, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("role-manage.view"))):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)

        result = delete_role_detail(role_detail.role_id)

        return result

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/getUsersByRole/")
async def Get_Users_By_Role(role_id: int, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("user-list.view"))):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)

        result = get_users_by_role(role_id)

        if result:
            return {
                "success": True,
                "users": result
            }

        return {
            "success": True,
            "users": []
        }

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/getUserPermissionsDetail/")
async def Get_User_Permissions_Detail(user_id: int, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("user-list.view"))):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)

        return get_user_with_permissions(user_id)

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Save role + extra permissions in one go (User Management drawer)
@router.post("/updateUserAccess/")
async def Update_User_Access(request: Request, payload: UpdateUserAccess, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("user-manage.update"))):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Try to get the real client IP
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            requestor_ip = forwarded_for.split(",")[0].strip()  # first IP is usually the client
        else:
            requestor_ip = request.client.host

        return update_user_access(decoded_data["sub"], requestor_ip, payload.user_id, payload.role_id, payload.permission_ids)

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


#=================== Event log ================================
@router.post("/activitylog/")
async def user_activity_log(request: Request, user: UserLog, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_login())):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)
        
        # Try to get the real client IP
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            user_ip = forwarded_for.split(",")[0].strip()  # first IP is usually the client
        else:
            user_ip = request.client.host

        result = user_log_event(user_ip, user.username, user.activity, user.status)

        if result:
            return {
                "success": True,
                "message": "User log successfully insert"
            }
        else:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


