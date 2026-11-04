from dotenv import load_dotenv
import os

from langchain_community.llms import OpenAI
from langchain_community.utilities import SQLDatabase

from urllib.parse import quote
import ast
import json

from langchain_experimental.sql import SQLDatabaseChain
from langchain.chains import create_sql_query_chain
from langchain_openai import ChatOpenAI

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import text
from datetime import datetime

from instruction import pm_instruction, additional_instruction, combine_instruction
from helper.searchQuery import run_search_query, get_search_db
from fastapi.concurrency import run_in_threadpool

import psycopg2

# Load environment variables
from dotenv import load_dotenv
import os

# Load environment variables
# Get environment (if not set, default to using .env)
APP_ENV = os.getenv("APP_ENV")

if APP_ENV:
    env_path = f"env/.env.{APP_ENV}"
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv("env/.env")  # Default to .env in root

# Define your OpenAI API key and database connection details
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Database connection
host = os.getenv("DB_HOST")
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")
database = os.getenv("DB_NAME")
port_rw = os.getenv("DB_PORT_RW")
port_read = os.getenv("DB_PORT_R")
sql_uri_read = f"postgresql+psycopg2://{user}:{password}@{host}:{port_read}/{database}"

# Define your LLM model
llm = ChatOpenAI(temperature=0, openai_api_key=OPENAI_API_KEY, model='gpt-4o-mini', request_timeout=120)

# ########################################################################
# Parameter: question, Response: risk
# Function: search the related information in database from the question
# ########################################################################
def _query_pm_database(question):
    db_read = get_search_db("pm_risk_table")

    # print("Process started ===================================== ")

    result = pm_instruction(question, db_read)
    query = result["raw_sql"]
    keywords = result["keywords"]

    if query:
        # Check the generated query, then execute it and fetch data
        output_list, message = run_search_query(query, "pm_risk_table")

        response = {
            "data": output_list,
            "keywords": keywords,
        }
        if message:
            response["message"] = message

        return json.dumps(response, indent=4, default=str)

    else:
        print("No SQL query was generated.")
        return json.dumps({
            "success": False,
            "message": "Unable to generate SQL query",
            "status": 500
        }, indent=4)

# The AI call and the database query are blocking, so they run in a worker
# thread. The server stays free to answer other requests while this waits.
async def query_pm_database(question):
    return await run_in_threadpool(_query_pm_database, question)

def query_combine(question):
    db_read = SQLDatabase.from_uri(sql_uri_read, include_tables=['pm_risk_table'], sample_rows_in_table_info=0, engine_args={'pool_pre_ping':True, 'pool_recycle':300})
    result = combine_instruction(question, db_read)
    # print(result)

    return result
