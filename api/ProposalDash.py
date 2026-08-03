# ==============================
# Standard Library
# ==============================
from typing import List, Optional

# ==============================
# Third-Party Libraries
# ==============================
from fastapi import APIRouter, HTTPException, Query, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# ==============================
# Internal Modules
# ==============================
from services.registerRisk import register_risk, proposal_list, proposal_list_Admin, proposal_summary_with_list, proposal_details, update_proposal, Post_submitRisk, pending_proposal, delete_proposal
from services.getSCAdmindata import count_proposal, count_risk_project, count_proposal_perUser, topten_sc_user, list_sc_risk

from helper.models import RiskRegistrationRequest, RiskUpdateRequest
from helper.tokenManagement import decode_access_token

# Bearer token authentication
bearer = HTTPBearer()

router = APIRouter()

#===================== Create and Manage Proposal ==============================
# Register new risk
@router.post("/risk-registration/") #CREATE NEW PROPOSAL
async def risk_data_registration(
    register: RiskRegistrationRequest,
    auth: HTTPAuthorizationCredentials = Security(bearer)
):
    try:
        # Verify JWT token
        token = auth.credentials
        decoded_data = decode_access_token(token)
        username = decoded_data["sub"]  # Extract username from token

        # Call upload_data function from preferredData.py
        result = await register_risk(register.customer, register.projectName, register.risk_detail, username)

        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=500, detail=result["message"])

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
#Get proposal Detail
@router.get("/proposal-details/")
async def get_proposal_details( 
    proposalId: str,
    auth: HTTPAuthorizationCredentials = Security(bearer)
):
    try:
        # Verify JWT token
        token = auth.credentials
        decoded_data = decode_access_token(token)
        username = decoded_data["sub"]  # Extract username from token

        # Call upload_data function from preferredData.py
        result = await proposal_details(proposalId)

        if result:
            return result
        else:
            raise HTTPException(status_code=500, detail=result["message"])

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Update Proposal Detail
@router.post("/update-proposal/")
async def update_proposal_details(
    updateproposal: RiskUpdateRequest,
    auth: HTTPAuthorizationCredentials = Security(bearer)
):
    try:
        # Verify JWT token
        token = auth.credentials
        decoded_data = decode_access_token(token)
        username = decoded_data["sub"]  # Extract username from token

        # Call upload_data function from preferredData.py
        result = await update_proposal(updateproposal.proposalId, updateproposal.customer, updateproposal.projectName, updateproposal.risk_detail, username)

        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=500, detail=result["message"])

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

#Delete Draft Proposal
@router.delete("/deleteproposal/")
async def DeleteProposal(proposalId: str, auth: HTTPAuthorizationCredentials = Security(bearer)):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username
        username = decoded_data["sub"]
        
        result = await delete_proposal(proposalId, username)

        if result["success"]:
            return result
        else:
            raise HTTPException(
                status_code=500,
                detail=result["message"]
            )

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

# Submit Risk
@router.post("/Submit-Risk/") #SUBMIT PROPOSAL
async def submit_Risk(
    updateproposal: RiskUpdateRequest,
    auth: HTTPAuthorizationCredentials = Security(bearer)
):
    try:
        # Verify JWT token
        token = auth.credentials
        decoded_data = decode_access_token(token)
        username = decoded_data["sub"]  # Extract username from token

        # Call upload_data function from preferredData.py
        result = await Post_submitRisk(updateproposal.proposalId, updateproposal.customer, updateproposal.projectName, updateproposal.risk_detail, username)

        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=500, detail=result["message"])

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


#===================== Proposal Dashboard Reporting ==============================
# Proposal List - [Non Admin]
@router.get("/proposal-list/")
async def get_proposal_list(
    auth: HTTPAuthorizationCredentials = Security(bearer)
):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)
        username = decoded_data["sub"]

        result = await proposal_list(username)

        # If result is a dictionary and has a 'success' key, treat it as error
        if isinstance(result, dict) and not result.get("success", True):
            raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

        # Otherwise, return result (even if empty list)
        return result

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Proposal List - Not use
@router.get("/proposal-list-Admin/")
async def get_proposal_list_Admin(
    auth: HTTPAuthorizationCredentials = Security(bearer),
    status: Optional[str] = Query(None, description="Filter by status (Draft or Complete)"),
    created_by: Optional[List[str]] = Query(None, description="Filter by one or more creators")
):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)
        username = decoded_data["sub"]

        result = await proposal_list_Admin(status=status, created_by=created_by)

        # If result is a dictionary and has a 'success' key, treat it as error
        if isinstance(result, dict) and not result.get("success", True):
            raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

        # Otherwise, return result (even if empty list)
        return result

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Proposal List - got top User List - can be filter base status and top bar chart
@router.get("/top-user-list-Admin/")
async def get_top_user_list_Admin(
    auth: HTTPAuthorizationCredentials = Security(bearer),
    status: Optional[str] = Query(None, description="Filter by proposal status"),
    created_by: Optional[List[str]] = Query(None, description="Filter by one or more creators")
):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)
        username = decoded_data["sub"]

        result = await proposal_summary_with_list(created_by=created_by, status=status)

        # If result is a dictionary and has a 'success' key, treat it as error
        if isinstance(result, dict) and not result.get("success", True):
            raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

        # Otherwise, return result (even if empty list)
        return result

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Get Number of Proposal Pending
@router.get("/proposal-pending-count/")
async def get_number_proposal_pending( 
    auth: HTTPAuthorizationCredentials = Security(bearer)
):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)
        username = decoded_data["sub"]

        result = await pending_proposal(username)

        # If result is a dictionary and has a 'success' key, treat it as error
        if isinstance(result, dict) and not result.get("success", True):
            raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

        # Otherwise, return result (even if empty list)
        return result

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Get Number of Proposal
@router.get("/proposal-count/")
async def get_number_proposal( 
    auth: HTTPAuthorizationCredentials = Security(bearer)
):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)
        username = decoded_data["sub"]

        result = await count_proposal()

        # If result is a dictionary and has a 'success' key,x treat it as error
        if isinstance(result, dict) and not result.get("success", True):
            raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

        # Otherwise, return result (even if empty list)
        return result

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Get Number of Risk and Project
@router.get("/project-risk-count/")
async def get_number_risk_project( 
    auth: HTTPAuthorizationCredentials = Security(bearer)
):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)
        username = decoded_data["sub"]

        result = await count_risk_project()

        # If result is a dictionary and has a 'success' key, treat it as error
        if isinstance(result, dict) and not result.get("success", True):
            raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

        # Otherwise, return result (even if empty list)
        return result

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

# Get Number of Proposal
@router.get("/list-sc_risk/")
async def get_sc_risk_list( 
    auth: HTTPAuthorizationCredentials = Security(bearer)
):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)

        result = await list_sc_risk()

        # If result is a dictionary and has a 'success' key,x treat it as error
        if isinstance(result, dict) and not result.get("success", True):
            raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

        # Otherwise, return result (even if empty list)
        return result

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Get Number of Complete Proposal per User
@router.get("/complete-proposal-perUser/")
async def get_number_complete_proposal_perUser( 
    auth: HTTPAuthorizationCredentials = Security(bearer)
):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)
        username = decoded_data["sub"]

        result = await count_proposal_perUser()

        # If result is a dictionary and has a 'success' key,x treat it as error
        if isinstance(result, dict) and not result.get("success", True):
            raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

        # Otherwise, return result (even if empty list)
        return result

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Get TOP 10 SC user - for bar chart
@router.get("/top-completed-proposal/")
async def get_top_completed_proposal( 
    auth: HTTPAuthorizationCredentials = Security(bearer)
):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)
        username = decoded_data["sub"]

        result = await topten_sc_user()

        # If result is a dictionary and has a 'success' key,x treat it as error
        if isinstance(result, dict) and not result.get("success", True):
            raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

        # Otherwise, return result (even if empty list)
        return result

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

