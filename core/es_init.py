from elasticsearch import Elasticsearch
import time

es = Elasticsearch("http://localhost:9200")

from elasticsearch import Elasticsearch
import time

es = Elasticsearch("http://localhost:9200")

# ==================================================
# INDEX CONFIGURATIONS
# ==================================================

INDEXES = {

    "pm_issues": {
        "mappings": {
            "properties": {
                "issue_id": {"type": "keyword"},
                "customer_segment": {"type": "text"},
                "project_type": {"type": "text"},
                "project_complexity": {"type": "text"},
                "issue_description": {"type": "text"},
                "issue_reason": {"type": "text"},
                "issue_owner": {"type": "text"},
                "issue_action_plan": {"type": "text"},
                "issue_help_needed": {"type": "text"},
                "issue_impacted_deliverables_milestone": {"type": "text"},
                "issue_resolution": {"type": "text"},
            }
        }
    },

    "pm_risk": {
        "mappings": {
            "properties": {
                "stakeholder": {"type": "text"},
                "customer_name": {"type": "text"},
                "project_name": {"type": "text"},
                "project_vertical": {"type": "text"},
                "project_type": {"type": "text"},
                "risk_id": {"type": "keyword"},
                "risk_category": {"type": "text"},
                "specific_risk": {"type": "text"},
                "risk_event": {"type": "text"},
                "risk_root_cause": {"type": "text"},
                "risk_impact": {"type": "text"},
                "likelihood_level": {"type": "text"},
                "likelihood_justification": {"type": "text"},
                "impact_level": {"type": "text"},
                "impact_justification": {"type": "text"},
                "risk_rating": {"type": "text"},
                "risk_mitigation_plan": {"type": "text"},
                "risk_mitigation_control_owner_group": {"type": "text"},
                "opportunity_id": {"type": "keyword"},
            }
        }
    },

    "sc_risk": {
        "mappings": {
            "properties": {
                "stakeholder": {"type": "text"},
                "risk_id": {"type": "keyword"},
                "customer": {"type": "text"},
                "project_name": {"type": "text"},
                "vertical": {"type": "text"},
                "project_description": {"type": "text"},
                "product_service_offering": {"type": "text"},
                "risk_category": {"type": "text"},
                "risk_desc": {"type": "text"},
                "risk_event": {"type": "text"},
                "root_cause": {"type": "text"},
                "risk_impact": {"type": "text"},
                "likelihood": {"type": "text"},
                "likelihood_justification": {"type": "text"},
                "impact": {"type": "text"},
                "impact_justification": {"type": "text"},
                "risk_rating": {"type": "text"},
                "key_mitigation": {"type": "text"},
                "residual_risk_rating": {"type": "text"},
                "control_owner": {"type": "text"},
                "sfdc_id": {"type": "keyword"}
            }
        }
    }

}

# ==================================================
# CREATE INDEX FUNCTION
# ==================================================

def create_indexes():

    # wait for ES ready
    for _ in range(10):
        try:
            if es.ping():
                print("✅ Elasticsearch connected")
                break
        except:
            time.sleep(2)

    # create all indexes
    for index_name, mapping in INDEXES.items():

        if not es.indices.exists(index=index_name):

            es.indices.create(
                index=index_name,
                body=mapping
            )

            print(f"✅ Index created: {index_name}")

        else:
            print(f"✔️ Index already exists: {index_name}")