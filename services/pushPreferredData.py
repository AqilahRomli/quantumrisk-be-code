# ==============================
# Standard Library
# ==============================
from typing import List

# ==============================
# Internal Modules
# ==============================
from helper.models import PMRiskData, SCRiskData
from core.db import get_async_db



# Function to upload prefer PM risk data
async def push_PM_preferred_risk(pm_risk_data: List[PMRiskData]):
    try:
        async with get_async_db("rw") as conn:
            async with conn.transaction():
                for data in pm_risk_data:
                    # Check for existing risk_id
                    existing = await conn.fetchval(
                        "SELECT 1 FROM pm_prefer_data WHERE risk_id = $1",
                        data.risk_id
                    )
                    if existing:
                        continue  # Skip if exists

                    await conn.execute(
                        """
                        INSERT INTO pm_prefer_data (
                            stakeholder, customer_name, project_name, project_vertical, project_type, risk_id, 
                            risk_category, specific_risk, risk_event, risk_root_cause,
                            risk_impact, likelihood_level, likelihood_justification,  
                            impact_level, impact_justification, risk_rating, risk_mitigation_plan, 
                            risk_mitigation_control_owner_group
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18
                        )
                        """,
                        data.stakeholder, data.customer_name, data.project_name, data.project_vertical, 
                        data.project_type, data.risk_id, data.risk_category, data.specific_risk, data.risk_event,
                        data.risk_root_cause, data.risk_impact, data.likelihood_level, data.likelihood_justification, 
                        data.impact_level, data.impact_justification, data.risk_rating, data.risk_mitigation_plan,
                        data.risk_mitigation_control_owner_group
                    )

            return {"success": True, "message": "PM risk data uploaded (skipped duplicates)"}
    except Exception as e:
        return {"success": False, "message": str(e)}

    
# Function to upload prefer SC risk data
async def push_SC_preferred_risk(sc_risk_data: List[SCRiskData]):
    try:
        async with get_async_db("rw") as conn:
            async with conn.transaction():
                for data in sc_risk_data:
                    # Check for existing risk_id
                    existing = await conn.fetchval(
                        "SELECT 1 FROM sc_prefer_data WHERE risk_id = $1",
                        data.risk_id
                    )
                    if existing:
                        continue  # Skip if exists

                    await conn.execute(
                        """
                        INSERT INTO sc_prefer_data (
                            stakeholder, risk_id, customer, project_name, vertical,
                            project_description, product_service_offering, risk_category,
                            risk_desc, risk_event, root_cause, risk_impact, likelihood, likelihood_justification,
                            impact, impact_justification, risk_rating, key_mitigation,
                            residual_risk_rating, control_owner
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20
                        )
                        """,
                        data.stakeholder, data.risk_id, data.customer, data.project_name, data.vertical,
                        data.project_description, data.product_service_offering, data.risk_category,
                        data.risk_desc, data.risk_event, data.risk_impact, data.root_cause, data.likelihood, data.likelihood_justification,
                        data.impact, data.impact_justification, data.risk_rating, data.key_mitigation,
                        data.residual_risk_rating, data.control_owner
                    )

            await conn.close()
            return {"success": True, "message": "SC risk data uploaded (skipped duplicates)"}
    except Exception as e:
        return {"success": False, "message": str(e)}
