
# ==============================
# Third-Party Libraries
# ==============================
from fastapi import (
    HTTPException,
    Request,
)
from fastapi.responses import JSONResponse

# ==========================================================================


# exception class
class HTTPException(HTTPException):
    def __init__(self, status_code: int, detail: str, headers=None):
        super().__init__(status_code, detail=detail, headers=headers)


# exception handler
def exception_404_handler(request: Request, exc: HTTPException):
    return JSONResponse(content=exc.json_response, status_code=exc.status_code)
