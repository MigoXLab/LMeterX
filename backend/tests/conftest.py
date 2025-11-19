"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Set testing environment variables before any imports
os.environ["TESTING"] = "1"

# Ensure backend package is importable when tests run from project root
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# Setup async test event loop
@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the entire test session"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_db_session():
    """Mock database session"""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.execute.return_value = Mock()
    mock_session.execute.return_value.scalars.return_value.all.return_value = []
    mock_session.execute.return_value.scalar_one_or_none.return_value = None
    mock_session.scalar = AsyncMock()
    mock_session.add = Mock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    class _AsyncTransaction:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            return False

    mock_session.begin = Mock(return_value=_AsyncTransaction())
    return mock_session


@pytest.fixture
def mock_request():
    """Mock FastAPI request object"""
    mock_request = Mock()
    mock_request.state = Mock()
    mock_request.state.db = Mock()
    return mock_request


# Test data fixtures
@pytest.fixture
def sample_task_data():
    """Sample task data"""
    return {
        "temp_task_id": "temp_123",
        "name": "Test Task",
        "target_host": "https://api.example.com",
        "api_path": "/chat/completions",
        "model": "gpt-3.5-turbo",
        "duration": 300,
        "concurrent_users": 10,
        "spawn_rate": 2,
        "chat_type": 1,
        "stream_mode": True,
        "headers": [],
    }


@pytest.fixture
def sample_task_response():
    """Sample task response data"""
    return {
        "id": "task_123",
        "name": "Test Task",
        "status": "completed",
        "target_host": "https://api.example.com",
        "model": "gpt-3.5-turbo",
        "concurrent_users": 10,
        "duration": 300,
        "spawn_rate": 2,
        "chat_type": 1,
        "stream_mode": True,
        "error_message": "",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
    }


# Mock logger to avoid file permission issues during testing
@pytest.fixture(autouse=True)
def mock_logger():
    """Mock logger to prevent file creation during tests"""
    with patch("utils.logger.logger") as mock_log:
        mock_log.add = MagicMock()
        mock_log.info = MagicMock()
        mock_log.error = MagicMock()
        mock_log.warning = MagicMock()
        mock_log.debug = MagicMock()
        yield mock_log
