# ==============================
# Standard Library
# ==============================
import random
import string
from typing import List
from datetime import datetime

# ==============================
# Internal Modules
# ==============================
from helper.models import HistoryData, HistoryAddInfoData
from core.db import get_async_db

#=================================================================


# Function to upload history data
async def push_history_data(history_data: List[HistoryData]):
    try:
        # Get database connection
        async with get_async_db("rw") as conn:
            async with conn.transaction():
                for data in history_data:
                    await conn.execute(
                        """
                        INSERT INTO history_table (
                            username, question_id, question, risk_id, stakeholder, timestamp, keyword
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7
                        )
                        """,
                        data.username, data.ques_id, data.question, data.risk_id, data.stakeholder, data.timestamp, data.keyword
                    )

            return {"success": True, "message": "Risk data uploaded successfully"}

    except Exception as e:
        print("❌ ERROR push_history_data:", repr(e))  # 🔥 use repr
        return {"success": False, "message": str(e)}
    
# Function to upload history data
async def push_history_addinfo_data(history_add_data: List[HistoryAddInfoData]):
    try:
        # Get database connection
        async with get_async_db("rw") as conn:
            async with conn.transaction():
                for data in history_add_data:
                    await conn.execute(
                        """
                        INSERT INTO history_addinfo_table (
                            username, question_id, question, risk_title, risk_description, risk_category, risk_root_cause, risk_impact, risk_mitigation, timestamp, keyword
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
                        )
                        """,
                        data.username, data.ques_id, data.question, data.risk_title, data.risk_description, data.risk_category, data.risk_root_cause, data.risk_impact, data.risk_mitigation, data.timestamp, data.keyword
                    )

            return {"success": True, "message": "Risk data uploaded successfully"}

    except Exception as e:
        return {"success": False, "message": str(e)}
    
async def generate_question_id():
    async with get_async_db("rw") as conn:
        date_str = datetime.now().strftime("%y%m%d")  # YYMMDD format
        
        while True:
            # Generate 5 candidate IDs at once
            candidate_ids = {f"QR-HQ{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}-{date_str}" for _ in range(5)}
            
            # Check which IDs already exist
            existing_ids = await conn.fetch("SELECT question_id FROM history_addinfo_table WHERE question_id = ANY($1)", list(candidate_ids))
            existing_ids = {row["question_id"] for row in existing_ids}

            await conn.close()
            # Find the first unique ID
            unique_ids = candidate_ids - existing_ids
            if unique_ids:
                return unique_ids.pop()  # Return the first available unique ID

