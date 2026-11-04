# ==============================
# Standard Library
# ==============================
import json
import asyncio
from typing import List
from datetime import datetime

# ==============================
# Third-Party Libraries
# ==============================
from fastapi import APIRouter, HTTPException, Security, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# ==============================
# Internal Modules
# ==============================
from helper.models import Item, getDataItem, Details, PMRiskData, SCRiskData, HistoryData, HistoryAddInfoData
from getDataPM import query_pm_database
from getDataSC import query_sc_database
from getDataIssue import query_issue_database
from getDataLessonLearn import query_ll_database
from services.getDataAdd import additional_Info
from services.pushPreferredData import push_PM_preferred_risk, push_SC_preferred_risk
from services.pushHistorySearching import push_history_data, push_history_addinfo_data, generate_question_id
from services.managementReport import get_top10_Keywords
from instruction import create_question_instruction

from helper.tokenManagement import decode_access_token
from helper.permissions import require_permission

# Bearer token authentication
bearer = HTTPBearer()

router = APIRouter()


#------------------ Risk Suggestion Query --------------------------------
# Most searched keywords across the system, shown on the Ask Me page before a search.
# Same query as the dashboard's /get-top-keywords/, but needs only query-page.
@router.get("/getPopularKeywords/")
async def popular_keywords(auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("query-page"))):
    try:
        result = await get_top10_Keywords()

        # get_top10_Keywords returns {"success": False, ...} on a database error
        if isinstance(result, dict) and not result.get("success", True):
            raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

        return {"success": True, "message": "Generate response successfully", "status": 200, "data": result}

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

#Generate question_id
@router.post("/generateQuestionId/")
async def query_item(item: Item, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("query-page"))):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username
        username = decoded_data["sub"]

        start_time = datetime.now()  # or datetime.now() if you prefer local time
        
        # return 404 when question null
        if item.question=="":
            raise HTTPException(status_code=400, detail="Input value cannot be empty") 

        question_id = await generate_question_id()  # Generate unique question_id

        # Combine both results into a single dictionary
        res = {
            "question_id": question_id,
            "timestamp": start_time,
        }

        # return response
        if res:
            return {"success": True, "message": "Generate response successfully", "status":200, "data": res}
        return {"success": False, "message": "Fail to get response", "status":404, "data": {}}
    
    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# get PM data for query
@router.post("/getPMData/")
async def query_item(item: getDataItem, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("query-page"))):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username
        username = decoded_data["sub"]
        
        # return 404 when question null
        if item.question=="":
            raise HTTPException(status_code=400, detail="Input value cannot be empty") 

        #test new code combine pm and sc
        pm_task = asyncio.create_task(query_pm_database(item.question))

        pm_result = await asyncio.gather(
            pm_task
        )

        pm_json = json.loads(pm_result[0]) 
        keywords = pm_json.get("keywords", [])

        # Log history for each pm_result entry
        for pm in pm_json.get("data", []):
            await push_history_data([
                HistoryData(
                    username= username,
                    ques_id= item.question_id,
                    question=item.question,
                    risk_id=pm.get("risk_id"),
                    stakeholder=pm.get("stakeholder"),
                    timestamp= item.timestamp,
                    keyword= keywords
                )
            ])

        # Combine both results into a single dictionary
        res = {
            "pm_result": pm_json,
        }

        # return response
        if res:
            return {"success": True, "message": "Generate response successfully", "status":200, "data": res}
        return {"success": False, "message": "Fail to get response", "status":404, "data": {}}
    
    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 

# get SC Data for query 
@router.post("/getSCData/")
async def query_item(item: getDataItem, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("query-page"))):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username
        username = decoded_data["sub"]
        
        # return 404 when question null
        if item.question=="":
            raise HTTPException(status_code=400, detail="Input value cannot be empty") 

        #test new code combine pm and sc
        sc_task = asyncio.create_task(query_sc_database(item.question))

        sc_result = await asyncio.gather(
            sc_task
        )
 
        sc_json = json.loads(sc_result[0])
        keywords = sc_json.get("keywords", [])

        # Log history for each sc_result entry
        for sc in sc_json.get("data", []):
            await push_history_data([
                HistoryData(
                    username= username,
                    ques_id= item.question_id,
                    question= item.question,
                    risk_id=sc.get("risk_id"),
                    stakeholder=sc.get("stakeholder"),
                    timestamp= item.timestamp,
                    keyword= keywords
                )
            ])

        # Combine both results into a single dictionary
        res = {
            "sc_result": sc_json
        }

        # return response
        if res:
            return {"success": True, "message": "Generate response successfully", "status":200, "data": res}
        return {"success": False, "message": "Fail to get response", "status":404, "data": {}}
    
    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
  

# get LL Data for query 
@router.post("/getLLData/")
async def query_item(item: getDataItem, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("query-page"))):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username
        username = decoded_data["sub"]
        
        # return 404 when question null
        if item.question=="":
            raise HTTPException(status_code=400, detail="Input value cannot be empty") 

        ll_task = asyncio.create_task(query_ll_database(item.question))

        ll_result = await asyncio.gather(
            ll_task
        )

        ll_json = json.loads(ll_result[0])
        keywords = ll_json.get("keywords", [])

        # Log history for each ll_result entry
        for ll in ll_json.get("data", []):
            await push_history_data([
                HistoryData(
                    username= username,
                    ques_id= item.question_id,
                    question=item.question,
                    risk_id=ll.get("ll_id"),
                    stakeholder="lesson_learn",
                    timestamp= item.timestamp,
                    keyword= keywords
                )
            ])

        # Combine both results into a single dictionary
        res = {
            "ll_result": ll_json
        }

        # return response
        if res:
            return {"success": True, "message": "Generate response successfully", "status":200, "data": res}
        return {"success": False, "message": "Fail to get response", "status":404, "data": {}}
    
    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 

# get Issue Data for query 
@router.post("/getIssueData/")
async def query_item(item: getDataItem, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("query-page"))):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username
        username = decoded_data["sub"]
        
        # return 404 when question null
        if item.question=="":
            raise HTTPException(status_code=400, detail="Input value cannot be empty") 

        issue_task = asyncio.create_task(query_issue_database(item.question))

        issue_result = await asyncio.gather(
            issue_task
        )

        issue_json = json.loads(issue_result[0])
        keywords = issue_json.get("keywords", [])

        # Log history for each ll_result entry
        for issue in issue_json.get("data", []):
            await push_history_data([
                HistoryData(
                    username= username,
                    ques_id= item.question_id,
                    question=item.question,
                    risk_id=issue.get("issue_id"),
                    stakeholder="Issue",
                    timestamp= item.timestamp,
                    keyword= keywords
                )
            ])

        # Combine both results into a single dictionary
        res = {
            "issue_result": issue_json
        }

        # return response
        if res:
            return {"success": True, "message": "Generate response successfully", "status":200, "data": res}
        return {"success": False, "message": "Fail to get response", "status":404, "data": {}}
    
    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# get Additional Data for query
@router.post("/getAddData/")
async def query_item(item: getDataItem, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("query-page"))):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username
        username = decoded_data["sub"]
        
        # return 404 when question null
        if item.question=="":
            raise HTTPException(status_code=400, detail="Input value cannot be empty") 

        addInfo_task = asyncio.create_task(additional_Info(item.question))

        add_info = await asyncio.gather(
            addInfo_task
        )

        add_info_json = json.loads(add_info[0])
        keywords=", ".join(add_info_json.get("keywords", []))

        # Log history for each add_Info
        for addInfo in add_info_json.get("data", []):
            await push_history_addinfo_data([
                HistoryAddInfoData(
                    username=username,
                    ques_id= item.question_id,
                    question=item.question,
                    risk_title=addInfo.get("Risk_Title"),
                    risk_description=addInfo.get("Risk_Description"),
                    risk_category=addInfo.get("Risk_Category"),
                    risk_root_cause=addInfo.get("Risk_Root_Cause"),
                    risk_impact=addInfo.get("Risk_Impact"),
                    risk_mitigation=addInfo.get("Risk_Mitigation"),
                    timestamp= item.timestamp,
                    keyword= keywords
                )
            ])

        # Combine both results into a single dictionary
        res = {
            "add_info": add_info_json
        }

        # return response
        if res:
            return {"success": True, "message": "Generate response successfully", "status":200, "data": res}
        return {"success": False, "message": "Fail to get response", "status":404, "data": {}}
    
    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Push preferred answer to preferred risk table
@router.post("/push-preferred-risk/")
async def upload_risk_data(
    pm_risk_data: List[PMRiskData], 
    sc_risk_data: List[SCRiskData], 
    auth: HTTPAuthorizationCredentials = Security(bearer),
    access: dict = Depends(require_permission("query-page"))
):
    try:
        # Verify JWT token
        token = auth.credentials
        decoded_data = decode_access_token(token)
        username = decoded_data["sub"]  # Extract username from token

        # Upload PM data
        if pm_risk_data:
            pm_result = await push_PM_preferred_risk(pm_risk_data)
            if not pm_result["success"]:
                raise HTTPException(status_code=500, detail=f"PM Risk Upload Failed: {pm_result['message']}")

        # Upload SC data
        if sc_risk_data:
            sc_result = await push_SC_preferred_risk(sc_risk_data)
            if not sc_result["success"]:
                raise HTTPException(status_code=500, detail=f"SC Risk Upload Failed: {sc_result['message']}")

        # If both succeeded
        return {
            "success": True,
            "message": "PM and SC risk data uploaded successfully"
        }

    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


#------------------ Risk Proposal Suggestion --------------------------------
#Generate Question base proposal detail
@router.post("/create-question/")
async def create_question(details: Details, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("proposal-manage.add"))):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username
        username = decoded_data["sub"]

        start_time = datetime.now()  # or datetime.now() if you prefer local time
        
        # return 400 when question null
        if details=="":
            raise HTTPException(status_code=400, detail="Input value cannot be empty") 
        
        # Generate Question
        question = await run_in_threadpool(create_question_instruction, details.projectName, details.vertical, details.projectDesc, details.product)

        # Generate unique question_id
        question_id = await generate_question_id()  

        # Combine both results into a single dictionary
        res = {
            "question": question,
            "question_id": question_id,
            "timestamp": start_time
        }

        # return response
        if res:
            return {"success": True, "message": "Generate response successfully", "status":200, "data": res}
        return {"success": False, "message": "Fail to get response", "status":404, "data": {}}
    
    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# get suggestion when register risk   
@router.post("/getSuggestion/")
async def suggest_query(details: Details, auth: HTTPAuthorizationCredentials = Security(bearer), access: dict = Depends(require_permission("proposal-manage.add"))):
    try:
        # Extract and verify the JWT token from the Authorization header
        token = auth.credentials
        decoded_data = decode_access_token(token)

        # Now you have access to the decoded user data, like their username
        username = decoded_data["sub"]

        start_time = datetime.now()  # or datetime.now() if you prefer local time
        # print(start_time)
        
        # return 400 when question null
        if details=="":
            raise HTTPException(status_code=400, detail="Input value cannot be empty") 
        
        # Generate Question
        question = await run_in_threadpool(create_question_instruction, details.projectName, details.vertical, details.projectDesc, details.product)
        # print(question)

        pm_task = asyncio.create_task(query_pm_database(question))
        sc_task = asyncio.create_task(query_sc_database(question))
        addInfo_task = asyncio.create_task(additional_Info(question))

        pm_result, sc_result, add_info = await asyncio.gather(
            pm_task, sc_task, addInfo_task
        )

        pm_json = json.loads(pm_result) 
        sc_json = json.loads(sc_result)
        add_info_json = json.loads(add_info)

        # Generate unique question_id
        question_id = await generate_question_id()  

        # Log history for each pm_result entry
        for pm in pm_json.get("data", []):
            await push_history_data([
                HistoryData(
                    username=username,
                    ques_id= question_id,
                    question=question,
                    risk_id=pm.get("risk_id"),
                    stakeholder=pm.get("stakeholder"),
                    timestamp= start_time,
                    keyword=", ".join(pm_json.get("keywords", []))
                )
            ])

        # Log history for each sc_result entry
        for sc in sc_json.get("data", []):
            await push_history_data([
                HistoryData(
                    username=username,
                    ques_id= question_id,
                    question=question,
                    risk_id=sc.get("risk_id"),
                    stakeholder=sc.get("stakeholder"),
                    timestamp= start_time,
                    keyword=", ".join(sc_json.get("keywords", []))
                )
            ])
        
        # Log history for each add_Info
        for addInfo in add_info_json.get("data", []):
            await push_history_addinfo_data([
                HistoryAddInfoData(
                    username=username,
                    ques_id= question_id,
                    question=question,
                    risk_title=addInfo.get("Risk_Title"),
                    risk_description=addInfo.get("Risk_Description"),
                    risk_category=addInfo.get("Risk_Category"),
                    risk_root_cause=addInfo.get("Risk_Root_Cause"),
                    risk_impact=addInfo.get("Risk_Impact"),
                    risk_mitigation=addInfo.get("Risk_Mitigation"),
                    timestamp= start_time,
                    keyword=", ".join(add_info_json.get("keywords", []))
                )
            ])

        # Combine both results into a single dictionary
        res = {
            "pm_result": pm_json,
            "sc_result": sc_json,
            "add_info": add_info_json
        }

        # return response
        if res:
            return {"success": True, "message": "Generate response successfully", "status":200, "question":question, "data": res}
        return {"success": False, "message": "Fail to get response", "status":404, "data": {}}
    
    except HTTPException as e:
        raise e  # Let FastAPI + global handler format it
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
