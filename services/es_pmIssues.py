# ==============================
# Standard Library
# ==============================
import json

# ==============================
# Third-Party Libraries
# ==============================
from core.es_client import es

from helper.InstructionAI import get_issues_keywords, get_pm_keywords, get_sc_keywords

async def get_issues(question):
    try:
        # 1. Generate ES query from LLM
        query, keywords= get_sc_keywords(question)

        # 2. Execute Elasticsearch query
        result = es.search(
            index="sc_risk",
            body=query
        )

        # 3. Extract data
        hits = result.get("hits", {}).get("hits", [])
        data = [hit["_source"] for hit in hits]

        return {
            "data": data,
            "keywords": keywords,
            "query": query
        }

    except Exception as e:
        return{
            "success": False,
            "message": str(e),
            "status": 500,
            "query": query
        }