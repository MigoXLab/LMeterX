"""
Cluster service tests: list, get, desired state, actual state, scaling, create.
"""

from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from model.cluster import Cluster
from service.cluster_service import (
    create_cluster,
    get_cluster,
    get_desired_state,
    list_clusters,
    scale_cluster,
    update_actual_state,
)


@pytest.fixture
def db():
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.add = Mock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def sample_cluster():
    c = MagicMock(spec=Cluster)
    c.id = "gpu-prod"
    c.name = "GPU Production"
    c.description = "GPU cluster"
    c.status = "active"
    c.desired_replicas = 3
    c.min_replicas = 1
    c.max_replicas = 10
    c.current_replicas = 3
    c.ready_replicas = 3
    c.created_at = None
    return c


@pytest.mark.asyncio
class TestGetCluster:
    async def test_found(self, db, sample_cluster):
        db.get = AsyncMock(return_value=sample_cluster)

        result = await get_cluster(db, "gpu-prod")

        assert result is not None
        assert result["id"] == "gpu-prod"
        assert result["name"] == "GPU Production"
        assert result["desired_replicas"] == 3

    async def test_not_found(self, db):
        db.get = AsyncMock(return_value=None)

        result = await get_cluster(db, "nonexistent")
        assert result is None


@pytest.mark.asyncio
class TestGetDesiredState:
    async def test_returns_replicas_config(self, db, sample_cluster):
        db.get = AsyncMock(return_value=sample_cluster)

        result = await get_desired_state(db, "gpu-prod")

        assert result["desired_replicas"] == 3
        assert result["min_replicas"] == 1
        assert result["max_replicas"] == 10

    async def test_not_found(self, db):
        db.get = AsyncMock(return_value=None)

        result = await get_desired_state(db, "nonexistent")
        assert result is None


@pytest.mark.asyncio
class TestUpdateActualState:
    async def test_updates_current_ready_available(self, db, sample_cluster):
        db.get = AsyncMock(return_value=sample_cluster)

        result = await update_actual_state(
            db=db,
            cluster_id="gpu-prod",
            current_replicas=5,
            ready_replicas=4,
            available_replicas=4,
        )

        assert result is True
        assert sample_cluster.current_replicas == 5
        assert sample_cluster.ready_replicas == 4

    async def test_not_found(self, db):
        db.get = AsyncMock(return_value=None)

        result = await update_actual_state(
            db=db,
            cluster_id="nonexistent",
            current_replicas=1,
            ready_replicas=1,
            available_replicas=1,
        )

        assert result is False


@pytest.mark.asyncio
class TestScaleCluster:
    async def test_scale_within_bounds(self, db, sample_cluster):
        db.get = AsyncMock(return_value=sample_cluster)

        result = await scale_cluster(db, "gpu-prod", desired_replicas=5)

        assert result is not None
        assert result["desired_replicas"] == 5
        assert sample_cluster.desired_replicas == 5

    async def test_scale_clamped_to_max(self, db, sample_cluster):
        db.get = AsyncMock(return_value=sample_cluster)

        result = await scale_cluster(db, "gpu-prod", desired_replicas=50)

        assert result["desired_replicas"] == 10

    async def test_scale_clamped_to_min(self, db, sample_cluster):
        db.get = AsyncMock(return_value=sample_cluster)

        result = await scale_cluster(db, "gpu-prod", desired_replicas=0)

        assert result["desired_replicas"] == 1

    async def test_not_found(self, db):
        db.get = AsyncMock(return_value=None)

        result = await scale_cluster(db, "nonexistent", desired_replicas=3)
        assert result is None


@pytest.mark.asyncio
class TestCreateCluster:
    async def test_create_success(self, db):
        result = await create_cluster(
            db=db,
            cluster_id="new-cluster",
            name="New Cluster",
            description="A new cluster",
            min_replicas=2,
            max_replicas=20,
        )

        assert result["id"] == "new-cluster"
        assert result["name"] == "New Cluster"
        assert result["status"] == "active"
        db.add.assert_called_once()
        db.flush.assert_awaited_once()


@pytest.mark.asyncio
class TestListClusters:
    async def test_list_with_stats(self, db, sample_cluster):
        clusters_result = MagicMock()
        clusters_result.scalars.return_value.all.return_value = [sample_cluster]

        engine_stats_result = MagicMock()
        stats_row = MagicMock()
        stats_row.online = 3
        stats_row.available_slots = 2
        engine_stats_result.one.return_value = stats_row

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        db.execute = AsyncMock(
            side_effect=[
                clusters_result,
                engine_stats_result,
                count_result,
                count_result,
            ]
        )

        result = await list_clusters(db)

        assert len(result) == 1
        assert result[0]["id"] == "gpu-prod"
        assert result[0]["online_engines"] == 3
        assert result[0]["available_slots"] == 2
