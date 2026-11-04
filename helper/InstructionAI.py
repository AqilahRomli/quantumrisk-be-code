# ==============================
# Standard Library
# ==============================
import re
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
llm = ChatOpenAI(temperature=0, openai_api_key=settings.OPENAI_API_KEY, model='gpt-4o-mini', request_timeout=120)

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
