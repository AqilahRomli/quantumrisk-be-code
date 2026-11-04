from dotenv import load_dotenv
import os

from langchain_community.llms import OpenAI
from langchain_community.utilities import SQLDatabase
from langchain_experimental.sql import SQLDatabaseChain
from langchain.chains import create_sql_query_chain
from langchain_openai import ChatOpenAI

from fastapi import HTTPException, Depends, Request, Header
from fastapi.responses import JSONResponse
import re
import concurrent.futures

# Load environment variables
from dotenv import load_dotenv
import os

# Load environment variables
# Get environment (if not set, default to using .env)
APP_ENV = os.getenv("APP_ENV")

if APP_ENV:
    env_path = f"env/.env.{APP_ENV}"
    # print(f"🔁 Loading env from {env_path}")
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv("env/.env")  # Default to .env in root


# Define your OpenAI API key and database connection details
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Define your LLM model
llm = ChatOpenAI(temperature=0, openai_api_key=OPENAI_API_KEY, model='gpt-4o-mini', request_timeout=120)

# Precompile regex patterns
PATTERNS = {
    "Risk_Title": re.compile(r"\*\*Risk Title:\*\*\s*(.+)"),
    "Risk_Description": re.compile(r"\*\*Risk Description:\*\*\s*(.+)"),
    "Risk_Category": re.compile(r"\*\*Risk Category:\*\*\s*(.+)"),
    "Risk_Root_Cause": re.compile(r"\*\*Risk Root Cause:\*\*\s*(.+)"),
    "Risk_Impact": re.compile(r"\*\*Risk Impact:\*\*\s*(.+)"),
    "Risk_Mitigation": re.compile(r"\*\*Risk Mitigation:\*\*\s*(.+)"),
    "Relevance": re.compile(r"\*\*Relevance:\*\*\s*(.+)")
}

def parse_risk_block(risk):
    if not risk.strip():
        return None

    extracted = {}
    for key, pattern in PATTERNS.items():
        match = pattern.search(risk)
        if match:
            extracted[key] = match.group(1).strip()
        else:
            return None  # Skip if any field is missing

    return extracted

# ################################################################################## #
# Parameter: respon_text (answer from OPENAI knowledge)      result:formatted_risks  #
# Function: Process fallback_response_text into JSON format                          #
# ################################################################################## #
def format_fallback_response1(response_text):
    risks = re.split(r"(?=###\s*Risk\s*\d+[:：])", response_text.strip())

    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = executor.map(parse_risk_block, risks)

    return [r for r in results if r]

def format_fallback_response(response_text):
    # --- Extract Keywords: "Keywords: key1, key2, key3" ---
    keywords = []

    match = re.search(r"Keywords\s*:\s*(.*)", response_text, re.IGNORECASE)
    if match:
        raw_keywords = match.group(1).strip()
        # Split by comma
        keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]


    # --- Extract Risk Blocks (existing logic) ---
    risks_raw = re.split(r"(?=###\s*Risk\s*\d+[:：])", response_text.strip())

    with concurrent.futures.ThreadPoolExecutor() as executor:
        parsed_risks = list(executor.map(parse_risk_block, risks_raw))

    risks = [r for r in parsed_risks if r]


    # --- Return both values ---
    return {
        "keywords": keywords,
        "risks": risks
    }


# ################################################################################### #
# Parameter: question, db   result: query_match, keywords                             #
# Function: generate query and keyword from question to get data from pm_risk_table   #
# ################################################################################### #
def pm_instruction(question, db):
    # Setup prompt to generate SQL query
    PROMPT = f"""
    You are given a table with columns: 
    Columns = [
    "stakeholder", "customer_name", "project_name", "project_vertical", "project_type",
    "risk_id", "risk_category", "specific_risk", "risk_event","risk_root_cause",
    "risk_impact", "likelihood_level", "likelihood_justification",
    "impact_level", "impact_justification", "risk_rating", "risk_mitigation_plan",
    "risk_mitigation_control_owner_group", "opportunity_id"
    ]

    Your goal: Generate an SQL query that retrieves all columns, but only searches for keywords in contextually relevant columns based on the user's question.

    Column Purposes
    Use this guide to help determine which columns to use when searching for keywords:
    - "customer_name": 	Customer associated with the project.
    - "project_vertical": industry sector or business domain
    - "project_name": Name of the project.
    - "project_type": Type or classification of the project.
    - "risk_category": Category grouping of the risk.
    - "specific_risk": Describes the specific risk.
    - "risk_event": Describes the risk event.
    - "risk_root_cause": Explains the root cause.
    - "risk_impact": Explains the consequence of the risk.
    - "risk_mitigation_plan": Describes how the risk will be mitigated.
    - "risk_mitigation_control_owner_group": Responsible party.
    - "risk_rating" / "likelihood_level" / "impact_level": Severity or probability ratings
    - "likelihood_justification" / "impact_justification": Justifications for rating level.
    - "stakeholder": Stakeholder involved in the risk or mitigation.
    - "opportunity_id": Same with SFDC id


    Steps:
    1. Correct any spelling issues in the question.
    2. Identify a focus column If the question includes context like “risk category”, “project type”, or “mitigation plan”, select the relevant column:
    - “mitigation plan” → risk_mitigation_plan
    - “stakeholder” → stakeholder
    - “project type” → project_type
    - “risk category” → risk_category
    - If a focus keyword is found, extract it (e.g., "connectivity" → project_type).
    - for project_vertical rewrite focus keyword by replace "space" with "_"
        -eg: “BANKING AND FINANCIAL SERVICES” → BANKING_AND_FINANCIAL_SERVICES
    3. Extract general keywords from the remaining question (remove stopwords).
    4. Identify Intent-based Columns:
    - Based on the context of the question, determine which column(s) the keyword should be searched in.
    + Only include a column for keyword matching if it is contextually relevant to the question.
    + Do not include "risk_mitigation_plan" unless the question explicitly mentions:
    - mitigation
    - mitigation plan
    - mitigation strategy
    - risk response
    - action plan

    - Example mappings:
    - If the question mentions "in mitigation plan", search in "risk_mitigation_plan"
    - If the keyword is a technology or service (e.g., "MetroE", "IPVPN"), search in:
        - "project_name"
        - "risk_desc_specific_risk"
    - If the context is about ownership or responsibility, prefer:
        - "stakeholder"
        - "risk_mitigation_control_owner_group"
    - If question ask for risk or project for SFDC id or opportunity id please refer to column "opportunity_id" and don't limit the result

    5. SQL Logic:
    - If a focus keyword exists, use: "focus_column" ILIKE '%focus_keyword%'
    + Apply keywords only in contextually appropriate columns.
    + Do NOT apply general keywords in "risk_mitigation_plan" unless the question mentions mitigation explicitly.
    + For general questions, match across standard context-rich fields like:
    "customer_name", "project_name", "project_type", "project_vertical",
    "risk_category", "risk_desc_specific_risk", "risk_desc_root_cause",
    "risk_desc_impact", "likelihood_justification", "impact_justification"
    - Use ILIKE for all comparisons.
    - Order by relevance (matches in focus_column weighted higher).
    - select data from all [column] that have been declare
    - Extract the number of results to return, if specified default 5.
    - If the question includes “all”, do not apply LIMIT — but still apply keyword matching the same as you would with a number.
    - Do not alter keyword logic based on the presence of a number vs. “all”.


    Return only the final SQL query.

    Example 1:
    Question: What are 3 risks involving MetroE and IPVPN for project type connectivity?
    → Focus Column: project_type
    → Focus Keyword: connectivity
    → General Keywords: MetroE, IPVPN
    → SQL:
    SELECT [columns] FROM pm_risk_table 
    WHERE "project_type" ILIKE '%connectivity%' AND (
    "customer_name" ILIKE '%metroE%' OR "customer_name" ILIKE '%IPVPN%' OR ...
    )
    LIMIT 3;

    Example 2:
    Question: What risks are associated with implementation scheduling?
    → Focus Column: risk_category
    → Focus Keyword: implementation_scheduling
    → General Keywords: 
    → SQL:
    SELECT [columns] FROM pm_risk_table 
    WHERE "risk_category" ILIKE '%implementation_scheduling%' 
    LIMIT 5;

    Example 3:
    Question: Can you list all risk for project that involve sdwan and IPVPN?
    → containt "all" in question
    → Focus Column: 
    → Focus Keyword: 
    → General Keywords: sdwan, IPVPN
    → SQL:
    SELECT [columns] FROM pm_risk_table 
    WHERE (
    "project_name" ILIKE '%sdwan%' OR "project_name" ILIKE '%IPVPN%' OR ...
    );

    Example 4:
    Question: Please list detail for project that have SFDC ID 1236-5897?
    → Focus Column: opportunity_id
    → Focus Keyword: 1236-5897
    → General Keywords: 
    → SQL:
    SELECT [columns] FROM pm_risk_table 
    WHERE "opportunity_id" ILIKE '%1236-5897%';

    The question: {question}
    """

    chain = create_sql_query_chain(llm, db)
    response_sql = chain.invoke({"question": PROMPT})

    # Extract SQL
    pattern = re.compile(r'(SELECT.*?;)', re.IGNORECASE | re.DOTALL)
    query_match = re.sub(pattern, r'\1', response_sql)

    # Extract keywords
    matches = re.findall(r"%([^%]+)%", response_sql)
    unique_keywords = set(matches)
    keywords = ', '.join(unique_keywords)

    return {
        "raw_sql": query_match,
        "keywords": keywords
    }

# ################################################################################### #
# Parameter: question, db   result: query_match, keywords                             #
# Function: generate query and keyword from question to get data from sc_risk_table   #
# ################################################################################### #
def sc_instruction(question, db):
    # Setup prompt to generate SQL query
    PROMPT = f"""
    You are given a table with columns: 
    Columns = [
    "stakeholder", "risk_id", "customer", "project_name", "vertical", 
    "project_description", "product_service_offering", "risk_category", 
    "risk_desc", "risk_event", "root_cause", "risk_impact", "likelihood", "likelihood_justification", 
    "impact", "impact_justification", "risk_rating", "key_mitigation", 
    "residual_risk_rating", "control_owner", "sfdc_id",
    ]

    Your goal: Generate an SQL query that retrieves all columns, but only searches for keywords in contextually relevant columns based on the user's question.

    //Need to Edit
    Column Purposes
    Use this guide to help determine which columns to use when searching for keywords:
    - "customer": 	Customer associated with the project.
    - "project_name": Name of the project.
    - "vertical": Type or classification of the project.
    - "project_description": Describes of project in detail.
    - "product_service_offering": List of products or services proposed for delivery..
    - "risk_category": Category grouping of the risk.
    - "risk_desc": Describes the specific risk in detail.
    - "risk_event": Explains the risk event.
    - "root_cause": Explains the root cause.
    - "risk_impact": Explains the consequence of the risk.
    - "key_mitigation": Describes how the risk will be mitigated.
    - "control_owner": Responsible party.
    - "risk_rating" / "likelihood" / "impact": Severity or probability ratings
    - "likelihood_justification" / "impact_justification": Justifications for rating level.
    - "stakeholder": Stakeholder involved in the risk or mitigation.
    - "sfdc_id": id for new opportunity


    Steps:
    1. Correct any spelling issues in the question.
    2. Identify a focus column If the question includes context like “risk category”, “vertical”, or “mitigation plan”, select the relevant column:
    - “mitigation plan” → key_mitigation
    - “stakeholder” → stakeholder
    - “vertical” → vertical
    - “risk category” → risk_category
    - If a focus keyword is found, extract it (e.g., "NON TECHNICAL" → risk_category).
    3. Extract general keywords from the remaining question (remove stopwords).
    4. Identify Intent-based Columns:
    - Based on the context of the question, determine which column(s) the keyword should be searched in.
    + Only include a column for keyword matching if it is contextually relevant to the question.
    + Do not include "key_mitigation" unless the question explicitly mentions:
    - mitigation
    - mitigation plan
    - mitigation strategy
    - risk response
    - action plan

    - Example mappings:
    - If the question mentions "in mitigation plan", search in "key_mitigation"
    - If the keyword is a technology or service (e.g., "MetroE", "IPVPN"), search in:
        - "project_name"
        - "project_description"
        - "product_service_offering"
    - If the context is about ownership or responsibility, prefer:
        - "stakeholder"
        - "control_owner"
    - If question ask for risk or project for SFDC id or opportunity id please refer to column "sfdc_id" and don't limit the result

    5. SQL Logic:
    - If a focus keyword exists, use: "focus_column" ILIKE '%focus_keyword%'
    + Apply keywords only in contextually appropriate columns.
    + Do NOT apply general keywords in "key_mitigation" unless the question mentions mitigation explicitly.
    + For general questions, match across standard context-rich fields like:
    "project_name", "vertical", "project_description", "product_service_offering", 
    "risk_desc", "risk_event", "root_cause", "risk_impact", "likelihood_justification", "impact_justification",
    - Use ILIKE for all comparisons.
    - Order by relevance (matches in focus_column weighted higher).
    - select data from all [column] that have been declare
    - Extract the number of results to return, if specified default 5.
    - If the question includes “all”, do not apply LIMIT — but still apply keyword matching the same as you would with a number.
    - Do not alter keyword logic based on the presence of a number vs. “all”.


    Return only the final SQL query.

    Example 1:
    Question: Can you list 3 risks for project involve metroE and IPVPN for the project vertical, education?
    → Focus Column: vertical
    → Focus Keyword: education
    → General Keywords: metroE, IPVPN
    → SQL:
    SELECT [columns] FROM sc_risk_table 
    WHERE "vertical" ILIKE '%education%' AND (
    "project_name" ILIKE '%metroE%' OR "project_name" ILIKE '%IPVPN%' OR ...
    )
    LIMIT 3;

    Example 2:
    Question: What risks are associated with implementation scheduling?
    → Focus Column: risk_category
    → Focus Keyword: implementation_scheduling
    → General Keywords: 
    → SQL:
    SELECT [columns] FROM sc_risk_table 
    WHERE "risk_category" ILIKE '%implementation_scheduling%' 
    LIMIT 5;

    Example 3:
    Question: Can you list all risk for project that involve sdwan?
    → containt "all" in question
    → Focus Column: 
    → Focus Keyword: 
    → General Keywords: sdwan
    → SQL:
    SELECT [columns] FROM sc_risk_table 
    WHERE (
    "project_name" ILIKE '%sdwan%' OR "project_name" ILIKE '%sdwan%' OR ...
    );

    Example 4:
    Question: Please list detail for project that have SFDC ID 1236-5897?
    → Focus Column: sfdc_id
    → Focus Keyword: 1236-5897
    → General Keywords: 
    → SQL:
    SELECT [columns] FROM sc_risk_table 
    WHERE "sfdc_id" ILIKE '%1236-5897%';

    The question: {question}
    """

    chain = create_sql_query_chain(llm, db)
    response_sql = chain.invoke({"question": PROMPT})

    # Extract SQL
    pattern = re.compile(r'(SELECT.*?;)', re.IGNORECASE | re.DOTALL)
    query_match = re.sub(pattern, r'\1', response_sql)

    # Extract keywords
    matches = re.findall(r"%([^%]+)%", response_sql)
    unique_keywords = set(matches)
    keywords = ', '.join(unique_keywords)

    return {
        "raw_sql": query_match,
        "keywords": keywords
    }

# ################################################################################### #
# Parameter: question        result: formatted_add_info                               #
# Function: get additional info base on question                                      #
# ################################################################################### #
def additional_instruction1(question):
    additional_prompt = f"""
    Fix typos in the question below, then identify the keywords in that question and answer it using the format provided.

    Corrected Question: [place corrected version here]

    For each risk, include exactly 5 items in this format:

    ### Risk {{n}}: {{Risk Title}}
    - **Risk Title:** ...
    - **Risk Description:** ...
    - **Risk Category:** ...
    - **Risk Root Cause:** ...
    - **Risk Impact:** ...
    - **Risk Mitigation:** ...
    - **Source Title:** ...
    - **Source Link:** ...
    **Relevance:** ...

    If the question asks for N answers, return that many; else, return 5.

    Question: {question}
    """

    fallback_response = llm.invoke(additional_prompt)
    fallback_response_text = getattr(fallback_response, "content", str(fallback_response))


    #print(fallback_response_text)
    # Format the fallback response
    formatted_add_info = format_fallback_response(fallback_response_text)

    return formatted_add_info

def additional_instruction(question):
    additional_prompt = f"""
    Fix typos in the question below, then identify the keywords in that question.
    Return the output using the exact format below.

    Corrected Question: [place corrected version here]

    Keywords: keyword1, keyword2, keyword3
    ...

    For each risk, include exactly 5 items in this format:

    ### Risk {{n}}: {{Risk Title}}
    - **Risk Title:** ...
    - **Risk Description:** ...
    - **Risk Category:** ...
    - **Risk Root Cause:** ...
    - **Risk Impact:** ...
    - **Risk Mitigation:** ...
    - **Source Title:** ...
    - **Source Link:** ...
    **Relevance:** ...

    If the question asks for N answers, return that many; else, return 5.

    Question: {question}
    """

    fallback_response = llm.invoke(additional_prompt)
    fallback_response_text = getattr(fallback_response, "content", str(fallback_response))

    # Format the fallback response
    formatted_add_info = format_fallback_response(fallback_response_text)

    return formatted_add_info

# ################################################################################### #
# Parameter: question, db   result: query_match, keywords                             #
# Function: generate query and keyword from question to get data from lesson_learn    #
# ################################################################################### #
def ll_instruction(question, db):
    # Setup prompt to generate SQL query
    PROMPT = f"""
    You are given a table with columns: 
    Columns = [
    "ll_id", "sfdc_opportunity_id", "customer_name", "project_name", 
    "sfdc_segment", "lead_project_manager", "achiement_improvement", 
    "category", "challenge",	"resolution", "lesson_learned", 
    "stakeholder_pic", "segment"
    ]

    Your goal: Generate an SQL query that retrieves all columns, but only searches for keywords in contextually relevant columns based on the user's question.

    Steps:
    1. Correct any spelling issues in the question.
    2. Extract Keywords: Remove stopwords and verbs. Identify main keywords.
    3. Build SQL WHERE Clause
    - Use ILIKE for all keyword matching.
    - select data from all [column] that have been declare
    - Apply each keyword across these columns:
        - project_name, challenge, resolution, lesson_learned
    4. Limit & Order Logic
    - If the question contains a number (e.g., “list 5”), use LIMIT with that value.
    - If it contains “all”, do not use LIMIT.
    - If neither, default to LIMIT 5.

    Return only the final SQL query.

    Example 1:
    Question: Can you list 3 risks for project involve metroE and IPVPN for the project vertical, education?
    → General Keywords: metroE, IPVPN
    → SQL:
    SELECT [columns] FROM lesson_learn
    WHERE (
    "project_name" ILIKE '%metroE%' OR "project_name" ILIKE '%IPVPN%' OR ...
    )
    LIMIT 3;

    Example 2:
    Question: What risks are associated with implementation scheduling?
    → General Keywords: implementation_scheduling
    → SQL:
    SELECT [columns] FROM lesson_learn
    WHERE (
    "project_name" ILIKE '%implementation_scheduling%' OR "project_name" ILIKE '%implementation_scheduling%' OR ...
    )
    LIMIT 5;

    Example 3:
    Question: Can you list all risk for project that involve sdwan?
    → containt "all" in question
    → General Keywords: sdwan
    → SQL:
    SELECT [columns] FROM lesson_learn 
    WHERE (
    "project_name" ILIKE '%sdwan%' OR "project_name" ILIKE '%sdwan%' OR ...
    );

    The question: {question}
    """

    chain = create_sql_query_chain(llm, db)
    response_sql = chain.invoke({"question": PROMPT})

    # Extract SQL
    pattern = re.compile(r'(SELECT.*?;)', re.IGNORECASE | re.DOTALL)
    query_match = re.sub(pattern, r'\1', response_sql)

    # Extract keywords
    matches = re.findall(r"%([^%]+)%", response_sql)
    unique_keywords = set(matches)
    keywords = ', '.join(unique_keywords)

    return {
        "raw_sql": query_match,
        "keywords": keywords
    }

# ################################################################################### #
# Parameter: question, db   result: query_match, keywords                             #
# Function: generate query and keyword from question to get data from PM Issues       #
# ################################################################################### #
def issue_instruction(question, db):
    # Setup prompt to generate SQL query
    PROMPT = f"""
    You are given a table with columns: 
    Columns = [
    "issue_id", "customer_segment", "project_type", "project_complexity",
    "issue_description", "issue_reason", "issue_owner", "issue_action_plan", 
    "issue_help_needed", "issue_impacted_deliverables_milestone", "issue_resolution"
    ]

    Your goal: Generate an SQL query that retrieves all columns, but only searches for keywords in contextually relevant columns based on the user's question.

    Steps:
    1. Correct any spelling issues in the question.
    2. Extract Keywords: Remove stopwords and verbs. Identify main keywords.
    3. Build SQL WHERE Clause
    - Use ILIKE for all keyword matching.
    - select data from all [column] that have been declare
    - Apply each keyword across these columns:
        - customer_segment, project_type, issue_description, issue_reason
    4. Limit & Order Logic
    - If the question contains a number (e.g., “list 3”), use LIMIT with that value.
    - If it contains “all”, do not use LIMIT.
    - If neither, default to LIMIT 5.

    Return only the final SQL query.

    Example 1:
    Question: Can you list 3 risks for project involve metroE and IPVPN for the project vertical, education?
    → General Keywords: metroE, IPVPN
    → SQL:
    SELECT [columns] FROM pm_issues
    WHERE (
    "customer_segment" ILIKE '%metroE%' OR "customer_segment" ILIKE '%IPVPN%' OR ...
    )
    LIMIT 3;

    Example 2:
    Question: What risks are associated with implementation scheduling?
    → General Keywords: implementation_scheduling
    → SQL:
    SELECT [columns] FROM pm_issues
    WHERE (
    "customer_segment" ILIKE '%implementation_scheduling%' OR "project_type" ILIKE '%implementation_scheduling%' OR ...
    )
    LIMIT 5;

    Example 3:
    Question: Can you list all risk for project that involve sdwan?
    → containt "all" in question
    → General Keywords: sdwan
    → SQL:
    SELECT [columns] FROM pm_issues 
    WHERE (
    "customer_segment" ILIKE '%sdwan%' OR "project_type" ILIKE '%sdwan%' OR ...
    );

    The question: {question}
    """

    chain = create_sql_query_chain(llm, db)
    response_sql = chain.invoke({"question": PROMPT})

    # Extract SQL
    pattern = re.compile(r'(SELECT.*?;)', re.IGNORECASE | re.DOTALL)
    query_match = re.sub(pattern, r'\1', response_sql)

    # Extract keywords
    matches = re.findall(r"%([^%]+)%", response_sql)
    unique_keywords = set(matches)
    keywords = ', '.join(unique_keywords)

    return {
        "raw_sql": query_match,
        "keywords": keywords
    }

# ################################################################################################################### #
# Parameter: projectName, vertical, projectDesc, product,      result: question                                       #
# Function: generate question from projectName, vertical, projectDesc, product to get data from pm_risk_table         #
# ################################################################################################################### #
def create_question_instruction(projectName, vertical, projectDesc, product):
    # Construct the prompt for the LLM
    prompt = f"""
    Task:
    You are given key project-related information: `projectName`, `vertical`, `projectDesc`, and `product`.

    Your task is to generate **one clearly worded, general risk-related question** based on the provided project details. This question will be used to query a risk database and must be formulated to support identifying relevant risks across multiple dimensions (e.g., project type, category, descriptions).

    Requirements:
    1. Phrase the question in **natural language**, focusing specifically on **risks related to the project**.
    2. Incorporate **general project context**, such as:
    - Technology or product used (e.g., SDWAN, IPVPN)
    - Nature of the project (e.g., WAN improvement, system integration)
    - Industry or vertical (e.g., public services, financial services)
    3. Ensure the question is **broad but meaningful**—not too narrow or overly specific—so it can map across multiple database columns.
    4. Avoid **vague or abstract language**. The question should reflect **practical, real-world concerns** related to project risks.
    5. Structure the question to support extraction of both:
    - **Focus keywords** (e.g., technology, project type)
    - **General keywords** (e.g., industry, project characteristics)
    These keywords should align with columns like `project_type`, `risk_category`, `risk_desc_specific_risk`, etc.
    6. **Do not include the exact project name**. Instead, generalize the description using project characteristics.

    Output:
    Return **only one** risk-related question in natural language.

    Input:
    - projectName: {projectName}
    - vertical: {vertical}
    - projectDesc: {projectDesc}
    - product: {product}
    """

    # Generate response using the language model
    response = llm.invoke(prompt)

    # Access the content/text from the response
    response_text = response.content if hasattr(response, "content") else str(response)

    # Extract the question
    risk_question = response_text.strip().replace("Question:", "").strip()

    return risk_question

# ################################################################################### #
# Parameter: question, db   result: query_match, keywords                             #
# Function: generate query and keyword from question to get data from pm_risk_table   #
# ################################################################################### #
def combine_instruction(question,db):
    # Setup prompt to generate SQL query
    instruction_template = """
    Description: Given you 2 task
    1. **Provide Knowledge-Based Answers:**
        - Based on your domain knowledge, generate five answers to the given question, which the answer must include risk title, risk description, risk category, risk root cause, risk impact and risk mitigation.

    2. **Generate SQL Queries for Data Retrieval:**
        - Given two different tables, `pm_risk_table` and `sc_risk_table`, your task is to extract information based on the provided question by generating two separate SQL queries tailored to each table’s schema.

        ### Table Structures:

        **1. pm_risk_table Columns:**
        - "stakeholder", "customer_name", "project_name", "project_vertical", "project_type", "risk_id", "risk_category", "risk_desc_specific_risk", "risk_desc_root_cause", "risk_desc_impact", "likelihood_level", "likelihood_justification", "impact_level", "impact_justification", "risk_rating", "risk_mitigation_plan", "risk_mitigation_control_owner"

        - PM Matching Columns:
            - "customer_name", "project_name", "project_vertical", "project_type", "risk_category", "risk_desc_specific_risk", "risk_desc_root_cause", "risk_desc_impact", "likelihood_level", "likelihood_justification", "impact_level", "impact_justification", "risk_rating", "risk_mitigation_plan"

        **2. sc_risk_table Columns:**
        - "stakeholder", "risk_id", "customer", "project_name", "vertical", "project_description", "product_service_offering", "risk_category", "risk_desc", "risk_event", "root_cause", "likelihood", "likelihood_justification", "impact", "impact_justification", "risk_rating", "key_mitigation", "residual_risk_rating", "control_owner"

        - SC Matching Columns :
            - "customer", "project_name", "vertical", "project_description", "product_service_offering", "risk_category", "risk_desc", "risk_event", "root_cause", "likelihood", "likelihood_justification", "impact", "impact_justification", "risk_rating", "key_mitigation", "residual_risk_rating"

        ---

        ### Steps:

        **1. Identify Focus Column and Keyword:**
        - If the question mentions a **specific attribute** (e.g., project type, risk category, vertical), identify the relevant focus column per table.
            - For example:
                - If the question mentions “project type”, map to `"project_type"` in `pm_risk_table` and skip for `sc_risk_table`.
                - If it mentions “vertical”, map to `"vertical"` in `sc_risk_table` and skip for `pm_risk_table`.
        - If no focus column is mentioned, skip focus identification and proceed with general keywords.

        **2. Extract Keywords:**
        - **Focus Keyword**:
            - If a focus column is identified, extract the specific value and format multi-word phrases with underscores (e.g., "implementation scheduling" → "implementation_scheduling").
        - **General Keywords**:
            - Extract all other meaningful terms from the question, excluding stopwords and context-free verbs.

        **3. Construct Queries:**
        - Construct an SQL query using the extracted Focus Keywords and General Keyword.
        - Use ILIKE instead of LIKE to ensure case-insensitive keyword matching.
        - Ensure the Focus Column(s) must contain the Focus Keyword, even if other conditions fail.
            - Example: If the question specifies "project_type", rows must satisfy "project_type ILIKE '%focus_keyword%'"
        - Apply OR conditions across all predefined matching columns for pm_risk_table (refer to PM Matching Columns) and sc_risk_table (refer to SC Matching Columns) to search for keyword matches.
        - Use parentheses to group conditions for each column to ensure clarity in logical operations.

        a. Example Scenarios: Focus Column and keywords Present
            Question: Can you list 5 risks for project involve metroE and IPVPN for the category, scheduling?
            Primary Column PM: "risk_category"
            Primary Column SC: "risk_category"
            Focus Keyword: scheduling
            Keywords: metroE, IPVPN
            Query:
            - For **pm_risk_table**, generate:
                SELECT 
                    "stakeholder", "customer_name", "project_name", "project_vertical", "project_type", "risk_id", 
                    "risk_category", "risk_desc_specific_risk", "risk_desc_root_cause", "risk_desc_impact",
                    "likelihood_level", "likelihood_justification", "impact_level", "impact_justification", 
                    "risk_rating", "risk_mitigation_plan", "risk_mitigation_control_owner"
                FROM pm_risk_table
                WHERE 
                    [IF FOCUS COLUMN PRESENT]
                    ("<focus_column_PM>" ILIKE '%<focus_keyword>%')
                    AND
                    (
                        "customer_name" ILIKE '%<keyword1>%' OR
                        "project_name" ILIKE '%<keyword1>%' OR
                        "project_vertical" ILIKE '%<keyword1>%' OR
                        "project_type" ILIKE '%<keyword1>%' OR
                        "risk_category" ILIKE '%<keyword1>%' OR
                        "risk_desc_specific_risk" ILIKE '%<keyword1>%' OR
                        "risk_desc_root_cause" ILIKE '%<keyword1>%' OR
                        "risk_desc_impact" ILIKE '%<keyword1>%' OR
                        "likelihood_level" ILIKE '%<keyword1>%' OR
                        "likelihood_justification" ILIKE '%<keyword1>%' OR
                        "impact_level" ILIKE '%<keyword1>%' OR
                        "impact_justification" ILIKE '%<keyword1>%' OR
                        "risk_rating" ILIKE '%<keyword1>%' OR
                        "risk_mitigation_control_owner" ILIKE '%<keyword1>%' OR
                        ...
                        [Repeat for each keyword]
                    )
                ORDER BY "risk_rating", "risk_category", "risk_desc_specific_risk"
                LIMIT <N>;

            - For **sc_risk_table**, generate:
                SELECT 
                    "stakeholder", "risk_id", "customer", "project_name", "vertical", "project_description", 
                    "product_service_offering", "risk_category", "risk_desc", "risk_event", "root_cause", 
                    "likelihood", "likelihood_justification", "impact", "impact_justification", 
                    "risk_rating", "key_mitigation", "residual_risk_rating", "control_owner"
                FROM sc_risk_table
                WHERE 
                    [IF FOCUS COLUMN PRESENT]
                    ("<focus_column_SC>" ILIKE '%<focus_keyword>%')
                    AND
                    (
                        "customer" ILIKE '%<keyword1>%' OR
                        "project_name" ILIKE '%<keyword1>%' OR
                        "vertical" ILIKE '%<keyword1>%' OR
                        "project_description" ILIKE '%<keyword1>%' OR
                        "product_service_offering" ILIKE '%<keyword1>%' OR
                        "risk_category" ILIKE '%<keyword1>%' OR
                        "risk_desc" ILIKE '%<keyword1>%' OR
                        "risk_event" ILIKE '%<keyword1>%' OR
                        "root_cause" ILIKE '%<keyword1>%' OR
                        "likelihood" ILIKE '%<keyword1>%' OR
                        "likelihood_justification" ILIKE '%<keyword1>%' OR
                        "impact" ILIKE '%<keyword1>%' OR
                        "impact_justification" ILIKE '%<keyword1>%' OR
                        "risk_rating" ILIKE '%<keyword1>%' OR
                        "key_mitigation" ILIKE '%<keyword1>%' OR
                        "residual_risk_rating" ILIKE '%<keyword1>%' OR
                        ...
                        [Repeat for each keyword]
                    )
                ORDER BY "risk_rating", "risk_category", "risk_desc"
                LIMIT <N>;
        
        b. Example Scenarios: Focus Column Present but no Keywords
            Question: What risks are associated with implementation scheduling?
            Primary Column PM: "risk_category"
            Primary Column SC: "risk_category"
            Focus Keyword: implementation_scheduling
            keyword:
            Query:
            - For **pm_risk_table**, generate:
                SELECT 
                    "stakeholder", "customer_name", "project_name", "project_vertical", "project_type", "risk_id", 
                    "risk_category", "risk_desc_specific_risk", "risk_desc_root_cause", "risk_desc_impact",
                    "likelihood_level", "likelihood_justification", "impact_level", "impact_justification", 
                    "risk_rating", "risk_mitigation_plan", "risk_mitigation_control_owner"
                FROM pm_risk_table
                WHERE 
                    [IF FOCUS COLUMN PRESENT]
                    ("<focus_column_PM>" ILIKE '%<focus_keyword>%')
                ORDER BY "risk_rating", "risk_category", "risk_desc_specific_risk"
                LIMIT <N>;

            - For **sc_risk_table**, generate:
                SELECT 
                    "stakeholder", "risk_id", "customer", "project_name", "vertical", "project_description", 
                    "product_service_offering", "risk_category", "risk_desc", "risk_event", "root_cause", 
                    "likelihood", "likelihood_justification", "impact", "impact_justification", 
                    "risk_rating", "key_mitigation", "residual_risk_rating", "control_owner"
                FROM sc_risk_table
                WHERE 
                    [IF FOCUS COLUMN PRESENT]
                    ("<focus_column_SC>" ILIKE '%<focus_keyword>%')
                ORDER BY "risk_rating", "risk_category", "risk_desc"
                LIMIT <N>;

        c. Example Scenarios: No Focus Column but have keywords
            Question: what is risk for project that involve metroE and IPVPN?
            Primary Column:
            Focus Keyword:
            Keywords: metroE, IPVPN
            Query:
            - For **pm_risk_table**, generate:
                SELECT 
                    "stakeholder", "customer_name", "project_name", "project_vertical", "project_type", "risk_id", 
                    "risk_category", "risk_desc_specific_risk", "risk_desc_root_cause", "risk_desc_impact",
                    "likelihood_level", "likelihood_justification", "impact_level", "impact_justification", 
                    "risk_rating", "risk_mitigation_plan", "risk_mitigation_control_owner"
                FROM pm_risk_table
                WHERE 
                    "customer_name" ILIKE '%<keyword1>%' OR
                    "project_name" ILIKE '%<keyword1>%' OR
                    "project_vertical" ILIKE '%<keyword1>%' OR
                    "project_type" ILIKE '%<keyword1>%' OR
                    "risk_category" ILIKE '%<keyword1>%' OR
                    "risk_desc_specific_risk" ILIKE '%<keyword1>%' OR
                    "risk_desc_root_cause" ILIKE '%<keyword1>%' OR
                    "risk_desc_impact" ILIKE '%<keyword1>%' OR
                    "likelihood_level" ILIKE '%<keyword1>%' OR
                    "likelihood_justification" ILIKE '%<keyword1>%' OR
                    "impact_level" ILIKE '%<keyword1>%' OR
                    "impact_justification" ILIKE '%<keyword1>%' OR
                    "risk_rating" ILIKE '%<keyword1>%' OR
                    "risk_mitigation_control_owner" ILIKE '%<keyword1>%' OR
                    ...
                    [Repeat for each keyword]
                ORDER BY "risk_rating", "risk_category", "risk_desc_specific_risk"
                LIMIT <N>;

            - For **sc_risk_table**, generate:
                SELECT 
                    "stakeholder", "risk_id", "customer", "project_name", "vertical", "project_description", 
                    "product_service_offering", "risk_category", "risk_desc", "risk_event", "root_cause", 
                    "likelihood", "likelihood_justification", "impact", "impact_justification", 
                    "risk_rating", "key_mitigation", "residual_risk_rating", "control_owner"
                FROM sc_risk_table
                WHERE
                    "customer" ILIKE '%<keyword1>%' OR
                    "project_name" ILIKE '%<keyword1>%' OR
                    "vertical" ILIKE '%<keyword1>%' OR
                    "project_description" ILIKE '%<keyword1>%' OR
                    "product_service_offering" ILIKE '%<keyword1>%' OR
                    "risk_category" ILIKE '%<keyword1>%' OR
                    "risk_desc" ILIKE '%<keyword1>%' OR
                    "risk_event" ILIKE '%<keyword1>%' OR
                    "root_cause" ILIKE '%<keyword1>%' OR
                    "likelihood" ILIKE '%<keyword1>%' OR
                    "likelihood_justification" ILIKE '%<keyword1>%' OR
                    "impact" ILIKE '%<keyword1>%' OR
                    "impact_justification" ILIKE '%<keyword1>%' OR
                    "risk_rating" ILIKE '%<keyword1>%' OR
                    "key_mitigation" ILIKE '%<keyword1>%' OR
                    "residual_risk_rating" ILIKE '%<keyword1>%' OR
                    ...
                    [Repeat for each keyword]
                ORDER BY "risk_rating", "risk_category", "risk_desc"
                LIMIT <N>;

        **4. Filtering and Ordering:**
        - Order results by column relevance and keyword match density.
        - If the question specifies a number, use it in LIMIT; otherwise, default to LIMIT 5.

    **3. Output:**
    - Return the PM SQL query and SC SQL query, formatted for execution in a database. and also answer for the question
    The question: {question}
    """

    final_prompt = instruction_template.format(question=question)
    response = llm.invoke(final_prompt) 
  

    return response