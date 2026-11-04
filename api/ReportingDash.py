# ==============================
# Third-Party Libraries
# ==============================
from fastapi import APIRouter, HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# ==============================
# Internal Modules
# ==============================
from services.managementReport import count_registered_user, get_Risk_LL_Issues, get_ytd_User_Activity, get_User_Activity_monthly, get_proposal_created_monthly, get_top10_Keywords, get_user_per_department, get_activity_per_user, get_activity_per_month_detail, get_proposal_list_per_status, get_proposal_per_month, list_risk, get_user_login_track, list_lesson_learn, list_Issues, get_registered_non_registered

from helper.tokenManagement import decode_access_token
from helper.permissions import require_permission


# Bearer token authentication
bearer = HTTPBearer()

router = APIRouter()

# Management Page - Get Number of Registered User
@router.get("/count-registered-user/")
async def get_number_user( 
    auth: HTTPAuthorizationCredentials = Security(bearer),
    access: dict = Depends(require_permission("general-reporting.view"))
):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)

        result = await count_registered_user()

        # If result is a dictionary and has a 'success' key,x treat it as error
        if isinstance(result, dict) and not result.get("success", True):
            raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

        # Otherwise, return result (even if empty list)
        return result

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Management Page - get total registered risk
@router.get("/get-risk-issues-ll/")
async def get_number_registered_risk_issues_ll( 
    auth: HTTPAuthorizationCredentials = Security(bearer),
    access: dict = Depends(require_permission("general-reporting.view"))
):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)

        result = await get_Risk_LL_Issues()

        # If result is a dictionary and has a 'success' key,x treat it as error
        if isinstance(result, dict) and not result.get("success", True):
            raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

        # Otherwise, return result (even if empty list)
        return result

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# Management Page - get year to date user activity
@router.get("/get-ytd-user-activity/")
async def get_yeartodate_user_activity( 
    auth: HTTPAuthorizationCredentials = Security(bearer),
    access: dict = Depends(require_permission("general-reporting.view"))
):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)

        result = await get_ytd_User_Activity()

        # If result is a dictionary and has a 'success' key,x treat it as error
        if isinstance(result, dict) and not result.get("success", True):
            raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

        # Otherwise, return result (even if empty list)
        return result

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# get user activity Monthly
@router.get("/get-user-activity-monthly/")
async def get_monthly_user_activity( 
    auth: HTTPAuthorizationCredentials = Security(bearer),
    access: dict = Depends(require_permission("general-reporting.view"))
):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)

        result = await get_User_Activity_monthly()

        # If result is a dictionary and has a 'success' key,x treat it as error
        if isinstance(result, dict) and not result.get("success", True):
            raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

        # Otherwise, return result (even if empty list)
        return result

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# get proposal created Monthly
@router.get("/get-proposal-created-monthly/")
async def get_monthly_proposal_created( 
    auth: HTTPAuthorizationCredentials = Security(bearer),
    access: dict = Depends(require_permission("proposal-reporting.view"))
):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)

        result = await get_proposal_created_monthly()

        # If result is a dictionary and has a 'success' key,x treat it as error
        if isinstance(result, dict) and not result.get("success", True):
            raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

        # Otherwise, return result (even if empty list)
        return result

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
  
# get top 10 Keyword
@router.get("/get-top-keywords/")
async def get_monthly_proposal_created( 
    auth: HTTPAuthorizationCredentials = Security(bearer),
    access: dict = Depends(require_permission("general-reporting.view"))
):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)

        result = await get_top10_Keywords()

        # If result is a dictionary and has a 'success' key,x treat it as error
        if isinstance(result, dict) and not result.get("success", True):
            raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

        # Otherwise, return result (even if empty list)
        return result

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
# Management Page - get Registered user detail
@router.get("/getUserperDepartment/")
async def Get_User_department(user_role:str, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("general-reporting.view"))):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username

        result = await get_user_per_department(user_role)

        return {
                "success": True,
                "data": result
            }

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Management Page - get activity per user detail
@router.get("/getActivityperUser/")
async def Get_Activity_per_User(user_role:str, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("general-reporting.view"))):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username

        result = await get_activity_per_user(user_role)

        return {
                "success": True,
                "data": result
            }

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Management Page - get activity per month
@router.get("/getActivityUserpermonth/")
async def Get_Activity_per_Month(user_role:str, month:str, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("general-reporting.view"))):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username

        result = await get_activity_per_month_detail(user_role, month)
        return {
                "success": True,
                "data": result
            }

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Management Page - get proposal per status
@router.get("/getproposalperstatus/")
async def Get_Proposal_Per_Status(status:str, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("proposal-reporting.view"))):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username

        result = await get_proposal_list_per_status(status)

        return {
            "success": True,
            "data": result
        }

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Management Page - get proposal per month
@router.get("/getproposalpermonth/")
async def Get_Proposal_per_Month(status:str, month:str, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("proposal-reporting.view"))):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username

        result = await get_proposal_per_month(status, month)
        return {
            "success": True,
            "data": result
        }

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Get Number of Risk PM+SC
@router.get("/list_all_risk/")
async def get_all_risk_list( 
    auth: HTTPAuthorizationCredentials = Security(bearer),
    access: dict = Depends(require_permission("general-reporting.view"))
):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)

        result = await list_risk()

        # If result is a dictionary and has a 'success' key,x treat it as error
        if isinstance(result, dict) and not result.get("success", True):
            raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

        # Otherwise, return result (even if empty list)
        return result

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# Management Page - get Registered user detail
@router.get("/getUserloginTrack/")
async def Get_User_login_track(auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("general-reporting.view"))):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username

        result = await get_user_login_track()

        return {
                "success": True,
                "data": result
            }

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Get Number of lesson learn
@router.get("/list_lesson_learn/")
async def get_all_lesson_learn( 
    auth: HTTPAuthorizationCredentials = Security(bearer),
    access: dict = Depends(require_permission("general-reporting.view"))
):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)

        result = await list_lesson_learn()

        # If result is a dictionary and has a 'success' key,x treat it as error
        if isinstance(result, dict) and not result.get("success", True):
            raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

        # Otherwise, return result (even if empty list)
        return result

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Get Number of Issues
@router.get("/list_Issues/")
async def get_all_issues( 
    auth: HTTPAuthorizationCredentials = Security(bearer),
    access: dict = Depends(require_permission("general-reporting.view"))
):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)

        result = await list_Issues()

        # If result is a dictionary and has a 'success' key,x treat it as error
        if isinstance(result, dict) and not result.get("success", True):
            raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

        # Otherwise, return result (even if empty list)
        return result

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Management Page - list Non Register and Registered Member
@router.get("/getRegisteredNonRegistered/")
async def Get_registered_non_registered(department:str, type:str, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("general-reporting.view"))):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)
        # Now you have access to the decoded user data, like their username
        
        result = await get_registered_non_registered(department, type)
        return {
                "success": True,
                "data": result
            }
    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 