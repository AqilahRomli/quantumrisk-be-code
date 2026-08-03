# ==============================
# Standard Library
# ==============================
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List

# ==============================
# Third-Party Libraries
# ==============================
from psycopg2.extras import RealDictCursor

from fastapi import HTTPException

# ==============================
# Internal Modules
# ==============================
from core.db import get_db
from core.security import decrypt

# ====================================================================

def get_grouped_history(username: str):
    try:
        with get_db("r") as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Date boundaries
            today = datetime.now().date()
            yesterday = today - timedelta(days=1)
            seven_days_ago = today - timedelta(days=7)

            query = """
            SELECT DISTINCT username, question_id, question, timestamp
            FROM history_addinfo_table
            WHERE username = %s
            ORDER BY timestamp DESC;
            """

            cursor.execute(query, (username,))
            rows = cursor.fetchall()

            # Initialize groups
            grouped = {
                "today": [],
                "yesterday": [],
                "last7Days": [],
                "older": []
            }

            for row in rows:
                # Convert and format timestamp
                original_ts = row["timestamp"]
                if original_ts:
                    local_ts = original_ts.astimezone(ZoneInfo("Asia/Kuala_Lumpur"))
                    row["timestamp"] = local_ts.isoformat()  # or use .strftime('%Y-%m-%d %H:%M:%S')

                    # Use the date part for grouping
                    record_date = local_ts.date()
                else:
                    record_date = None

                # Group by date
                if record_date == today:
                    grouped["today"].append(row)
                elif record_date == yesterday:
                    grouped["yesterday"].append(row)
                elif seven_days_ago < record_date < yesterday:
                    grouped["last7Days"].append(row)
                else:
                    grouped["older"].append(row)

            cursor.close()

            return grouped

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch history: {str(e)}")


def individual_delete_history(question_id:str, username: str):
    try:
        with get_db("rw") as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Delete from history_table
            cursor.execute("""
                DELETE FROM history_table
                WHERE question_id = %s AND username = %s
            """, (question_id, username))
            deleted_main = cursor.rowcount

            # Delete from history_addinfo_table
            cursor.execute("""
                DELETE FROM history_addinfo_table
                WHERE question_id = %s AND username = %s
            """, (question_id, username))
            deleted_addinfo = cursor.rowcount

            conn.commit()
            cursor.close()

            # Return True if at least one deletion occurred
            return deleted_main > 0 or deleted_addinfo > 0
    
    except Exception as e:
        raise Exception(f"Database error during delete: {str(e)}")


def bulk_delete_history(question_ids: List[str], username: str) -> int:
    try:
        with get_db("rw") as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Use tuple for SQL IN clause
            format_ids = tuple(question_ids)

            # Delete from both tables
            cursor.execute("""
                DELETE FROM history_table
                WHERE question_id IN %s AND username = %s
            """, (format_ids, username))
            deleted_main = cursor.rowcount

            cursor.execute("""
                DELETE FROM history_addinfo_table
                WHERE question_id IN %s AND username = %s
            """, (format_ids, username))
            deleted_addinfo = cursor.rowcount

            conn.commit()
            cursor.close()

            return deleted_main + deleted_addinfo
    except Exception as e:
        raise Exception(f"Bulk delete failed: {str(e)}")


def get_history_data(question_id:str, username: str):
    try:
        with get_db("r") as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Step 1: Get add_info
            cursor.execute("""
                SELECT question_id, risk_title, risk_description, risk_category, 
                    risk_root_cause, risk_impact, risk_mitigation  
                FROM history_addinfo_table 
                WHERE question_id = %s AND username = %s
            """, (question_id, username))
            add_info = cursor.fetchall()

            # Step 2: Get risk_ids with stakeholders
            cursor.execute("""
                SELECT risk_id, stakeholder 
                from history_table
                WHERE question_id = %s AND username = %s
            """, (question_id, username))
            history_entries = cursor.fetchall()

            # Step 3: Group risk_ids by stakeholder
            stakeholder_risks = {"PM": [], "SC": [], "lesson_learn": [], "Issue": []}
            for entry in history_entries:
                stakeholder = entry["stakeholder"]
                risk_id = entry["risk_id"]
                if stakeholder in stakeholder_risks:
                    stakeholder_risks[stakeholder].append(risk_id)

            # Step 4: Query PM risk data
            pm_data = []
            if stakeholder_risks["PM"]:
                format_ids = tuple(stakeholder_risks["PM"])
                cursor.execute("""
                    SELECT stakeholder, customer_name, project_name, project_vertical, 
                        project_type, risk_id, risk_category, specific_risk, risk_event,
                        risk_root_cause, risk_impact, likelihood_level, 
                        likelihood_justification, impact_level, impact_justification, 
                        risk_rating, risk_mitigation_plan, risk_mitigation_control_owner_group
                    FROM pm_risk_table
                    WHERE risk_id IN %s
                """, (format_ids,))
                pm_data = cursor.fetchall()

            # Step 5: Query SC risk data
            sc_data = []
            if stakeholder_risks["SC"]:
                format_ids = tuple(stakeholder_risks["SC"])
                cursor.execute("""
                    SELECT stakeholder, risk_id, customer, project_name, vertical, 
                        project_description, product_service_offering, risk_category, 
                        risk_desc, risk_event, root_cause, risk_impact, likelihood, 
                        likelihood_justification, impact, impact_justification, 
                        risk_rating, key_mitigation, residual_risk_rating, control_owner
                    FROM sc_risk_table
                    WHERE risk_id IN %s
                """, (format_ids,))
                sc_data = cursor.fetchall()

            # Step 6: Query Lesson Learnt data
            ll_data = []
            if stakeholder_risks["lesson_learn"]:
                format_ids = tuple(stakeholder_risks["lesson_learn"])
                cursor.execute("""
                    SELECT ll_id, sfdc_opportunity_id, customer_name, project_name,
                        sfdc_segment, lead_project_manager, achiement_improvement,
                        category, challenge, resolution, lesson_learned, stakeholder_pic,
                        segment
                    FROM lesson_learn
                    WHERE ll_id IN %s
                """, (format_ids,))
                ll_data = cursor.fetchall()

            # Step 6: Query PM Issue data
            issue_data = []
            if stakeholder_risks["Issue"]:
                format_ids = tuple(stakeholder_risks["Issue"])
                cursor.execute("""
                    SELECT issue_id, customer_segment, project_type, project_complexity,
                        issue_description, issue_reason, issue_owner,
                        issue_action_plan, issue_help_needed, issue_impacted_deliverables_milestone, 
                        issue_resolution
                    FROM pm_issues
                    WHERE issue_id IN %s
                """, (format_ids,))
                issue_data = cursor.fetchall()

            cursor.close()

            return {
                "pm_data": pm_data,
                "sc_data": sc_data,
                "add_info": add_info,
                "ll_data": ll_data,
                "issue_data": issue_data
            }

    except Exception as e:
        raise Exception(f"Database error during delete: {str(e)}")


#Test for decrypt sensitive data
def get_forcase_value():
    try:
        with get_db("r") as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            query = """
            SELECT risk_id, total_forecasted_revenue_sfdc_current
            FROM pm_risk_table
            limit 1
            """

            cursor.execute(query)
            rows = cursor.fetchall()

            cursor.close()

            # Decrypt the value before returning
            for row in rows:
                encrypted = row["total_forecasted_revenue_sfdc_current"]
                if encrypted:
                    try:
                        decrypted = decrypt(encrypted)
                        row["total_forecasted_revenue_sfdc_current"] = decrypted
                    except Exception:
                        row["total_forecasted_revenue_sfdc_current"] = "DECRYPTION_ERROR"

            return rows

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch history: {str(e)}")
