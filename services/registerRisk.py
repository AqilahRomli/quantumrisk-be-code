# ==============================
# Standard Library
# ==============================
import random
import string
from datetime import datetime
from typing import List

# ==============================
# Third-Party Libraries
# ==============================
from cryptography.fernet import InvalidToken

# ==============================
# Internal Modules
# ==============================
from helper.models import RiskDetail
from core.db import get_async_db
from core.security import encrypt, decrypt


async def generate_risk_id(conn):
    date_str = datetime.now().strftime("%y%m%d")  # YYMMDD format
    
    while True:
        # Generate 5 candidate IDs at once
        candidate_ids = {f"SCRR-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}-{date_str}" for _ in range(5)}
        
        # Check which IDs already exist
        existing_ids = await conn.fetch("SELECT risk_id FROM sc_risk_register_table WHERE risk_id = ANY($1)", list(candidate_ids))
        existing_ids = {row["risk_id"] for row in existing_ids}

        # Find the first unique ID
        unique_ids = candidate_ids - existing_ids
        if unique_ids:
            return unique_ids.pop()  # Return the first available unique ID
     

async def generate_proposal_id(conn):
    date_str = datetime.now().strftime("%y%m%d")  # YYMMDD format
    
    while True:
        # Generate 5 candidate IDs at once
        candidate_ids = {f"SCPT-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}-{date_str}" for _ in range(5)}
        
        # Check which IDs already exist
        existing_ids = await conn.fetch("SELECT proposal_id FROM sc_proposal_table WHERE proposal_id = ANY($1)", list(candidate_ids))
        existing_ids = {row["proposal_id"] for row in existing_ids}

        # Find the first unique ID
        unique_ids = candidate_ids - existing_ids
        if unique_ids:
            return unique_ids.pop()  # Return the first available unique ID


# Function to upload risk data
async def register_risk(customer, projectName, risk_data: List[RiskDetail], username):
    try:
        # Get database connection
        async with get_async_db("rw") as conn:
            risk_ids = []

            async with conn.transaction():
                proposal_id = await generate_proposal_id(conn)
                await conn.execute(
                    """
                    INSERT INTO sc_proposal_table (
                        proposal_id, customer, proposal_title, status, created_by
                    ) VALUES ($1, $2, $3, $4, $5)
                    """,
                    proposal_id, customer, projectName, "Draft", username
                )

                for data in risk_data:
                    # Generate unique risk ID
                    risk_id = await generate_risk_id(conn)

                    # Insert into sc_risk_register_table
                    await conn.execute(
                        """
                        INSERT INTO sc_risk_register_table (
                            risk_id,
                            proposal_id,
                            customer,
                            project_name,
                            gm_name,
                            agm_name,
                            manager_name,
                            assistant_manager_name,
                            vertical,
                            sfdc_id,
                            project_description,
                            product_service_offering,
                            custom_product_components,
                            risk_category,
                            risk_event,
                            root_cause,
                            risk_impact,
                            likelihood,
                            likelihood_justification,
                            impact,
                            impact_justification,
                            risk_rating,
                            key_mitigation,
                            residual_risk_rating,
                            control_owner
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                            $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25
                        )
                        """,
                        risk_id, proposal_id, data.customer_name, data.project_name, data.gm_name, data.agm_name,
                        data.manager_name, data.assistant_manager_name, data.vertical, data.sfdc_id,
                        data.project_description, data.product_service_offering, data.custom_product_components, data.risk_category,
                        data.risk_event, data.root_cause, data.risk_impact, data.likelihood, data.likelihood_justification,
                        data.impact, data.impact_justification, data.risk_rating, data.key_mitigation,
                        data.residual_risk_rating, data.control_owner
                    )

                    risk_ids.append(risk_id)


            return {"success": True, "message": "Risk data registration successfully"}

    except Exception as e:
        return {"success": False, "message": str(e)}


#Get proposal List
async def proposal_list(username: str):
    try:
        async with get_async_db("r") as conn:
            rows = await conn.fetch("SELECT * FROM sc_proposal_table WHERE created_by = $1", username)
            proposals = [dict(row) for row in rows]  # Convert to list of dictionaries
            return proposals
    except Exception as e:
        return {"success": False, "message": str(e)}
    

#Get proposal List for Admin / SC Admin
async def proposal_list_Admin(username: str = None, status: str = None, created_by: str = None, reset: bool = False):
    try:
        async with get_async_db("r") as conn:
            # Build the base query
            query = """
                SELECT
                    spt.proposal_id,
                    spt.customer,
                    spt.proposal_title,
                    spt.status,
                    spt.created_by,
                    spt.updated_at,
                    rut.name
                FROM sc_proposal_table spt
                JOIN risk_user_table rut 
                  ON spt.created_by = rut.username
                WHERE 1=1
            """
            params = []

            # Apply filters (only if not reset)
            if not reset and created_by:
                if isinstance(created_by, str):
                    created_by = [created_by]

                placeholders = ", ".join(f"${i+1}" for i in range(len(created_by)))
                query += f" AND spt.created_by IN ({placeholders})"
                params.extend(created_by)

            # Add GROUP BY + ORDER BY after filters
            query += """
                GROUP BY spt.created_by, rut.name, spt.customer, spt.proposal_title, spt.status, spt.updated_at, spt.proposal_id
            """

            rows = await conn.fetch(query, *params)

            proposals = []
            for row in rows:
                row_dict = dict(row)

                # Try decrypting the name
                try:
                    if row_dict.get("name"):
                        row_dict["name"] = decrypt(row_dict["name"])
                except InvalidToken:
                    # If not encrypted, leave as is
                    pass

                proposals.append(row_dict)

            return {"success": True, "data": proposals}
        
    except Exception as e:
        return {"success": False, "message": str(e)}


# Get proposal List for Admin / SC Admin
async def top_user_list_Admin(username: str = None, created_by: str = None, reset: bool = False):
    try:
        async with get_async_db("r") as conn:
            # Build the base query
            query = """
                SELECT
                    sp.created_by,
                    ru.name AS full_name,
                    SUM(CASE WHEN sp.status = 'Draft' THEN 1 ELSE 0 END) AS draft_count,
                    SUM(CASE WHEN sp.status = 'Complete' THEN 1 ELSE 0 END) AS complete_count,
                    COUNT(*) AS total_proposals,
                    MAX(sp.updated_at) AS last_updated
                FROM sc_proposal_table sp
                JOIN risk_user_table ru
                  ON sp.created_by = ru.username  -- adjust if it's ru.id instead
                WHERE 1=1
            """
            params = []

            # Apply filters (only if not reset)
            if not reset and created_by:
                if isinstance(created_by, str):
                    created_by = [created_by]

                placeholders = ", ".join(f"${i+1}" for i in range(len(created_by)))
                query += f" AND sp.created_by IN ({placeholders})"
                params.extend(created_by)

            # Add GROUP BY + ORDER BY after filters
            query += """
                GROUP BY sp.created_by, ru.name
                ORDER BY complete_count DESC
            """

            rows = await conn.fetch(query, *params)

            proposals = []
            for row in rows:
                row_dict = dict(row)

                # Try decrypting the name
                try:
                    if row_dict.get("full_name"):
                        row_dict["full_name"] = decrypt(row_dict["full_name"])
                except InvalidToken:
                    # If not encrypted, leave as is
                    pass

                proposals.append(row_dict)

            return {"success": True, "data": proposals}
        
    except Exception as e:
        return {"success": False, "message": str(e)}

# Combined API: Get summary + proposals per user
async def proposal_summary_with_list(created_by: str = None, status: str = None, reset: bool = False):
    try:
        async with get_async_db("r") as conn:
            # -------------------------------
            # 1. Query for summary (user totals)
            # -------------------------------
            summary_query = """
                SELECT
                    sp.created_by,
                    ru.name AS full_name,
                    SUM(CASE WHEN sp.status = 'Draft' THEN 1 ELSE 0 END) AS draft_count,
                    SUM(CASE WHEN sp.status = 'Complete' THEN 1 ELSE 0 END) AS complete_count,
                    COUNT(*) AS total_proposals,
                    MAX(sp.updated_at) AS last_updated
                FROM sc_proposal_table sp
                JOIN risk_user_table ru
                  ON sp.created_by = ru.username
                WHERE 1=1
            """
            params = []

            if not reset and created_by:
                # if isinstance(created_by, str):
                #     created_by = [created_by]

                placeholders = ", ".join(f"${i+1}" for i in range(len(created_by)))
                summary_query += f" AND sp.created_by IN ({placeholders})"
                params.extend(created_by)

            if not reset and status:
                summary_query += f" AND sp.status = ${len(params) + 1}"
                params.append(status)

            summary_query += """
                GROUP BY sp.created_by, ru.name
                ORDER BY complete_count DESC
            """

            summary_rows = await conn.fetch(summary_query, *params)

            # -------------------------------
            # 2. Query for detailed proposals
            # -------------------------------
            proposal_query = """
                SELECT
                    spt.proposal_id,
                    spt.customer,
                    spt.proposal_title,
                    spt.status,
                    spt.created_by,
                    spt.updated_at,
                    rut.name
                FROM sc_proposal_table spt
                JOIN risk_user_table rut 
                  ON spt.created_by = rut.username
                WHERE 1=1
            """
            proposal_params = []

            if not reset and created_by:
                placeholders = ", ".join(f"${i+len(proposal_params)+1}" for i in range(len(created_by)))
                proposal_query += f" AND spt.created_by IN ({placeholders})"
                proposal_params.extend(created_by)

            if not reset and status:
                proposal_query += f" AND spt.status = ${len(proposal_params) + 1}"
                proposal_params.append(status)

            proposal_rows = await conn.fetch(proposal_query, *proposal_params)

            # -------------------------------
            # 3. Organize proposals by created_by
            # -------------------------------
            proposals_by_user = {}
            for row in proposal_rows:
                row_dict = dict(row)
                try:
                    if row_dict.get("name"):
                        row_dict["name"] = decrypt(row_dict["name"])
                except InvalidToken:
                    pass

                proposals_by_user.setdefault(row_dict["created_by"], []).append(row_dict)

            # -------------------------------
            # 4. Merge summaries with proposals
            # -------------------------------
            result = []
            for row in summary_rows:
                row_dict = dict(row)
                try:
                    if row_dict.get("full_name"):
                        row_dict["full_name"] = decrypt(row_dict["full_name"])
                except InvalidToken:
                    pass

                row_dict["proposal"] = proposals_by_user.get(row_dict["created_by"], [])
                result.append(row_dict)

            return {"success": True, "data": result}
        
    except Exception as e:
        return {"success": False, "message": str(e)}


#Number of Pending Proposal   
async def pending_proposal(username: str):
    try:
        async with get_async_db("r") as conn:
            row = await conn.fetchrow(
                """
                SELECT COUNT(DISTINCT proposal_id) AS count
                FROM sc_proposal_table
                WHERE status = 'Draft' AND created_by = $1
                """,
                username
            )
            # Return as a simple dict like {"count": 3}
            return {"count": row["count"]}
    except Exception as e:
        return {"success": False, "message": str(e)}


async def proposal_details(proposalId: str):
    try:
        async with get_async_db("r") as conn:
            # Query proposal information (assuming only one row per proposal_id)
            proposal_row = await conn.fetchrow(
                """
                SELECT 
                    srt.customer, 
                    srt.project_name, 
                    srt.gm_name, 
                    srt.agm_name, 
                    srt.manager_name, 
                    srt.assistant_manager_name, 
                    srt.vertical, 
                    srt.sfdc_id, 
                    srt.project_description, 
                    srt.product_service_offering, 
                    srt.custom_product_components, 
                    spt.created_by,
                    spt.updated_at
                FROM 
                    sc_risk_register_table srt
                JOIN sc_proposal_table spt 
                ON srt.proposal_id = spt.proposal_id
                WHERE srt.proposal_id  = $1 LIMIT 1
                """, proposalId
            )

            if not proposal_row:
                return {"success": False, "message": "Proposal not found"}
            
            created_by = await conn.fetchrow(
                """
                SELECT 
                    rut."name"
                FROM 
                    risk_user_table rut 
                WHERE rut.username   = $1 LIMIT 1
                """, proposal_row['created_by']
            )

            if created_by and created_by["name"]:
                name_value = created_by["name"]
                try:
                    # Try to decrypt
                    name_creator = decrypt(name_value)
                except Exception:
                    # If decryption fails, assume it's already plain text
                    name_creator = name_value
            else:
                name_creator = None

            proposal_status = await conn.fetchrow(
                """
                SELECT 
                    spt2.status
                FROM 
                    sc_proposal_table spt2 
                WHERE spt2.proposal_id   = $1 LIMIT 1
                """, proposalId
            )
                
            # Query associated risks
            risk_rows = await conn.fetch(
                "SELECT risk_id, proposal_id, risk_category, risk_event, root_cause, risk_impact, likelihood, likelihood_justification, impact, impact_justification, risk_rating, key_mitigation, residual_risk_rating, control_owner FROM sc_risk_register_table WHERE proposal_id = $1", proposalId
            )

            # Format risk data
            risks = [dict(risk) for risk in risk_rows]

            # Format proposal data
            proposal_data = dict(proposal_row)

            # Split product_service_offering string into a list
            if "product_service_offering" in proposal_data:
                product_string = proposal_data["product_service_offering"]
                proposal_data["product_service_offering"] = [
                    item.strip() for item in product_string.split(",") if item.strip()
                ]
            
            proposal_data["created_by_name"] = name_creator
            proposal_data["status"] = proposal_status["status"]

            return {
                "success": True,
                "proposal": proposal_data,
                "risks": risks
            }
        
    except Exception as e:
        return {"success": False, "message": str(e)}

# Function to update Proposal Details
async def update_proposal(proposalId: str, customer: str, projectName: str, risk_data: List[RiskDetail], username: str):
    try:
        async with get_async_db("rw") as conn:
            risk_ids = []

            async with conn.transaction():
                # 1. Check if proposal exists
                existing = await conn.fetchrow(
                    "SELECT 1 FROM sc_proposal_table WHERE proposal_id = $1",
                    proposalId
                )
                if not existing:
                    return {"success": False, "message": f"Proposal ID '{proposalId}' does not exist"}

                # 2. Optional: Update proposal detail
                await conn.execute(
                    """
                    UPDATE sc_proposal_table 
                    SET customer = $1, proposal_title = $2, created_by = $3, updated_at = NOW()
                    WHERE proposal_id = $4
                    """,
                    customer, projectName, username, proposalId
                )

                # 3. Delete all related risks
                await conn.execute(
                    "DELETE FROM sc_risk_register_table WHERE proposal_id = $1",
                    proposalId
                )

                # 4. Re-insert updated risk data
                for data in risk_data:
                    risk_id = await generate_risk_id(conn)

                    # Check if CUSTOM_PRODUCT is in product_service_offering
                    custom_components = data.custom_product_components
                    if 'CUSTOM_PRODUCT' not in data.product_service_offering:
                        custom_components = None  # or '' if your DB prefers empty string

                    await conn.execute(
                        """
                        INSERT INTO sc_risk_register_table (
                            risk_id,
                            proposal_id,
                            customer,
                            project_name,
                            gm_name,
                            agm_name,
                            manager_name,
                            assistant_manager_name,
                            vertical,
                            sfdc_id,
                            project_description,
                            product_service_offering,
                            custom_product_components,
                            risk_category,
                            risk_event,
                            root_cause,
                            risk_impact,
                            likelihood,
                            likelihood_justification,
                            impact,
                            impact_justification,
                            risk_rating,
                            key_mitigation,
                            residual_risk_rating,
                            control_owner
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                            $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25
                        )
                        """,
                        risk_id, proposalId, data.customer_name, data.project_name, data.gm_name, data.agm_name,
                        data.manager_name, data.assistant_manager_name, data.vertical, data.sfdc_id,
                        data.project_description, data.product_service_offering, custom_components, data.risk_category,
                        data.risk_event, data.root_cause, data.risk_impact, data.likelihood, data.likelihood_justification,
                        data.impact, data.impact_justification, data.risk_rating, data.key_mitigation,
                        data.residual_risk_rating, data.control_owner
                    )

                    risk_ids.append(risk_id)

            return {"success": True, "message": "Proposal and risks updated successfully"}

    except Exception as e:
        return {"success": False, "message": str(e)}


async def delete_proposal(proposalId: str, username: str):
    try:
        async with get_async_db("rw") as conn:
            await conn.execute(
                """
                DELETE FROM sc_proposal_table
                WHERE proposal_id = $1 AND created_by = $2
                """,
                proposalId, username
            )

            return {"success": True, "message": "Proposal successfully deleted"}

    except Exception as e:
        return {"success": False, "message": str(e)}


# Function to Insert risk data into SC_RISK_TABLE
async def Post_submitRisk(proposalId, customer, projectName, risk_data: List[RiskDetail], username):
    try:
        async with get_async_db("rw") as conn:
            risk_ids = []

            async with conn.transaction():
                # 1. Check if proposal exists
                existing = await conn.fetchrow(
                    "SELECT 1 FROM sc_proposal_table WHERE proposal_id = $1",
                    proposalId
                )
                if not existing:
                    return {"success": False, "message": f"Proposal ID '{proposalId}' does not exist"}

                # 2. Optional: Update proposal detail
                await conn.execute(
                    """
                    UPDATE sc_proposal_table 
                    SET customer = $1, proposal_title = $2, status = $3, created_by = $4, updated_at = NOW()
                    WHERE proposal_id = $5
                    """,
                    customer, projectName, "Complete", username, proposalId
                )

                # 3. Delete all related risks
                await conn.execute(
                    "DELETE FROM sc_risk_register_table WHERE proposal_id = $1",
                    proposalId
                )

                # 4. Re-insert updated risk data
                for data in risk_data:
                    risk_id = await generate_risk_id(conn)

                    # Split string to list for checking
                    product_list = data.product_service_offering.split(', ')

                    # Clear custom components if CUSTOM_PRODUCT not present
                    custom_components = data.custom_product_components
                    if 'CUSTOM_PRODUCT' not in product_list:
                        custom_components = None

                    # Build combined product string for sc_risk_table
                    offerings = []
                    for item in product_list:
                        if item == 'CUSTOM_PRODUCT' and custom_components:
                            offerings.append(f'{item} (Components: {custom_components})')
                        else:
                            offerings.append(item)
                    combined_product_service = ', '.join(offerings)

                    await conn.execute(
                        """
                        INSERT INTO sc_risk_register_table (
                            risk_id,
                            proposal_id,
                            customer,
                            project_name,
                            gm_name,
                            agm_name,
                            manager_name,
                            assistant_manager_name,
                            vertical,
                            sfdc_id,
                            project_description,
                            product_service_offering,
                            custom_product_components,
                            risk_category,
                            risk_event,
                            root_cause,
                            risk_impact,
                            likelihood,
                            likelihood_justification,
                            impact,
                            impact_justification,
                            risk_rating,
                            key_mitigation,
                            residual_risk_rating,
                            control_owner
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                            $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25
                        )
                        """,
                        risk_id, proposalId, data.customer_name, data.project_name, data.gm_name, data.agm_name,
                        data.manager_name, data.assistant_manager_name, data.vertical, data.sfdc_id,
                        data.project_description, data.product_service_offering, custom_components, data.risk_category,
                        data.risk_event, data.root_cause, data.risk_impact, data.likelihood, data.likelihood_justification,
                        data.impact, data.impact_justification, data.risk_rating, data.key_mitigation,
                        data.residual_risk_rating, data.control_owner
                    )

                    await conn.execute(
                        """
                        INSERT INTO sc_risk_table (
                            stakeholder,
                            risk_id,
                            customer,
                            project_name,
                            gm_name,
                            agm_name,
                            manager_name,
                            assistant_manager_name,
                            vertical,
                            sfdc_id,
                            project_description,
                            product_service_offering,
                            risk_category,
                            risk_event,
                            root_cause,
                            risk_impact,
                            likelihood,
                            likelihood_justification,
                            impact,
                            impact_justification,
                            risk_rating,
                            key_mitigation,
                            residual_risk_rating,
                            control_owner
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                            $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24
                        )
                        """,
                        "SC", risk_id, data.customer_name, data.project_name, data.gm_name, data.agm_name,
                        data.manager_name, data.assistant_manager_name, data.vertical, data.sfdc_id,
                        data.project_description, combined_product_service, data.risk_category,
                        data.risk_event, data.root_cause, data.risk_impact, data.likelihood, data.likelihood_justification,
                        data.impact, data.impact_justification, data.risk_rating, data.key_mitigation,
                        data.residual_risk_rating, data.control_owner
                    )


                    risk_ids.append(risk_id)

            return {"success": True, "message": "Proposal and risks updated successfully"}

    except Exception as e:
        return {"success": False, "message": str(e)}
