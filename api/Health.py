# ==============================
# Standard Library
# ==============================
import os
import asyncio

# ==============================
# Third-Party Libraries
# ==============================
import psycopg2

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

# ==============================
# Internal Modules
# ==============================
from core import db
from core.config import settings

router = APIRouter()

CHECK_TIMEOUT_SECONDS = 5


# Run "SELECT 1" through one of the application connection pools
async def check_pool(mode: str) -> str:
    try:
        async def ping():
            async with db.get_async_db(mode) as conn:
                await conn.fetchval("SELECT 1")

        await asyncio.wait_for(ping(), timeout=CHECK_TIMEOUT_SECONDS)
        return "ok"
    except Exception as e:
        print(f"[health] database ({mode}) check failed: {repr(e)}")
        return "failed"


# Log in as the restricted AI search user and confirm it can read a search table
def check_search_user() -> str:
    if not settings.DB_SEARCH_USER:
        return "not configured"

    connection = None
    try:
        connection = psycopg2.connect(
            host=settings.DB_HOST,
            user=settings.DB_SEARCH_USER,
            password=settings.DB_SEARCH_PASSWORD,
            database=settings.DB_NAME,
            port=settings.DB_PORT_R,
            connect_timeout=CHECK_TIMEOUT_SECONDS
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pm_risk_table LIMIT 1")
            cursor.fetchall()
        return "ok"
    except Exception as e:
        print(f"[health] search user check failed: {repr(e)}")
        return "failed"
    finally:
        if connection is not None:
            connection.close()


# ##################################################################################### #
# Check the backend after a deployment: is it running and can it reach the database?   #
# No login needed. It returns no data, only "ok" / "failed" for each check.            #
# 200 = everything ok, 503 = at least one check failed (details are in the server log) #
# ##################################################################################### #
@router.get("/health/")
async def health_check():
    checks = {
        "database_read_write": await check_pool("rw"),
        "database_read": await check_pool("r"),
        "search_user": await run_in_threadpool(check_search_user),
    }

    healthy = "failed" not in checks.values()

    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "success": healthy,
            "status": 200 if healthy else 503,
            "message": "Backend is running and connected to the database" if healthy else "Backend is running but a check failed",
            "data": {
                "environment": os.getenv("APP_ENV") or "local",
                "password_login": "enabled" if settings.PASSWORD_LOGIN_ENABLED else "disabled",
                "checks": checks,
            }
        }
    )
