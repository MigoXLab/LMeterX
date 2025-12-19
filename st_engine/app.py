"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import threading
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from db.database import init_db
from service.poller import (
    common_task_create_poller,
    common_task_stop_poller,
    task_create_poller,
    task_stop_poller,
)
from utils.logger import logger


def start_polling():
    """Initializes and starts the background polling threads for task management."""
    logger.info("Starting polling threads...")
    task_create_thread = threading.Thread(
        target=task_create_poller, daemon=True, name="TaskCreatePollerThread"
    )
    task_stop_thread = threading.Thread(
        target=task_stop_poller, daemon=True, name="TaskStopPollerThread"
    )
    common_task_create_thread = threading.Thread(
        target=common_task_create_poller,
        daemon=True,
        name="CommonTaskCreatePollerThread",
    )
    common_task_stop_thread = threading.Thread(
        target=common_task_stop_poller,
        daemon=True,
        name="CommonTaskStopPollerThread",
    )
    task_create_thread.start()
    task_stop_thread.start()
    common_task_create_thread.start()
    common_task_stop_thread.start()
    logger.info("Polling threads started successfully.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Asynchronous context manager to handle application startup and shutdown events.
    """
    # Executed on application startup
    logger.info("Performance testing engine is starting up...")

    # Initialize the database with a retry mechanism
    db_initialized = False
    max_retries = 5
    retry_count = 0
    while not db_initialized and retry_count < max_retries:
        try:
            init_db()
            logger.info(
                "Database connection and SessionLocal initialized successfully."
            )
            db_initialized = True
        except Exception as e:
            retry_count += 1
            logger.error(
                f"Database initialization failed (Attempt {retry_count}/{max_retries}): {e}"
            )
            if retry_count < max_retries:
                logger.info("Retrying in 30 seconds...")
                time.sleep(30)
            else:
                logger.error(
                    "Maximum database initialization retries reached. Engine will exit."
                )
                # Propagate the exception to fail the application startup
                raise e

    if db_initialized:
        # Start background polling tasks if the database is initialized
        start_polling()

    yield

    # Executed on application shutdown
    logger.info("Performance testing engine is shutting down.")


app = FastAPI(lifespan=lifespan)


@app.get("/health", summary="Health Check", tags=["Monitoring"])
async def health_check():
    """
    Provides a health check endpoint to verify that the service is running.
    Returns a simple JSON response indicating the status.
    """
    return {"status": "ok"}


if __name__ == "__main__":
    logger.info("Starting server with Uvicorn...")

    uvicorn.run("app:app", host="127.0.0.1", port=5002, reload=True)
