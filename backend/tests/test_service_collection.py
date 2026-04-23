"""
Collection Service tests.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from model.collection import (
    Collection,
    CollectionCreateRequest,
    CollectionTaskAddRequest,
    CollectionUpdateRequest,
)
from service.collection_service import (
    _get_collection_or_404,
    add_task_to_collection_svc,
    create_collection_svc,
    delete_collection_svc,
    remove_task_from_collection_svc,
    update_collection_svc,
)
from utils.error_handler import ErrorResponse


@pytest.fixture
def mock_request():
    req = MagicMock(spec=Request)
    req.state = MagicMock()
    req.state.db = AsyncMock(spec=AsyncSession)
    return req


@pytest.mark.asyncio
class TestCollectionService:
    """Test suite for collection service."""

    @patch("service.collection_service._resolve_username")
    @patch("service.collection_service.is_admin_user")
    async def test_update_collection_permission_denied(
        self, mock_is_admin, mock_resolve_username, mock_request
    ):
        mock_resolve_username.return_value = "hacker"
        mock_is_admin.return_value = False

        # Mock DB collection
        db_collection = Collection(id="123", name="test", created_by="owner")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = db_collection
        mock_request.state.db.execute.return_value = mock_result

        with pytest.raises(ErrorResponse) as exc_info:
            await update_collection_svc(
                mock_request, "123", CollectionUpdateRequest(name="hacked")
            )
        assert exc_info.value.status_code == 403

    @patch("service.collection_service._resolve_username")
    @patch("service.collection_service.is_admin_user")
    async def test_update_collection_permission_granted_owner(
        self, mock_is_admin, mock_resolve_username, mock_request
    ):
        mock_resolve_username.return_value = "owner"
        mock_is_admin.return_value = False

        db_collection = Collection(id="123", name="test", created_by="owner")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = db_collection
        mock_request.state.db.execute.return_value = mock_result

        # We also need to mock _get_collection_or_404 correctly or db.scalar for task count
        mock_request.state.db.scalar.return_value = 0

        res = await update_collection_svc(
            mock_request, "123", CollectionUpdateRequest(name="updated")
        )
        assert res["name"] == "updated"

    @patch("service.collection_service._resolve_username")
    @patch("service.collection_service.is_admin_user")
    async def test_delete_collection_permission_denied(
        self, mock_is_admin, mock_resolve_username, mock_request
    ):
        mock_resolve_username.return_value = "hacker"
        mock_is_admin.return_value = False

        db_collection = Collection(id="123", name="test", created_by="owner")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = db_collection
        mock_request.state.db.execute.return_value = mock_result

        with pytest.raises(ErrorResponse) as exc_info:
            await delete_collection_svc(mock_request, "123")
        assert exc_info.value.status_code == 403

    @patch("service.collection_service._resolve_username")
    @patch("service.collection_service.is_admin_user")
    async def test_delete_collection_permission_granted_admin(
        self, mock_is_admin, mock_resolve_username, mock_request
    ):
        mock_resolve_username.return_value = "admin_user"
        mock_is_admin.return_value = True

        db_collection = Collection(id="123", name="test", created_by="owner")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = db_collection
        mock_request.state.db.execute.return_value = mock_result

        res = await delete_collection_svc(mock_request, "123")
        assert res["message"] == "Collection deleted successfully"
