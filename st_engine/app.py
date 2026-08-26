"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os
import threading
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from utils.logger import logger
from utils.resource_collector import start_resource_collector, stop_resource_collector

ENGINE_MODE = os.getenv("ENGINE_MODE", "api")


def start_polling_db_mode():
    """Deprecated: Legacy mode that polls MySQL directly. Use ENGINE_MODE=api instead."""
    from db.database import get_db_session, init_db
    from service.heartbeat import (
        ensure_heartbeat_table,
        heartbeat_and_reconcile_loop,
        update_heartbeat,
    )
    from service.poller import (
        http_task_create_poller,
        http_task_enqueue_poller,
        http_task_stop_poller,
        llm_task_create_poller,
        llm_task_enqueue_poller,
        llm_task_stop_poller,
    )

    db_initialized = False
    max_retries = 5
    retry_count = 0
    while not db_initialized and retry_count < max_retries:
        try:
            init_db()
            logger.info("Database connection initialized successfully.")
            db_initialized = True
        except Exception as e:
            retry_count += 1
            logger.error(
                f"Database initialization failed (Attempt {retry_count}/{max_retries}): {e}"
            )
            if retry_count < max_retries:
                time.sleep(30)
            else:
                raise e

    if db_initialized:
        try:
            ensure_heartbeat_table()
            with get_db_session() as session:
                update_heartbeat(session)
            logger.info("Engine heartbeat initialised successfully.")
        except Exception as e:
            logger.warning(f"Failed to initialise engine heartbeat (non-fatal): {e}")

        logger.info("Starting DB polling threads...")
        threads = [
            threading.Thread(
                target=llm_task_enqueue_poller,
                daemon=True,
                name="LlmTaskEnqueuePollerThread",
            ),
            threading.Thread(
                target=llm_task_create_poller,
                daemon=True,
                name="LlmTaskCreatePollerThread",
            ),
            threading.Thread(
                target=llm_task_stop_poller, daemon=True, name="LlmTaskStopPollerThread"
            ),
            threading.Thread(
                target=http_task_enqueue_poller,
                daemon=True,
                name="HttpTaskEnqueuePollerThread",
            ),
            threading.Thread(
                target=http_task_create_poller,
                daemon=True,
                name="HttpTaskCreatePollerThread",
            ),
            threading.Thread(
                target=http_task_stop_poller,
                daemon=True,
                name="HttpTaskStopPollerThread",
            ),
            threading.Thread(
                target=heartbeat_and_reconcile_loop,
                daemon=True,
                name="HeartbeatReconcileThread",
            ),
        ]
        for t in threads:
            t.start()
        logger.info("DB polling threads started successfully.")


def start_polling_api_mode():
    """New mode: Engine communicates with Backend via HTTP REST API."""
    from service.api_poller import (
        api_heartbeat_loop,
        api_log_push_loop,
        api_stop_poller,
        api_task_poller,
        startup_register,
    )

    registered = False
    max_retries = 10
    for attempt in range(max_retries):
        if startup_register():
            registered = True
            break
        logger.warning(
            f"Registration attempt {attempt+1}/{max_retries} failed, retrying in 5s..."
        )
        time.sleep(5)

    if not registered:
        logger.error("Engine failed to register with Backend. Starting pollers anyway.")

    logger.info("Starting API polling threads...")
    threads = [
        threading.Thread(
            target=api_heartbeat_loop, daemon=True, name="ApiHeartbeatThread"
        ),
        threading.Thread(
            target=api_task_poller, daemon=True, name="ApiTaskPollerThread"
        ),
        threading.Thread(
            target=api_stop_poller, daemon=True, name="ApiStopPollerThread"
        ),
        threading.Thread(
            target=api_log_push_loop, daemon=True, name="ApiLogPushThread"
        ),
    ]
    for t in threads:
        t.start()
    logger.info("API polling threads started successfully.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Asynchronous context manager for application startup and shutdown."""
    logger.info(f"Performance testing engine starting up (mode={ENGINE_MODE})...")

    if ENGINE_MODE == "api":
        start_polling_api_mode()
    else:
        start_polling_db_mode()

    try:
        start_resource_collector()
        logger.info("System resource collector started successfully.")
    except Exception as e:
        logger.warning(f"Failed to start resource collector (non-fatal): {e}")

    yield

    logger.info("Performance testing engine is shutting down.")
    if ENGINE_MODE == "api":
        try:
            from service.api_poller import shutdown_unregister

            shutdown_unregister()
        except Exception as e:
            logger.warning(f"Failed to unregister engine during shutdown: {e}")
    try:
        stop_resource_collector()
    except Exception as e:
        logger.debug(f"Ignored error stopping resource collector during shutdown: {e}")


app = FastAPI(lifespan=lifespan)


@app.get("/health", summary="Health Check", tags=["Monitoring"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "mode": ENGINE_MODE}


if __name__ == "__main__":
    logger.info("Starting server with Uvicorn...")
    uvicorn.run("app:app", host="127.0.0.1", port=5002, reload=True)
