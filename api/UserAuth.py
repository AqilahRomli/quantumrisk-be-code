# ==============================
# Third-Party Libraries
# ==============================
from fastapi import APIRouter, Request, HTTPException, Header, Security, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# ==============================
# Internal Modules
# ==============================
from helper.models import User, RegisterUser, UserPassword, UpdateRole, DeleteUser, AdminChangePassword, UserLog
from helper.tokenManagement import decode_access_token

from services.getUserAuth import register_user, login_EntraID, login_user, get_user_detail, change_password, get_all_user, update_user_role, remove_user, Admin_change_password, change_own_role, bulk_register_process, get_roles, get_permissions, user_log_event


# Bearer token authentication
bearer = HTTPBearer()

router = APIRouter()

#==================== User Login ====================
# Email Password Login
@router.post("/login/")
async def login(user: User):
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
# Admin Page - user registration Individual
@router.post("/register/") 
async def register(request: Request, user: RegisterUser):
    requestor_ip = request.client.host
    return register_user(user.username_requestor, requestor_ip, user.fullname, user.username, user.email, user.staffId, user.division, user.user_role, user.user_access)

# Admin Page - Bulk User Registration 
@router.post("/bulk_register/")
async def bulk_register(
    request: Request,
    file: UploadFile = File(...),
    username_requestor: str = Form(...) 
):
    requestor_ip = request.client.host

    return bulk_register_process(file, username_requestor, requestor_ip)

# Admin Page - get All user detail
@router.get("/getAllUser/")
async def Get_All_User(auth: HTTPAuthorizationCredentials = Security(bearer)):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username
        username = decoded_data["sub"]
        role = decoded_data["role"]

        # ✅ Check if user is admin
        if role != "Admin":
            raise HTTPException(
                status_code=403,
                detail="Access denied. Admins only."
            )
        
        result = get_all_user()

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

# Admin Page - post update User Role
@router.post("/updateRole/")
async def Update_User_Role(request: Request, userRole: UpdateRole, auth: HTTPAuthorizationCredentials = Security(bearer)):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)
        role = decoded_data["role"]

        # ✅ Check if user is admin
        if role != "Admin":
            raise HTTPException(
                status_code=403,
                detail="Access denied. Admins only."
            )
        
        # Try to get the real client IP
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            requestor_ip = forwarded_for.split(",")[0].strip()  # first IP is usually the client
        else:
            requestor_ip = request.client.host

        result = update_user_role(requestor_ip, userRole.username_requestor, userRole.username, userRole.id, userRole.role)

        if result:
            return {
                "success": True,
                "message": "User Role successfully Update"
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

# Admin Page - post remove user
@router.post("/removeUser/")
async def delete_User(RemoveUser: DeleteUser, auth: HTTPAuthorizationCredentials = Security(bearer)):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)
        role = decoded_data["role"]

        # ✅ Check if user is admin
        if role != "Admin":
            raise HTTPException(
                status_code=403,
                detail="Access denied. Admins only."
            )

        result = remove_user(RemoveUser.username, RemoveUser.id) #create function to delete user

        if result:
            return {
                "success": True,
                "message": "User successfully deleted"
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

# Admin Page - post change password
@router.post("/adminchangePassword/")
async def Admin_Change_Password(userDetail: AdminChangePassword, auth: HTTPAuthorizationCredentials = Security(bearer)):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)
        role = decoded_data["role"]

        # ✅ Check if user is admin
        if role != "Admin":
            raise HTTPException(
                status_code=403,
                detail="Access denied. Admins only."
            )

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

# Admin Page - post update User Role
@router.post("/switchRole/")
async def Switch_Role(userRole: UpdateRole, auth: HTTPAuthorizationCredentials = Security(bearer)):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)
        access = decoded_data["access"]

        # ✅ Check if user is admin
        if access != "Developer":
            raise HTTPException(
                status_code=403,
                detail="Access denied. developer only."
            )

        result = change_own_role(userRole.username, userRole.id, userRole.role)

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
async def Get_User_Detail(user_id: str, auth: HTTPAuthorizationCredentials = Security(bearer)):
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

# Profile Page - User change password
@router.post("/changePassword/")
async def Change_Password(userDetail: UserPassword, auth: HTTPAuthorizationCredentials = Security(bearer)):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)
        username = decoded_data["sub"]

        result = change_password(userDetail.user_id, userDetail.password, userDetail.newpassword, username)

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


# Admin Page - get All Roles
@router.get("/getAllRoles/")
async def Get_All_Roles(auth: HTTPAuthorizationCredentials = Security(bearer)):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username
        username = decoded_data["sub"]
        role = decoded_data["role"]

        # ✅ Check if user is admin
        if role != "Admin":
            raise HTTPException(
                status_code=403,
                detail="Access denied. Admins only."
            )
        
        result = get_roles()

        if result:
            return {
                "success": True,
                "data": result
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

# Admin Page - get All Permissions
@router.get("/getAllPermissions/")
async def Get_All_Permissions(auth: HTTPAuthorizationCredentials = Security(bearer)):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username
        username = decoded_data["sub"]
        role = decoded_data["role"]

        # ✅ Check if user is admin
        if role != "Admin":
            raise HTTPException(
                status_code=403,
                detail="Access denied. Admins only."
            )
        
        result = get_permissions()

        if result:
            return {
                "success": True,
                "data": result
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


#=================== Event log ================================
@router.post("/activitylog/")
async def user_activity_log(request: Request, user: UserLog, auth: HTTPAuthorizationCredentials = Security(bearer)):
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


