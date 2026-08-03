# ==============================
# Third-Party Libraries
# ==============================
from fastapi import APIRouter, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# ==============================
# Internal Modules
# ==============================
from services.Historypage import get_grouped_history, individual_delete_history, bulk_delete_history, get_history_data

from helper.models import BulkDeleteRequest
from helper.tokenManagement import decode_access_token


# Bearer token authentication
bearer = HTTPBearer()

router = APIRouter()

# get history
@router.get("/getHistory/")
async def historydata(auth: HTTPAuthorizationCredentials = Security(bearer)):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username
        username = decoded_data["sub"]
        # print(username)
        
        
        res = get_grouped_history(username)

        if any(res.values()):  # At least one category has data
            return {
                "success": True,
                "message": "Generate response successfully",
                "status": 200,
                "data": res
            }

        return {
            "success": True,
            "message": "No history was recorded",
            "status": 200,
            "data": {
                "today": [],
                "yesterday": [],
                "last7Days": [],
                "older": []
            }
        }

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# delete history individual
@router.delete("/deleteHistoryIndividual/")
async def DeleteHistoryIndividual(question_id: str, auth: HTTPAuthorizationCredentials = Security(bearer)):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username
        username = decoded_data["sub"]
        
        result = individual_delete_history(question_id, username)

        if result:
            return {"success": True, "message": "History entry deleted"}
        else:
            raise HTTPException(
                status_code=404,
                detail="History entry not found or does not belong to user"
            )

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/deleteHistoryBulk/")
async def delete_history_bulk(
    request: BulkDeleteRequest,
    auth: HTTPAuthorizationCredentials = Security(bearer)
):
    try:
        token = auth.credentials
        decoded_data = decode_access_token(token)
        username = decoded_data["sub"]

        deleted_count = bulk_delete_history(request.question_ids, username)

        if deleted_count > 0:
            return {"success": True, "message": f"Deleted {deleted_count} entries."}
        else:
            return {"success": False, "message": "No matching history entries found."}
    
    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# get history detail
@router.get("/getHistoryDetails/")
async def Get_History_Detail(question_id: str, auth: HTTPAuthorizationCredentials = Security(bearer)):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username
        username = decoded_data["sub"]
        
        result = get_history_data(question_id, username)

        if result:
            return {
                "success": True,
                "pm_data": result["pm_data"],
                "sc_data": result["sc_data"],
                "add_info": result["add_info"],
                "ll_data": result["ll_data"],
                "issue_data": result["issue_data"]
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