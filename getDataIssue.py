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

from fastapi import HTTPException, Depends, Request, Header
from fastapi.responses import JSONResponse
import re

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import text
from datetime import datetime

from instruction import issue_instruction

import psycopg2

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
llm = ChatOpenAI(temperature=0, openai_api_key=OPENAI_API_KEY, model='gpt-4o-mini', request_timeout=600)

# query result from question bank
def queryDBQuestion(host, user, password, database, port, query):
    try:
        # Establish a connection to the postgresql database
        connection = psycopg2.connect(
            host = host,
            user = user,
            password = password,
            database = database,
            port = port
        )

        # Create a cursor object
        cursor = connection.cursor()

        # Execute the query
        cursor.execute(query)

        # Fetch all rows and insert into an array
        rows = cursor.fetchall()  # Fetch all rows
        return rows
    except psycopg2.Error as err:
        print("Error executing query:", err)
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'connection' in locals():
            connection.close()

# ########################################################################
# Parameter: question, Response: risk
# Function: search the related information in database from the question
# ########################################################################
async def query_issue_database(question):
    db_read = SQLDatabase.from_uri(sql_uri_read, include_tables=['lesson_learn'], sample_rows_in_table_info=2, engine_args={'pool_pre_ping':True, 'pool_recycle':300})
    
    try:
        # print("Process started ===================================== ")

        result = issue_instruction(question, db_read)
        query = result["raw_sql"]
        keywords = result["keywords"]

        if query:
            # Find the start of the SELECT statement
            start_index = query.find("SELECT")
            end_index = query.find(";") + 1  # Include the semicolon
            query = query[start_index:end_index]  # Extract the matched SQL query
            print("Generated SQL Query:", query)
            # print("SQL query was generated")

            # Execute the query and fetch data
            response_sql_rows = queryDBQuestion(host, user, password, database, port_read, query)
            # response_sql_rows = str(response_sql_rows)

            if not response_sql_rows or response_sql_rows == "[]":
                return json.dumps({
                    "data": [],
                    "keywords": keywords,
                }, indent=4)
            else:
                # Preprocess the output
                # print(response_sql_rows)
                output_list = [
                    {
                        "issue_id": row[0],
                        "customer_segment": row[1],
                        "project_type": row[2],
                        "project_complexity": row[3],
                        "issue_description": row[4],
                        "issue_reason": row[5],
                        "issue_owner": row[6],
                        "issue_action_plan": row[7],
                        "issue_help_needed": row[8],
                        "issue_impacted_deliverables_milestone": row[9],
                        "issue_resolution": row[10]
                    }
                    for row in response_sql_rows
                ]

                return json.dumps({
                    "data": output_list,
                    "keywords": keywords,
                }, indent=4)

        else:
            print("No SQL query was generated.")
            return json.dumps({
                "success": False,
                "message": "Unable to generate SQL query",
                "status": 500
            }, indent=4)
    finally:
        # ✅ Explicitly close/dispose engine
        db_read._engine.dispose()
    
