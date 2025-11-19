"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.api_analysis import router as analysis
from api.api_log import router as log
from api.api_system import router as system
from api.api_task import router as task
from api.api_upload import router as upload
from middleware.db_middleware import DBSessionMiddleware

app = FastAPI(
    title="LMeterX Backend API",
    description="LMeterX Backend",
    version="1.0.0",
)

# Add database middleware
app.add_middleware(DBSessionMiddleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
app.include_router(system, prefix="/api/system", tags=["system"])
app.include_router(task, prefix="/api/tasks", tags=["tasks"])
app.include_router(log, prefix="/api/logs", tags=["logs"])
app.include_router(upload, prefix="/api/upload", tags=["upload"])

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=5001, workers=2, reload=True)
