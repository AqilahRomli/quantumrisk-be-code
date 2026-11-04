# ==============================
# Standard Library
# ==============================
import json

# ==============================
# Third-Party Libraries
# ==============================
from langchain_openai import ChatOpenAI

from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

# ==============================
# Internal Modules
# ==============================
from helper.InstructionAI import additional_instruction



# ########################################################################
# Parameter: question, Response: risk
# Function: get additional information base on question
# ########################################################################
async def additional_Info(question):
    #print("Process started ===================================== ")

    # The AI call is blocking, so it runs in a worker thread and the server
    # stays free to answer other requests while this waits.
    add_result = await run_in_threadpool(additional_instruction, question)

    if add_result:
        #print("get Additional Info")
        #print(add_result)
        
        return json.dumps({
            "data": add_result.get("risks", []),
            "keywords": add_result.get("keywords", [])
        }, indent=4)

    else:
        print("No add info was generated.")
        return json.dumps({
            "success": False,
            "message": "Unable to generate SQL query",
            "status": 500
        }, indent=4)