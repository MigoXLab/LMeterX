"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import URL, create_engine, event, text
from sqlalchemy.exc import DisconnectionError, OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import Pool

from db.db_config import get_settings
from utils.logger import logger

# --- Database Setup ---

# Load database settings
settings = get_settings()


def get_safe_database_url() -> str:
    """
    Get a safe database URL string for logging purposes with password masked.

    Returns:
        A database URL string with the password replaced by '***'
    """
    return (
        f"mysql+pymysql://{settings.DB_USER}:***@"
        f"{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    )


# Construct the database URL securely using SQLAlchemy URL object
# Use get_safe_database_url() for logging purposes
DATABASE_URL = URL.create(
    drivername="mysql+pymysql",
    username=settings.DB_USER,
    password=settings.DB_PASSWORD,
    host=settings.DB_HOST,
    port=settings.DB_PORT,
    database=settings.DB_NAME,
)

# Create a safe URL for logging (password masked)
# This should be used whenever we need to log connection information
SAFE_DATABASE_URL = get_safe_database_url()

# Global variables for the database engine and session factory
engine = None
SessionLocal = None


# Register pool event listener at class level for all Pool instances
# This ensures the listener is properly registered and works across multiple engines
@event.listens_for(Pool, "connect")
def _on_connect(dbapi_conn, connection_record):
    """
    Called when a new DBAPI connection is created (before it's added to the pool).
    Set connection-level configurations here.
    """
    # Set connection character set encoding
    # This is redundant with connect_args but serves as a safeguard
    pass


@event.listens_for(Pool, "checkout")
def _on_checkout(dbapi_conn, connection_record, connection_proxy):
    """
    Called when a connection is retrieved from the pool.
    Note: pool_pre_ping=True already validates connections before checkout,
    so additional validation here is unnecessary. This listener is kept
    for potential future connection-level adjustments.
    """
    # Connection validation is handled by pool_pre_ping=True
    # Additional per-checkout logic can be added here if needed
    pass


def init_db():
    """
    Initializes the database engine and session factory.

    This function creates a SQLAlchemy engine with a connection pool and sets up
    a sessionmaker to create new database sessions. It also tests the connection.
    """
    global engine, SessionLocal
    if engine is not None:
        logger.info("Database engine is already initialized.")
        return

    try:
        logger.info(f"Initializing database engine to: {SAFE_DATABASE_URL}")
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,  # Test connections for liveness before using them (critical for RDS).
            pool_recycle=settings.DB_POOL_RECYCLE,  # Recycle connections after a set time.
            pool_size=settings.DB_POOL_SIZE,  # Set the connection pool size.
            max_overflow=settings.DB_MAX_OVERFLOW,  # Set the connection pool overflow.
            pool_timeout=settings.DB_POOL_TIMEOUT,  # Timeout for getting connection from pool.
            echo=False,  # SECURITY: Keep False in production to prevent SQL statement logging
            # NOTE: Even with echo=False, avoid logging DATABASE_URL object as it contains credentials
            connect_args={
                "connect_timeout": 15,  # Connection establishment timeout
                "charset": "utf8mb4",
                "use_unicode": True,
                # Note: autocommit removed from connection level to avoid conflicts with session-level transaction management
                # The sessionmaker below controls transaction behavior (autocommit=False)
                "program_name": "st_engine",
            },
        )

        # Pool event listeners are registered at class level (see above)
        # No need to call _setup_pool_events() for instance-specific registration

        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        # Test the database connection
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("Database connection successful.")

    except Exception as e:
        # SECURITY: Log error without exposing connection details
        error_msg = str(e).replace(str(DATABASE_URL), SAFE_DATABASE_URL)
        logger.error(f"Failed to initialize database connection: {error_msg}")
        # Reset globals on failure
        engine = None
        SessionLocal = None
        raise


def dispose_engine():
    """Dispose the engine and all connections in the pool."""
    global engine, SessionLocal
    if engine is not None:
        try:
            engine.dispose()
            logger.info("Database engine disposed successfully.")
        except Exception as e:
            logger.warning(f"Error disposing database engine: {e}")
        finally:
            engine = None
            SessionLocal = None


@contextmanager
def get_db_session() -> Iterator[Session]:
    """
    Provides a transactional scope around a series of operations.

    This context manager ensures that the database session is properly
    initialized and closed, and handles connection errors by attempting to
    re-establish the connection.

    Yields:
        Session: A new SQLAlchemy session object.
    """
    global engine, SessionLocal
    if engine is None or SessionLocal is None:
        logger.warning("Database not initialized. Attempting to initialize now.")
        init_db()

    if SessionLocal is None:
        raise RuntimeError("Failed to initialize database session factory")

    session = SessionLocal()
    try:
        yield session
    except OperationalError as e:
        # Handle database connection errors gracefully
        # SECURITY: Log error without exposing connection details
        error_msg = str(e).replace(str(DATABASE_URL), SAFE_DATABASE_URL)
        logger.warning(f"Database operational error occurred: {error_msg}")
        try:
            session.rollback()
        except Exception as rollback_error:
            logger.debug(
                f"Failed to rollback after operational error: {rollback_error}"
            )
        raise
    except Exception as e:
        # SECURITY: Log error without exposing connection details
        error_msg = str(e).replace(str(DATABASE_URL), SAFE_DATABASE_URL)
        logger.error(f"An error occurred during the database session: {error_msg}")
        try:
            session.rollback()
        except Exception as rollback_error:
            # If rollback fails due to connection issues, log but don't mask original error
            logger.debug(f"Failed to rollback session: {rollback_error}")
        raise
    finally:
        try:
            session.close()
        except Exception as close_error:
            # If close fails, the connection is likely already dead
            logger.debug(f"Failed to close session: {close_error}")
