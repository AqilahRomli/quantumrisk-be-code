# ==============================
# Standard Library
# ==============================
from datetime import datetime
from dateutil.relativedelta import relativedelta

# ==============================
# Third-Party Libraries
# ==============================
from cryptography.fernet import InvalidToken

# ==============================
# Internal Modules
# ==============================
from core.db import get_async_db
from core.security import encrypt, decrypt


#Number of user per department   
async def count_registered_user():
    try:
        async with get_async_db("r") as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(DISTINCT CASE 
                        WHEN access = 'User' AND user_role = 'RAC-User' THEN username 
                    END) AS rac_user_count,
                    COUNT(DISTINCT CASE 
                        WHEN access = 'User' AND user_role IN ('PM-Admin', 'PM-User') THEN username
                    END) AS pm_user_count,
                    COUNT(DISTINCT CASE 
                        WHEN access = 'User' AND user_role IN ('SC-Admin', 'SC-User') THEN username 
                    END) AS sc_user_count,
                    COUNT(DISTINCT CASE 
                        WHEN access = 'User' AND user_role = 'BTSM-User' THEN username 
                    END) AS btsm_user_count,
                    COUNT(DISTINCT CASE 
                        WHEN access = 'User' THEN username 
                    END) AS total_user_count,
                    COUNT(DISTINCT CASE 
                        WHEN access = 'Developer' THEN username 
                    END) AS developer_count,
                    (
                SELECT COUNT(DISTINCT ult.username)
                FROM user_login_track ult
                JOIN risk_user_table rut
                    ON ult.username = rut.username
                WHERE rut.access <> 'Developer'
                ) AS user_login,
                    (SELECT COUNT(DISTINCT name) FROM pm_members) AS pm_members_count,
                    (SELECT COUNT(DISTINCT name) FROM sc_members) AS sc_members_count
                FROM risk_user_table;

                """
            )
            return {
                "total": row["total_user_count"],
                "pm_user": row["pm_user_count"],
                "sc_user": row["sc_user_count"],
                "rac_user": row["rac_user_count"],
                "btsm_user": row["btsm_user_count"],
                "user_login": row["user_login"],
                "pm_expected_user": row["pm_members_count"],
                "sc_expected_user": row["sc_members_count"]
            }
    except Exception as e:
        return {"success": False, "message": str(e)}
    

#Get Total Risk PM Risk + SC Risk, Issues and Lesson Learnt
async def get_Risk_LL_Issues():
    try:
        async with get_async_db("r") as conn:
            row = await conn.fetchrow(
                """
                SELECT
                -- Risks
                (SELECT COUNT(DISTINCT risk_id) FROM sc_risk_table) AS sc_risk,
                (SELECT COUNT(DISTINCT risk_id) FROM pm_risk_table) AS pm_risk,
                (
                    (SELECT COUNT(DISTINCT risk_id) FROM sc_risk_table) +
                    (SELECT COUNT(DISTINCT risk_id) FROM pm_risk_table)
                ) AS total_risk,

                -- Lesson Learned
                (SELECT COUNT(DISTINCT ll_id) FROM lesson_learn) AS total_ll,

                -- Issues
                (SELECT COUNT(DISTINCT issue_id) FROM pm_issues) AS total_issues;
                """
            )
            return {
                "total_risk": row["total_risk"],
                "total_pm_risk": row["pm_risk"],
                "total_sc_risk": row["sc_risk"],
                "total_pm_issues": row["total_issues"],
                "total_pm_ll": row["total_ll"],
            }
    except Exception as e:
        return {"success": False, "message": str(e)}


#Get Year to Date (YTD) of User Activity
async def get_ytd_User_Activity():
    try:
        async with get_async_db("r") as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(DISTINCT CASE 
                        WHEN rut.user_role IN ('PM-User', 'PM-Admin') THEN hat.username
                    END) AS pm_question_id,
                    COUNT(DISTINCT CASE 
                        WHEN rut.user_role IN ('SC-User', 'SC-Admin') THEN hat.username 
                    END) AS sc_question_id
                FROM history_addinfo_table hat
                JOIN risk_user_table rut 
                    ON hat.username = rut.username
                WHERE rut.user_role <> 'Admin'
                AND rut.user_role <> 'RAC-User'
                AND rut.user_role <> 'BTSM-User'
                AND rut.access <> 'Developer'
                """
            )
            return {
                "pm_activity": row["pm_question_id"],
                "sc_activity": row["sc_question_id"],
            }
    except Exception as e:
        return {"success": False, "message": str(e)}


#Get User Activity Monthly
async def get_User_Activity_monthly():
    try:
        async with get_async_db("r") as conn:
            rows = await conn.fetch(
                """
                SELECT
                    DATE_TRUNC('month', hat.timestamp) AS month_value,
                    COUNT(DISTINCT CASE 
                        WHEN rut.user_role IN ('PM-User', 'PM-Admin') THEN hat.username  
                    END) AS pm_question_id,
                    COUNT(DISTINCT CASE 
                        WHEN rut.user_role IN ('SC-User', 'SC-Admin') THEN hat.username 
                    END) AS sc_question_id
                FROM history_addinfo_table hat
                JOIN risk_user_table rut 
                    ON hat.username = rut.username
                WHERE rut.user_role NOT IN ('Admin', 'RAC-User', 'BTSM-User')
                AND rut.access <> 'Developer'
                GROUP BY month_value
                ORDER BY month_value
                """
            )

            result = []

            for row in rows:
                dt: datetime = row["month_value"]   # this is a datetime object

                result.append({
                    "month": dt.strftime("%Y-%m"),
                    "pm_activity": row["pm_question_id"],
                    "sc_activity": row["sc_question_id"],
                })

            return {"success": True, "data": result}

    except Exception as e:
        return {"success": False, "message": str(e)}


#Get Proposal Registered Monthly
async def get_proposal_created_monthly():
    try:
        async with get_async_db("r") as conn:
            rows = await conn.fetch(
                """
                SELECT
                    DATE_TRUNC('month', spt.created_at) AS month_value,
                    COUNT(DISTINCT CASE 
                        WHEN spt.status = 'Draft' THEN spt.proposal_id 
                    END) AS draft_proposal,
                    COUNT(DISTINCT CASE 
                        WHEN spt.status = 'Complete' THEN spt.proposal_id 
                    END) AS complete_proposal
                FROM sc_proposal_table spt 
                GROUP BY month_value
                ORDER BY month_value;
                """
            )

            result = []

            for row in rows:
                dt: datetime = row["month_value"]   # this is a datetime object

                result.append({
                    "month": dt.strftime("%Y-%m"),
                    "draft_proposal": row["draft_proposal"],
                    "complete_proposal": row["complete_proposal"],
                })

            return {"success": True, "data": result}

    except Exception as e:
        return {"success": False, "message": str(e)}
   

# Get Popular Keywords
async def get_top10_Keywords():
    try:
        async with get_async_db("r") as conn:
            rows = await conn.fetch(
                """
                SELECT
                    LOWER(TRIM(k.keyword)) AS keyword,
                    COUNT(*) AS total_count
                FROM (
                    SELECT DISTINCT question_id, unnest(string_to_array(keyword, ',')) AS keyword
                    FROM history_table
                ) AS k
                WHERE k.keyword <> ''  -- ignore empty keywords
                GROUP BY LOWER(TRIM(k.keyword))
                ORDER BY total_count DESC
                LIMIT 10
                """
            )
            
            # Convert result to list of dicts
            return [
                {"keyword": row["keyword"], "count": row["total_count"]}
                for row in rows
            ]
        
    except Exception as e:
        return {"success": False, "message": str(e)}


#get User per department
async def get_user_per_department(user_role: str):
    try:
        async with get_async_db("r") as conn:
            # Define role expansion mapping
            role_mapping = {
                "SC-User": ["SC-User", "SC-Admin"],
                "PM-User": ["PM-User", "PM-Admin"],
            }

            if user_role == "all":
                rows = await conn.fetch(
                    """
                    SELECT id, username, user_role, name, email, staff_id, division
                    FROM risk_user_table
                    WHERE user_role <> 'Admin'
                    AND access <> 'Developer'
                    """,
                )
            elif user_role in role_mapping:
                roles = role_mapping[user_role]
                rows = await conn.fetch(
                    """
                    SELECT id, username, user_role, name, email, staff_id, division
                    FROM risk_user_table
                    WHERE user_role = ANY($1::text[])
                    AND access <> 'Developer'
                    """,
                    roles,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, username, user_role, name, email, staff_id, division
                    FROM risk_user_table
                    WHERE user_role = $1
                    AND access <> 'Developer'
                    """,
                    user_role
                )
            result = []

            for row in rows:
                row = dict(row)

                for field in ["name", "email", "staff_id"]:
                    try:
                        if row.get(field):
                            row[field] = decrypt(row[field])
                    except InvalidToken:
                        pass

                result.append(row)

            return result

    except Exception as e:
        return {"success": False, "message": str(e)}


#get activity per user per month
async def get_activity_per_user(user_role: str):
    try:
        async with get_async_db("r") as conn:
            # Define role expansion mapping
            role_mapping = {
                "SC-User": ["SC-User", "SC-Admin"],
                "PM-User": ["PM-User", "PM-Admin"],
            }

            if (user_role == 'all'):
                rows = await conn.fetch(
                """
                SELECT
                    rut.username,
                    rut.name,
                    rut.email,
                    rut.user_role,
                    COUNT(DISTINCT hat.question_id) AS activity_count
                FROM history_addinfo_table hat
                JOIN risk_user_table rut
                    ON hat.username = rut.username
                WHERE rut.user_role NOT IN ('Admin', 'RAC-User', 'BTSM-User')
                AND rut.access <> 'Developer'
                GROUP BY
                    rut.username,
                    rut.name,
                    rut.email,
                    rut.user_role
                ORDER BY activity_count DESC;
                """,
            )
            elif user_role in role_mapping:
                roles = role_mapping[user_role]
                rows = await conn.fetch(
                    """
                    SELECT
                        rut.username,
                        rut.name,
                        rut.email,
                        rut.user_role,
                        COUNT(DISTINCT hat.question_id) AS activity_count
                    FROM history_addinfo_table hat
                    JOIN risk_user_table rut
                        ON hat.username = rut.username
                    WHERE rut.user_role = ANY($1::text[])
                    AND rut.access <> 'Developer'
                    GROUP BY
                        rut.username,
                        rut.name,
                        rut.email,
                        rut.user_role
                    ORDER BY activity_count DESC;
                    """,
                    roles
                )

            else:
                rows = await conn.fetch(
                    """
                    SELECT
                        rut.username,
                        rut.name,
                        rut.email,
                        rut.user_role,
                        COUNT(DISTINCT hat.question_id) AS activity_count
                    FROM history_addinfo_table hat
                    JOIN risk_user_table rut
                        ON hat.username = rut.username
                    WHERE rut.user_role = $1
                    AND rut.access <> 'Developer'
                    GROUP BY
                        rut.username,
                        rut.name,
                        rut.email,
                        rut.user_role
                    ORDER BY activity_count DESC;
                    """,
                    user_role
                )

            result = []  # final list of dicts

            for row in rows:
                row = dict(row)  # ✅ convert immutable Record → mutable dict

                # Decrypt safely
                for field in ["name", "email"]:
                    try:
                        if row.get(field):
                            row[field] = decrypt(row[field])
                    except InvalidToken:
                        pass

                result.append(row)

            return result

    except Exception as e:
        return {"success": False, "message": str(e)}


#get activity per user per month
async def get_activity_per_month_detail(
    user_role: str,
    month: str  # format: YYYY-MM (e.g. "2025-10")
):
    try:
        # Parse month
        start_date = datetime.strptime(month, "%Y-%m")
        end_date = start_date + relativedelta(months=1)

        async with get_async_db("r") as conn:
            # Define role expansion mapping
            role_mapping = {
                "SC-User": ["SC-User", "SC-Admin"],
                "PM-User": ["PM-User", "PM-Admin"],
            }

            base_query = """
                SELECT
                    DATE_TRUNC('month', hat.timestamp) AS month_value,
                    rut.username,
                    rut.name,
                    rut.email,
                    rut.user_role,
                    COUNT(DISTINCT hat.question_id) AS activity_count
                FROM history_addinfo_table hat
                JOIN risk_user_table rut
                    ON hat.username = rut.username
                WHERE
                    rut.user_role NOT IN ('Admin', 'RAC-User', 'BTSM-User')
                    AND rut."access" <> 'Developer'
                    AND hat.timestamp >= $1
                    AND hat.timestamp < $2
            """

            params = [start_date, end_date]

            if user_role not in ("SC-User", "PM-User"):        # ✅ fix 1: && → 'not in'
                base_query += " AND rut.user_role = $3"
                params.append(user_role)
            else:                                               # ✅ fix 2: missing colon
                roles = role_mapping[user_role]
                base_query += " AND rut.user_role = ANY($3::text[])"  # ✅ fix 3: $1 → $3
                params.append(roles)

            base_query += """
                GROUP BY
                    month_value,
                    rut.username,
                    rut.name,
                    rut.email,
                    rut.user_role
                ORDER BY activity_count DESC
            """

            rows = await conn.fetch(base_query, *params)

            result = []
            for row in rows:
                row = dict(row)

                # Decrypt fields safely
                for field in ["name", "email"]:
                    try:
                        if row.get(field):
                            row[field] = decrypt(
                                row[field])
                    except InvalidToken:
                        pass

                result.append(row)

            return {
                "success": True,
                "data": result,
                "month": month
            }

    except Exception as e:
        return {"success": False, "message": str(e)}


#get proposal list per status
async def get_proposal_list_per_status(status: str):
    try:
        async with get_async_db("r") as conn:
            rows = await conn.fetch(
            """
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
            WHERE spt.status = $1
            """, status
            )
            result = []  # final list of dicts

            for row in rows:
                row = dict(row)  # ✅ convert immutable Record → mutable dict

                # Decrypt safely
                for field in ["name", "email"]:
                    try:
                        if row.get(field):
                            row[field] = decrypt(row[field])
                    except InvalidToken:
                        pass

                result.append(row)

            return result

    except Exception as e:
        return {"success": False, "message": str(e)}


#get proposal list per month
async def get_proposal_per_month(
    status: str,
    month: str  # format: YYYY-MM (e.g. "2025-10")
):
    try:
        # Parse month
        start_date = datetime.strptime(month, "%Y-%m")
        end_date = start_date + relativedelta(months=1)

        async with get_async_db("r") as conn:
            base_query = """
                SELECT
                    DATE_TRUNC('month', spt.created_at) AS month_created,
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
                WHERE spt.created_at >= $1
                AND spt.created_at < $2
            """

            params = [start_date, end_date]

            if status != "all":
                base_query += " AND spt.status = $3"
                params.append(status)
            
            rows = await conn.fetch(base_query, *params)

            result = []
            for row in rows:
                row = dict(row)

                # Decrypt fields safely
                for field in ["name", "email"]:
                    try:
                        if row.get(field):
                            row[field] = decrypt(
                                row[field])
                    except InvalidToken:
                        pass

                result.append(row)

            return {
                "success": True,
                "data": result,
                "month": month
            }

    except Exception as e:
        return {"success": False, "message": str(e)}


async def list_risk():
    try:
        async with get_async_db("r") as conn:
            sc_risk = await conn.fetch(
                """
                SELECT 
                    srt.customer,
                    srt.project_name,
                    srt.sfdc_id,
                    srt.risk_category,
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

            pm_risk = await conn.fetch(
                """
                SELECT 
                    prt.customer_name,
                    prt.project_name,
                    prt.opportunity_id,
                    prt.project_vertical ,
                    prt.project_type ,
                    prt.risk_category,
                    prt.specific_risk,
                    prt.risk_event,
                    prt.risk_root_cause,
                    prt.risk_impact,
                    prt.likelihood_level,
                    prt.likelihood_justification,
                    prt.impact_level,
                    prt.impact_justification,
                    prt.risk_rating,
                    prt.risk_mitigation_plan ,
                    prt.risk_mitigation_control_owner_group 
                FROM pm_risk_table prt 
                """
            )

            return {
                "success": True,
                "total_scrisk": len(sc_risk),   # ✅ number of rows
                "data_scrisk": sc_risk,
                "total_pmrisk": len(pm_risk),   # ✅ number of rows
                "data_pmrisk": pm_risk
            }

    except Exception as e:
        return {"success": False, "message": str(e)}


#get User Login Track
async def get_user_login_track():
    try:
        async with get_async_db("r") as conn:
            rows = await conn.fetch(
            """
            SELECT
                ult.id,
                ult.username,
                ult.email,
                rut.name,
                rut.user_role,
                ult.login_time
            FROM user_login_track ult 
            LEFT JOIN risk_user_table rut
                ON ult.username = rut.username
            WHERE rut."access" <> 'Developer'
            ORDER BY ult.login_time ASC;
            """,
            )

            result = []  # final list of dicts

            for row in rows:
                row = dict(row)  # ✅ convert immutable Record → mutable dict

                # Decrypt safely
                for field in ["name"]:
                    try:
                        if row.get(field):
                            row[field] = decrypt(row[field])
                    except InvalidToken:
                        pass

                # ✅ Format login_time
                if row.get("login_time"):
                    row["login_time"] = row["login_time"].strftime("%Y-%m-%d %H:%M:%S")

                result.append(row)

            return result

    except Exception as e:
        return {"success": False, "message": str(e)}


#get lesson learn list
async def list_lesson_learn():
    try:
        async with get_async_db("r") as conn:
            lesson_learn = await conn.fetch(
                """
                SELECT 
                    ll.customer_name,
                    ll.project_name,
                    ll.sfdc_opportunity_id,
                    ll.sfdc_segment,
                    ll.category,
                    ll.challenge,
                    ll.resolution,
                    ll.lesson_learned,
                    ll.stakeholder_pic
                FROM lesson_learn ll 
                """
            )

            return {
                "success": True,
                "total_lessonlearn": len(lesson_learn),   # ✅ number of rows
                "data_lessonlearn": lesson_learn,
            }
        
    except Exception as e:
        return {"success": False, "message": str(e)}


#get list Issues
async def list_Issues():
    try:
        async with get_async_db("r") as conn:
            issues = await conn.fetch(
                """
                SELECT 
                    pi2.project_type,
                    pi2.project_complexity,
                    pi2.issue_description,
                    pi2.issue_reason,
                    pi2.issue_owner,
                    pi2.issue_action_plan,
                    pi2.issue_impacted_deliverables_milestone,
                    pi2.issue_resolution 
                FROM pm_issues pi2
                """
            )

            return {
                "success": True,
                "total_issues": len(issues),   # ✅ number of rows
                "data_issues": issues,
            }

    except Exception as e:
        return {"success": False, "message": str(e)}


#get list Non Register and Registered Member
async def get_registered_non_registered(department: str, type: str):
    try:
        async with get_async_db("r") as conn:
            # 1. Resolve table + role filter dynamically
            member_table = "pm_members" if department == "PM" else "sc_members"
            role_filter = (
                "user_role = 'PM-User'"
                if department == "PM"
                else "user_role IN ('SC-Admin', 'SC-User')"
            )
            # 2. Get member list
            member_rows = await conn.fetch(
                f"""
                SELECT name
                FROM {member_table};
                """
            )
            # Keep both original + normalized
            members = [
                {
                    "original": row["name"],
                    "normalized": row["name"].strip().lower()
                }
                for row in member_rows if row["name"]
            ]
            # 3. Get risk users
            risk_rows = await conn.fetch(
                f"""
                SELECT name
                FROM risk_user_table
                WHERE access = 'User' AND {role_filter};
                """
            )
            # 4. Decrypt + normalize
            risk_name_set = set()
            for row in risk_rows:
                try:
                    if row["name"]:
                        decrypted = decrypt(row["name"])
                        risk_name_set.add(decrypted.strip().lower())
                except InvalidToken:
                    continue
            # 5. Compare + build FE-friendly result
            registered = []
            non_registered = []
            for member in members:
                item = {
                    "name": member["original"],   # ✅ display name
                    "is_registered": member["normalized"] in risk_name_set
                }
                if item["is_registered"]:
                    registered.append(item)
                else:
                    non_registered.append(item)
            # 6. Return based on type
            if type == "registered":
                data = registered
            elif type == "non_registered":
                data = non_registered
            else:
                return {
                    "success": False,
                    "message": "Invalid type. Use 'registered' or 'non_registered'"
                }
            return {
                "success": True,
                "type": type,
                "count": len(data),
                "data": data
            }
        
    except Exception as e:
        return {"success": False, "message": str(e)}
    
    