# ==============================
# Third-Party Libraries
# ==============================
from cryptography.fernet import Fernet, InvalidToken

# ==============================
# Internal Modules
# ==============================
from core.db import get_async_db
from core.security import encrypt, decrypt

#Number of Proposal
async def count_proposal():
    try:
        async with get_async_db("r") as conn:
            row = await conn.fetchrow("""
                SELECT
                    COUNT(DISTINCT proposal_id) AS total_proposals,
                    COUNT(DISTINCT proposal_id) FILTER (WHERE status = 'Draft') AS draft_count,
                    COUNT(DISTINCT proposal_id) FILTER (WHERE status = 'Complete') AS complete_count
                FROM sc_proposal_table;
            """)

            return {
                "total": row["total_proposals"],
                "draft": row["draft_count"],
                "complete": row["complete_count"]
            }

    except Exception as e:
        return {"success": False, "message": str(e)}
          
#Number of Risk and project   
async def count_risk_project():
    try:
        async with get_async_db("r") as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(DISTINCT risk_id) AS total_risk,
                    COUNT(DISTINCT project_name) AS total_project
                FROM sc_risk_table;
                """
            )

            proposal_registered = await conn.fetchrow(
                """
                SELECT
                    COUNT(DISTINCT spt.proposal_id) AS registered_proposal
                FROM sc_proposal_table spt ;
                """
            )
            return {
                "risk": row["total_risk"],
                "project": row["total_project"],
                "proposal": proposal_registered["registered_proposal"]
            }
        
    except Exception as e:
        return {"success": False, "message": str(e)}   

#Number of Proposal   
async def count_proposal_perUser():
    try:
        async with get_async_db("r") as conn:
            rows = await conn.fetch(
                """
                SELECT
                    created_by,
                    COUNT(DISTINCT proposal_id) AS complete_count
                FROM sc_proposal_table
                WHERE status = 'Complete'
                GROUP BY created_by
                ORDER BY complete_count DESC;
                """
            )

            # Build a list of results
            result = []
            for row in rows:
                result.append({
                    "user": row["created_by"],
                    "complete": row["complete_count"]
                })

            return {"success": True, "data": result}

    except Exception as e:
        return {"success": False, "message": str(e)}

# Top 10 User Proposal Page
async def topten_sc_user():
    try:
        async with get_async_db("r") as conn:
            rows = await conn.fetch(
                """
                SELECT
                    sp.created_by,
                    ru.name AS full_name,
                    SUM(CASE WHEN sp.status = 'Draft' THEN 1 ELSE 0 END) AS draft_count,
                    SUM(CASE WHEN sp.status = 'Complete' THEN 1 ELSE 0 END) AS complete_count,
                    COUNT(*) AS total_proposals
                FROM sc_proposal_table sp
                JOIN risk_user_table ru
                  ON sp.created_by = ru.username  -- adjust if it's ru.id instead
                WHERE sp.status IN ('Draft', 'Complete')
                GROUP BY sp.created_by, ru.name
                ORDER BY complete_count DESC
                LIMIT 10;
                """
            )

            # Build a list of results
            result = []
            for row in rows:
                full_name = row["full_name"]
                try:
                    if full_name:
                        full_name = decrypt(full_name)
                except InvalidToken:
                    # Value is plain text, not encrypted
                    pass

                result.append({
                    "user": row["created_by"],
                    "name": full_name,
                    "draft": row["draft_count"],
                    "complete": row["complete_count"],
                    "total": row["total_proposals"]
                })

            return {"success": True, "data": result}

    except Exception as e:
        return {"success": False, "message": str(e)}


async def list_sc_risk():
    try:
        async with get_async_db("r") as conn:
            rows = await conn.fetch(
                """
                SELECT 
                    srt.customer,
                    srt.project_name,
                    srt.sfdc_id,
                    srt.risk_event,
                    srt.root_cause,
                    srt.risk_impact,
                    srt.risk_category,
                    srt.likelihood,
                    srt.likelihood_justification,
                    srt.impact,
                    srt.impact_justification,
                    srt.risk_rating,
                    srt.key_mitigation,
                    srt.residual_risk_rating,
                    srt.control_owner
                FROM sc_risk_table srt
                """
            )

            return {
                "success": True,
                "total": len(rows),   # ✅ number of rows
                "data": rows
            }
        
    except Exception as e:
        return {"success": False, "message": str(e)}
 