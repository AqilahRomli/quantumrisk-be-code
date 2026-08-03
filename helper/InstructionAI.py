# ==============================
# Standard Library
# ==============================
import re
import json
import concurrent.futures

# ==============================
# Third-Party Libraries
# ==============================
from langchain_openai import ChatOpenAI

# ==============================
# Internal Modules
# ==============================
from core.config import settings


# Define your LLM model
llm = ChatOpenAI(temperature=0, openai_api_key=settings.OPENAI_API_KEY, model='gpt-4o-mini', request_timeout=600)

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


def get_issues_keywords(question):

    prompt = f"""
    Extract important search keywords from the question.

    RULES:
    - Remove stopwords
    - Remove generic words:
        - issue
        - risk
        - project
        - involve
        - problem
    - Keep only meaningful search terms
    - Detect result limit
    - If user says "all", limit = 1000
    - Default limit = 20

    Return ONLY valid JSON.

    FORMAT:
    {{
        "keywords": [],
        "limit": 5
    }}

    QUESTION:
    {question}
    """

    response = llm.invoke(prompt)

    content = response.content
    content = content.replace("```json", "").replace("```", "").strip()

    result = json.loads(content)

    keywords = result["keywords"]
    limit = result["limit"]

    query = build__issues_query(keywords, limit)

    return query, keywords


def build__issues_query(keywords, limit):

    search_fields = [
        "risk_mitigation_plan^2",
        "stakeholder^2",
        "project_type^2",
        "risk_category^2",
        "project_vertical^2",
        "project_name^2",
        "risk_desc_specific_risk^2"
    ]

    should_clauses = []

    for keyword in keywords:

        should_clauses.append({
            "multi_match": {
                "query": keyword,
                "fields": search_fields,
                "type": "best_fields",
                "fuzziness": "AUTO",
                "operator": "or"
            }
        })

    query = {
        "query": {
            "bool": {
                "should": should_clauses,
                "minimum_should_match": 1
            }
        },
        "size": limit
    }

    print("limit", limit)

    return query


def get_pm_keywords(question):

    prompt = f"""
        Extract search metadata from the user question.

        Return ONLY valid JSON.

        RULES:
        - Extract focus column if exists
        - Extract focus keyword
        - for project_vertical rewrite focus keyword by replace "space" with "_"
            -eg: “BANKING AND FINANCIAL SERVICES” → BANKING_AND_FINANCIAL_SERVICES
        - Extract important keywords only
        - Remove stopwords
        - Detect limit
        - If user says "all", limit = 1000
        - Detect whether mitigation search is needed

        VALID focus_column values:
        [
            "stakeholder",
            "customer_name",
            "project_name",
            "project_vertical",
            "project_type",
            "risk_category",
            "specific_risk",
            "risk_event",
            "risk_root_cause",
            "risk_impact",
            "risk_mitigation_plan",
            "risk_mitigation_control_owner_group",
            "opportunity_id"
        ]

        OUTPUT FORMAT:
        {{
            "focus_column": "",
            "focus_keyword": "",
            "keywords": [],
            "limit": 5,
            "search_mitigation": false,
            "is_sfdc_search": false
        }}

        QUESTION:
        {question}
        """

    response = llm.invoke(prompt)

    content = response.content
    content = content.replace("```json", "").replace("```", "").strip()

    result = json.loads(content)

    keywords = result["keywords"]

    query = build__pm_risk_query(result)

    return query, keywords

def build__pm_risk_query(metadata):

    keywords = metadata["keywords"]
    focus_column = metadata["focus_column"]
    focus_keyword = metadata["focus_keyword"]
    limit = metadata["limit"]
    search_mitigation = metadata["search_mitigation"]
    is_sfdc_search = metadata["is_sfdc_search"]

    should_clauses = []
    must_clauses = []

    # ==========================================
    # Focus column logic
    # ==========================================

    if focus_column and focus_keyword:

        must_clauses.append({
            "match": {
                focus_column: {
                    "query": focus_keyword,
                    "fuzziness": "AUTO"
                }
            }
        })

    # ==========================================
    # Standard search fields
    # ==========================================

    search_fields = [
        "customer_name^2",
        "project_name^2",
        "project_type^2",
        "project_vertical^2",
        "risk_category^3",
        "specific_risk^4",
        "risk_event^4",
        "risk_root_cause^4",
        "risk_impact^4"
    ]

    # add mitigation only when needed
    if search_mitigation:
        search_fields.append("risk_mitigation_plan^3")

    # ==========================================
    # Keyword search
    # ==========================================

    for keyword in keywords:

        should_clauses.append({
            "multi_match": {
                "query": keyword,
                "fields": search_fields,
                "type": "best_fields",
                "fuzziness": "AUTO"
            }
        })

    # ==========================================
    # SFDC exact search
    # ==========================================

    if is_sfdc_search:

        must_clauses.append({
            "wildcard": {
                "opportunity_id.keyword": f"*{focus_keyword}*"
            }
        })

    query = {
        "query": {
            "bool": {
                "must": must_clauses,
                "should": should_clauses,
                "minimum_should_match": 1 if should_clauses else 0
            }
        },
        "size": limit
    }

    return query


def get_sc_keywords(question):

    prompt = f"""
        You are an AI query classifier and Elasticsearch metadata extractor
        for a project risk management system.

        Your job:
        1. Detect whether the user is making a search request.
        2. Extract ONLY meaningful searchable business keywords and normalized synonyms for better Elasticsearch matching.
        3. 
        3. Extract focus column if exists and Extract focus keyword
        4. Detect limit, Default limit = 10
        5. If user says "all", limit = 1000
        6. Detect whether mitigation search is needed

        VALID focus_column values:
        [
            "stakeholder",
            "customer",
            "project_name",
            "vertical",
            "project_description",
            "product_service_offering",
            "risk_category",
            "risk_desc",
            "risk_event",
            "root_cause",
            "risk_impact",
            "key_mitigation",
            "control_owner",
            "sfdc_id",
        ]

        OUTPUT FORMAT:
        {{
            "is_search_request": true,
            "focus_column": "",
            "focus_keyword": "",
            "keywords": [],
            "limit": 5,
            "search_mitigation": false,
            "is_sfdc_search": false
        }}

        QUESTION:
        {question}
        """

    # prompt = f"""
    #     You are an AI query classifier and Elasticsearch metadata extractor
    #     for a project risk management system.

    #     Your job:
    #     1. Detect whether the user is making a search request.
    #     2. Extract meaningful searchable business keywords.
    #     3. Generate normalized synonyms for better Elasticsearch matching.
    #     4. Estimate search confidence.

    #     Return ONLY valid JSON.

    #     ==================================================
    #     SEARCH REQUEST DETECTION
    #     ==================================================

    #     Set "is_search_request" = false when:
    #     - greeting
    #     - casual conversation
    #     - thank you messages
    #     - unrelated questions
    #     - small talk
    #     - meaningless input

    #     Examples:
    #     - "hi"
    #     - "hello"
    #     - "thank you"
    #     - "how are you"
    #     - "good morning"

    #     Set "is_search_request" = true when:
    #     - user searches project risks
    #     - user searches mitigation
    #     - user searches technologies
    #     - user searches customers
    #     - user searches projects
    #     - user searches business terms
    #     - user provides technical keywords only

    #     Examples:
    #     - "sdwan"
    #     - "vpn"
    #     - "cloud"
    #     - "cisco"
    #     - "maxis"
    #     - "datacenter"

    #     ==================================================
    #     SEARCH CONFIDENCE
    #     ==================================================

    #     Generate:
    #     "search_confidence": value between 0 and 1

    #     Guideline:
    #     - 0.90 - 1.00
    #     Very clear search request

    #     - 0.70 - 0.89
    #     Likely search request

    #     - 0.50 - 0.69
    #     Ambiguous

    #     - below 0.50
    #     Probably not search request

    #     Examples:
    #     "show sdwan risks" -> 0.98
    #     "sdwan" -> 0.90
    #     "network issue" -> 0.60
    #     "hello" -> 0.05

    #     ==================================================
    #     KEYWORD EXTRACTION RULES
    #     ==================================================

    #     1. Extract ONLY meaningful searchable business keywords.

    #     2. DO NOT include generic intent words:
    #     [
    #         "risk",
    #         "risks",
    #         "project",
    #         "projects",
    #         "list",
    #         "show",
    #         "find",
    #         "search",
    #         "get",
    #         "display",
    #         "related",
    #         "involve"
    #     ]

    #     3. Keep multi-word technical phrases together:
    #     Examples:
    #     - "sd wan"
    #     - "cloud migration"
    #     - "data center"
    #     - "vpn gateway"

    #     4. Detect focus_column ONLY when clearly targeted.

    #     5. focus_keyword must contain exact searchable phrase.

    #     6. keywords must contain ONLY searchable business terms.

    #     ==================================================
    #     SYNONYM GENERATION - Include in Keyword
    #     ==================================================

    #     Generate normalized keyword variations for Elasticsearch matching.

    #     Examples:

    #     "sdwan" ->
    #     [
    #         "sdwan",
    #         "sd wan",
    #         "sd-wan"
    #     ]

    #     "datacenter" ->
    #     [
    #         "datacenter",
    #         "data center",
    #         "data-center"
    #     ]

    #     "vpn gateway" ->
    #     [
    #         "vpn gateway",
    #         "vpn-gateway"
    #     ]

    #     Rules:
    #     - lowercase all synonyms
    #     - remove duplicates
    #     - preserve technical meaning
    #     - include spacing variations
    #     - include hyphen variations when meaningful

    #     ==================================================
    #     LIMIT RULES
    #     ==================================================

    #     - default limit = 5
    #     - if user says "all", limit = 1000

    #     ==================================================
    #     MITIGATION DETECTION
    #     ==================================================

    #     Set "search_mitigation" = true if question mentions:
    #     - mitigation
    #     - action plan
    #     - recommendation
    #     - prevention
    #     - resolution
    #     - workaround

    #     ==================================================
    #     SFDC DETECTION
    #     ==================================================

    #     Set "is_sfdc_search" = true if query resembles:
    #     - opportunity ID
    #     - SFDC ID
    #     - CRM identifier

    #     ==================================================
    #     VALID focus_column VALUES
    #     ==================================================

    #     [
    #         "stakeholder",
    #         "customer",
    #         "project_name",
    #         "vertical",
    #         "project_description",
    #         "product_service_offering",
    #         "risk_category",
    #         "risk_desc",
    #         "risk_event",
    #         "root_cause",
    #         "risk_impact",
    #         "key_mitigation",
    #         "control_owner",
    #         "sfdc_id"
    #     ]

    #     ==================================================
    #     OUTPUT FORMAT
    #     ==================================================

    #     {{
    #         "is_search_request": true,
    #         "search_confidence": 0.95,
    #         "focus_column": "",
    #         "focus_keyword": "",
    #         "keywords": [],
    #         "limit": 5,
    #         "search_mitigation": false,
    #         "is_sfdc_search": false
    #     }}

    #     ==================================================
    #     QUESTION
    #     ==================================================

    #     {question}
    #     """

    response = llm.invoke(prompt)

    content = response.content
    content = content.replace("```json", "").replace("```", "").strip()

    result = json.loads(content)

    keywords = result["keywords"]

    query = build__sc_risk_query(result)

    return result

def build__sc_risk_query(metadata):

    keywords = metadata["keywords"]
    focus_column = metadata["focus_column"]
    focus_keyword = metadata["focus_keyword"]
    limit = metadata["limit"]
    search_mitigation = metadata["search_mitigation"]
    is_sfdc_search = metadata["is_sfdc_search"]

    should_clauses = []
    must_clauses = []

    # ==========================================
    # Focus column logic
    # ==========================================

    if focus_column and focus_keyword:

        must_clauses.append({
            "match": {
                focus_column: {
                    "query": focus_keyword,
                    "fuzziness": "AUTO"
                }
            }
        })

    # ==========================================
    # Standard search fields
    # ==========================================

    search_fields = [
        "customer^2",
        "project_name^2",
        "project_description^2",
        "vertical^2",
        "product_service_offering^2",
        "risk_category^3",
        "risk_desc^4",
        "risk_event^4",
        "root_cause^4",
        "risk_impact^4"
    ]

    # add mitigation only when needed
    if search_mitigation:
        search_fields.append("key_mitigation^3")

    # ==========================================
    # Keyword search
    # ==========================================

    for keyword in keywords:

        should_clauses.append({
            "multi_match": {
                "query": keyword,
                "fields": search_fields,
                "type": "best_fields",
                "fuzziness": "AUTO"
            }
        })

    # ==========================================
    # SFDC exact search
    # ==========================================

    if is_sfdc_search:

        must_clauses.append({
            "term": {
                "sfdc_id": focus_keyword
            }
        })

    query = {
        "query": {
            "bool": {
                "must": must_clauses,
                "should": should_clauses,
                "minimum_should_match": 1 if should_clauses else 0
            }
        },
        "size": limit
    }

    return query

