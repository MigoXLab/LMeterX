"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import threading
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from db.database import get_db_session, init_db
from service.heartbeat import (
    ensure_heartbeat_table,
    heartbeat_and_reconcile_loop,
    update_heartbeat,
)
from service.poller import (
    http_task_create_poller,
    http_task_stop_poller,
    llm_task_create_poller,
    llm_task_stop_poller,
)
from utils.logger import logger
from utils.resource_collector import start_resource_collector, stop_resource_collector


def start_polling():
    """Initializes and starts the background polling threads for task management."""
    logger.info("Starting polling threads...")
    llm_task_create_thread = threading.Thread(
        target=llm_task_create_poller, daemon=True, name="LlmTaskCreatePollerThread"
    )
    llm_task_stop_thread = threading.Thread(
        target=llm_task_stop_poller, daemon=True, name="LlmTaskStopPollerThread"
    )
    http_task_create_thread = threading.Thread(
        target=http_task_create_poller,
        daemon=True,
        name="HttpTaskCreatePollerThread",
    )
    http_task_stop_thread = threading.Thread(
        target=http_task_stop_poller,
        daemon=True,
        name="HttpTaskStopPollerThread",
    )
    heartbeat_thread = threading.Thread(
        target=heartbeat_and_reconcile_loop,
        daemon=True,
        name="HeartbeatReconcileThread",
    )
    llm_task_create_thread.start()
    llm_task_stop_thread.start()
    http_task_create_thread.start()
    http_task_stop_thread.start()
    heartbeat_thread.start()
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
        # Ensure heartbeat table exists and write the initial heartbeat
        # so that peer engines (and subsequent reconciliation) see us as alive
        # BEFORE any poller starts its own startup reconciliation.
        try:
            ensure_heartbeat_table()
            with get_db_session() as session:
                update_heartbeat(session)
            logger.info("Engine heartbeat initialised successfully.")
        except Exception as e:
            logger.warning(f"Failed to initialise engine heartbeat (non-fatal): {e}")

        # Start background polling tasks if the database is initialized
        start_polling()

    # Start system resource collector (pushes CPU/Memory/Network to VictoriaMetrics)
    try:
        start_resource_collector()
        logger.info("System resource collector started successfully.")
    except Exception as e:
        logger.warning(f"Failed to start resource collector (non-fatal): {e}")

    yield

    # Executed on application shutdown
    logger.info("Performance testing engine is shutting down.")
    try:
        stop_resource_collector()
    except Exception as e:
        logger.debug(f"Ignored error stopping resource collector during shutdown: {e}")


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
