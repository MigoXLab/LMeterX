"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.api_analysis import router as analysis
from api.api_auth import router as auth
from api.api_common_task import router as common_task
from api.api_log import router as log
from api.api_system import router as system
from api.api_task import router as task
from api.api_upload import router as upload
from middleware.auth_middleware import AuthMiddleware
from middleware.db_middleware import DBSessionMiddleware
from utils.auth_settings import get_auth_settings
from utils.error_handler import ErrorResponse
from utils.logger import logger

app = FastAPI(
    title="LMeterX Backend API",
    description="LMeterX Backend",
    version="1.0.0",
)

auth_settings = get_auth_settings()
DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:80",
    "http://127.0.0.1:80",
]
allowed_origins = DEFAULT_ALLOWED_ORIGINS.copy()
# Allow overriding via env (comma-separated list)
custom_origins = getattr(auth_settings, "ALLOWED_ORIGINS", None)
if isinstance(custom_origins, str) and custom_origins.strip():
    allowed_origins = [
        origin.strip() for origin in custom_origins.split(",") if origin.strip()
    ]


@app.exception_handler(ErrorResponse)
async def handle_service_error(_: Request, exc: ErrorResponse):
    """Return a unified response body for all ErrorResponse exceptions."""
    return exc.to_response()


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException):
    """
    Log and return standard HTTP errors (e.g., validation 422) without
    leaking stack traces.
    """
    logger.warning(
        "HTTP error %s on %s %s: %s",
        exc.status_code,
        request.method,
        request.url.path,
        exc.detail,
    )
    return JSONResponse(status_code=exc.status_code, content=exc.detail)


@app.exception_handler(Exception)
async def handle_unexpected_exception(request: Request, exc: Exception):
    """Catch-all for unexpected errors with structured logging."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return ErrorResponse.internal_server_error().to_response()


@app.middleware("http")
async def add_backend_marker(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-LMeterX-Backend"] = "1"
    return response


# Add auth middleware (exclude health and login) only when LDAP is enabled.
# Tests set TESTING=1 to avoid auth when running locally.
if auth_settings.LDAP_ENABLED and not os.getenv("TESTING"):
    app.add_middleware(
        AuthMiddleware,
        exempt_paths={"/health", "/", "/api/auth/login", "/api/auth/logout"},
    )

# Add database middleware
app.add_middleware(DBSessionMiddleware)

# Add CORS middleware only when needed (browser access)
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return JSONResponse(content={"status": "healthy", "service": "backend"})


@app.get("/")
def read_root():
    """Root endpoint."""
    return {"message": "LMeterX Backend API"}


# add api routers
app.include_router(analysis, prefix="/api/analyze", tags=["analysis"])
app.include_router(auth, prefix="/api/auth", tags=["auth"])
app.include_router(system, prefix="/api/system", tags=["system"])
app.include_router(task, prefix="/api/tasks", tags=["tasks"])
app.include_router(common_task, prefix="/api/common-tasks", tags=["common-tasks"])
app.include_router(log, prefix="/api/logs", tags=["logs"])
app.include_router(upload, prefix="/api/upload", tags=["upload"])

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=5001, workers=2, reload=True)
