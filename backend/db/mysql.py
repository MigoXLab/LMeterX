"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from typing import AsyncGenerator

from sqlalchemy import URL
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import AsyncAdaptedQueuePool

from db.db_config import get_settings
from utils.logger import logger

settings = get_settings()


def get_safe_database_url() -> str:
    """
    Get a safe database URL string for logging purposes with password masked.

    Returns:
        A database URL string with the password replaced by '***'
    """
    return (
        f"mysql+aiomysql://{settings.DB_USER}:***@"
        f"{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    )


# Construct the database URL securely using SQLAlchemy URL object
# Use get_safe_database_url() for logging purposes
DATABASE_URL = URL.create(
    drivername="mysql+aiomysql",
    username=settings.DB_USER,
    password=settings.DB_PASSWORD,
    host=settings.DB_HOST,
    port=settings.DB_PORT,
    database=settings.DB_NAME,
)

# Create a safe URL for logging (password masked)
# This should be used whenever we need to log connection information
SAFE_DATABASE_URL = get_safe_database_url()

# Log connection info safely (without password)
logger.info(f"Initializing database connection to: {SAFE_DATABASE_URL}")

# Create an asynchronous database engine with robust connection handling
engine = create_async_engine(
    DATABASE_URL,
    poolclass=AsyncAdaptedQueuePool,
    pool_pre_ping=True,  # Critical: Test connections for liveness before using them (prevents stale connections)
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    echo=False,  # SECURITY: Keep False in production to prevent SQL statement logging
    # NOTE: Even with echo=False, avoid logging DATABASE_URL object as it contains credentials
    connect_args={
        "connect_timeout": 15,  # Connection establishment timeout (seconds)
        "charset": "utf8mb4",
        # Note: autocommit removed from connection level to avoid conflicts with session-level transaction management
        # The async_session_factory below controls transaction behavior (autocommit=False)
    },
)

# Create a factory for asynchronous database sessions
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Create a base class for declarative models
Base = declarative_base()


# Dependency function to get a database session
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to get an async database session.

    This is a generator that yields a session and ensures it's properly
    closed after the request is finished. It also handles committing
    transactions on success or rolling back on failure.

    Usage:
        @app.get("/items")
        async def read_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except OperationalError as e:
            # Handle database connection errors gracefully
            # SECURITY: Log error without exposing connection details
            error_msg = str(e).replace(str(DATABASE_URL), SAFE_DATABASE_URL)
            logger.warning(f"Database operational error in get_db: {error_msg}")
            try:
                await session.rollback()
            except Exception as rollback_error:
                logger.debug(
                    f"Failed to rollback after operational error: {rollback_error}"
                )
            raise
        except Exception:
            try:
                await session.rollback()
            except Exception as rollback_error:
                # If rollback fails, the connection is likely already dead
                logger.debug(f"Failed to rollback session: {rollback_error}")
            raise
        finally:
            try:
                await session.close()
            except Exception as close_error:
                logger.debug(f"Failed to close session: {close_error}")
