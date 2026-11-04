# ==============================
# Third-Party Libraries
# ==============================
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from fastapi.responses import JSONResponse

# ==============================
# Internal Modules
# ==============================
from core.db import init_async_db
from helper.permissions import warn_roles_without_permissions

from api import UserAuth, RiskManagement, ProposalDash, ReportingDash, HistoryManagement, Health, SSOAuthentication

# Bearer token authentication
bearer = HTTPBearer()

app = FastAPI()


# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    "http://localhost",
    "http://localhost:8080", 
    "http://localhost:4200",
    "http://localhost:4300",
],
    allow_credentials=True,
    allow_methods=["*"],  # You can restrict HTTP methods as needed (e.g., ["GET", "POST"])
    allow_headers=["*"],  # You can restrict headers as needed
)

@app.on_event("startup")
async def startup():
    await init_async_db()
    await warn_roles_without_permissions()


# Error Handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "status": exc.status_code,
            "detail": exc.detail,
            # e.g. "PERMISSION_DENIED" (helper/permissions.py), so the frontend can tell it apart
            **({"code": exc.code} if getattr(exc, "code", None) else {})
        }
    )

# Routers
app.include_router(UserAuth.router)
app.include_router(RiskManagement.router)
app.include_router(ProposalDash.router)
app.include_router(ReportingDash.router)
app.include_router(HistoryManagement.router)

# OV to QR SSO Authentication API
app.include_router(
    SSOAuthentication.router,
    prefix="/auth"
)
app.include_router(Health.router)
