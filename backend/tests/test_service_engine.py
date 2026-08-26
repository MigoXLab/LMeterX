"""
Engine service tests: registration, heartbeat, task claim, status/results,
stopping tasks, and dead-engine reconciliation.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from model.cluster import Cluster
from model.engine import EngineHeartbeat
from service.engine_service import (
    HEARTBEAT_STALE_SECONDS,
    claim_task,
    get_stopping_tasks,
    process_heartbeat,
    reconcile_dead_engines,
    register_engine,
    submit_task_results,
    update_task_status,
)
from service.probe_service import PROBE_EXECUTION_TIMEOUT


@pytest.fixture
def db():
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.add = Mock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.mark.asyncio
class TestRegisterEngine:
    async def test_register_new_engine(self, db):
        db.get = AsyncMock(side_effect=[None, None])

        result = await register_engine(
            db=db,
            engine_id="eng-001",
            cluster_id="gpu-prod",
            capabilities={"max_concurrent_tasks": 1},
            version="1.0.0",
        )

        assert result["status"] == "registered"
        assert result["heartbeat_interval"] == 10
        assert db.add.call_count >= 1

    async def test_register_existing_engine(self, db):
        existing = MagicMock(spec=EngineHeartbeat)
        existing.engine_id = "eng-001"
        existing.status = "offline"
        cluster = MagicMock(spec=Cluster)
        db.get = AsyncMock(side_effect=[existing, cluster])

        result = await register_engine(
            db=db,
            engine_id="eng-001",
            cluster_id="gpu-prod",
            capabilities={"max_concurrent_tasks": 1},
            version="1.1.0",
        )

        assert result["status"] == "registered"
        assert existing.status == "online"
        assert existing.version == "1.1.0"


@pytest.mark.asyncio
class TestProcessHeartbeat:
    async def test_heartbeat_online(self, db):
        hb = MagicMock(spec=EngineHeartbeat)
        hb.engine_id = "eng-001"
        db.get = AsyncMock(return_value=hb)

        result = await process_heartbeat(
            db=db,
            engine_id="eng-001",
            cluster_id="gpu-prod",
            running_tasks=[],
            cpu_usage=20.0,
            memory_usage=50.0,
            available_slots=1,
        )

        assert result["status"] == "ok"
        assert hb.status == "online"

    async def test_heartbeat_busy(self, db):
        hb = MagicMock(spec=EngineHeartbeat)
        hb.engine_id = "eng-001"
        db.get = AsyncMock(return_value=hb)

        result = await process_heartbeat(
            db=db,
            engine_id="eng-001",
            cluster_id="gpu-prod",
            running_tasks=["task-123"],
            cpu_usage=80.0,
            memory_usage=70.0,
            available_slots=0,
        )

        assert result["status"] == "ok"
        assert hb.status == "busy"

    async def test_heartbeat_not_registered(self, db):
        db.get = AsyncMock(return_value=None)

        result = await process_heartbeat(
            db=db,
            engine_id="eng-unknown",
            cluster_id="gpu-prod",
            running_tasks=[],
            cpu_usage=0.0,
            memory_usage=0.0,
            available_slots=1,
        )

        assert result["status"] == "not_registered"


@pytest.mark.asyncio
class TestClaimTask:
    async def test_claim_probe_includes_execution_deadline(self, db):
        probe = MagicMock()
        probe.id = "probe-001"
        probe.probe_type = "llm"
        probe.request_config = {"target_host": "https://api.example.com"}
        probe.status = "pending"
        probe.engine_id = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = probe
        db.execute = AsyncMock(return_value=mock_result)

        result = await claim_task(
            db=db,
            engine_id="eng-001",
            cluster_id="gpu-prod",
            task_types=["probe"],
        )

        assert result["id"] == "probe-001"
        assert result["type"] == "probe"
        assert result["config"]["execution_timeout"] == PROBE_EXECUTION_TIMEOUT
        assert probe.status == "claimed"
        assert probe.engine_id == "eng-001"

    async def test_claim_llm_task(self, db):
        dispatch_entry = MagicMock()
        dispatch_entry.queue_seq = 1
        dispatch_entry.task_type = "llm"
        dispatch_entry.task_id = "task-001"
        dispatch_entry.status = "queued"

        task = MagicMock()
        task.id = "task-001"
        task.name = "LLM Test"
        task.status = "queuing"
        task.cluster_id = "gpu-prod"
        task.is_deleted = 0
        task.target_host = "https://api.example.com"
        task.api_path = "/v1/chat/completions"
        task.duration = 60
        task.concurrent_users = 10
        task.spawn_rate = 5
        task.headers = "{}"
        task.cookies = "{}"
        task.model = "gpt-4"
        task.stream_mode = "True"
        task.request_payload = ""
        task.field_mapping = ""
        task.api_type = "openai-chat"
        task.cert_file = None
        task.key_file = None
        task.warmup_enabled = 1
        task.warmup_duration = 120
        task.chat_type = 0
        task.test_data = ""
        task.load_mode = "fixed"
        task.step_start_users = None
        task.step_increment = None
        task.step_duration = None
        task.step_max_users = None
        task.step_sustain_duration = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dispatch_entry
        db.execute = AsyncMock(return_value=mock_result)
        db.get = AsyncMock(return_value=task)

        result = await claim_task(
            db=db,
            engine_id="eng-001",
            cluster_id="gpu-prod",
            task_types=["llm"],
        )

        assert result is not None
        assert result["id"] == "task-001"
        assert result["type"] == "llm"
        assert dispatch_entry.status == "claimed"
        assert dispatch_entry.engine_id == "eng-001"
        assert task.status == "running"
        assert task.engine_id == "eng-001"

    async def test_claim_http_first_regardless_of_requested_type_order(self, db):
        dispatch_entry = MagicMock()
        dispatch_entry.queue_seq = 1
        dispatch_entry.task_type = "http"
        dispatch_entry.task_id = "http-001"
        dispatch_entry.status = "queued"

        task = MagicMock()
        task.id = "http-001"
        task.name = "HTTP Test"
        task.status = "queuing"
        task.cluster_id = "gpu-prod"
        task.is_deleted = 0
        task.target_host = "https://api.example.com"
        task.target_url = "https://api.example.com/health"
        task.api_path = "/health"
        task.duration = 60
        task.concurrent_users = 10
        task.spawn_rate = 5
        task.headers = "{}"
        task.cookies = "{}"
        task.dataset_file = ""
        task.load_mode = "fixed"
        task.step_start_users = None
        task.step_increment = None
        task.step_duration = None
        task.step_max_users = None
        task.step_sustain_duration = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dispatch_entry
        db.execute = AsyncMock(return_value=mock_result)
        db.get = AsyncMock(return_value=task)

        result = await claim_task(
            db=db,
            engine_id="eng-001",
            cluster_id="gpu-prod",
            task_types=["llm", "http"],
        )

        assert result is not None
        assert result["id"] == "http-001"
        assert result["type"] == "http"
        assert dispatch_entry.status == "claimed"
        assert task.status == "running"

        statement = db.execute.await_args.args[0]
        assert "task_dispatch_queue.queue_seq ASC" in str(statement)
        assert "FOR UPDATE" in str(statement)

    async def test_claim_skips_stale_queue_entry(self, db):
        stale_entry = MagicMock()
        stale_entry.task_type = "http"
        stale_entry.task_id = "deleted-http"
        stale_entry.status = "queued"

        valid_entry = MagicMock()
        valid_entry.task_type = "llm"
        valid_entry.task_id = "llm-002"
        valid_entry.status = "queued"

        stale_task = MagicMock()
        stale_task.status = "stopped"
        stale_task.is_deleted = 0
        stale_task.cluster_id = "gpu-prod"

        valid_task = MagicMock()
        valid_task.id = "llm-002"
        valid_task.name = "LLM Test"
        valid_task.status = "queuing"
        valid_task.is_deleted = 0
        valid_task.cluster_id = "gpu-prod"
        valid_task.target_host = "https://api.example.com"
        valid_task.api_path = "/v1/chat/completions"
        valid_task.duration = 60
        valid_task.concurrent_users = 1
        valid_task.spawn_rate = 1
        valid_task.headers = "{}"
        valid_task.cookies = "{}"
        valid_task.test_data = ""

        stale_result = MagicMock()
        stale_result.scalar_one_or_none.return_value = stale_entry
        valid_result = MagicMock()
        valid_result.scalar_one_or_none.return_value = valid_entry
        db.execute = AsyncMock(side_effect=[stale_result, valid_result])
        db.get = AsyncMock(side_effect=[stale_task, valid_task])

        result = await claim_task(
            db=db,
            engine_id="eng-001",
            cluster_id="gpu-prod",
            task_types=["llm", "http"],
        )

        assert result["id"] == "llm-002"
        assert stale_entry.status == "cancelled"
        assert valid_entry.status == "claimed"

    async def test_claim_no_task(self, db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await claim_task(
            db=db,
            engine_id="eng-001",
            cluster_id="gpu-prod",
            task_types=["llm", "http"],
        )

        assert result is None


@pytest.mark.asyncio
class TestUpdateTaskStatus:
    async def test_update_success(self, db):
        task = MagicMock()
        task.id = "task-001"
        task.engine_id = "eng-001"
        task.status = "running"
        db.get = AsyncMock(side_effect=[task, None])

        result = await update_task_status(
            db=db,
            task_id="task-001",
            engine_id="eng-001",
            status="stopping",
        )

        assert result is True
        assert task.status == "stopping"

    async def test_update_wrong_engine(self, db):
        task = MagicMock()
        task.id = "task-001"
        task.engine_id = "eng-001"
        db.get = AsyncMock(side_effect=[task, None])

        result = await update_task_status(
            db=db,
            task_id="task-001",
            engine_id="eng-wrong",
            status="stopping",
        )

        assert result is False


@pytest.mark.asyncio
class TestSubmitResults:
    async def test_submit_llm_results(self, db):
        task = MagicMock()
        task.id = "task-001"
        task.engine_id = "eng-001"
        task.status = "running"
        db.get = AsyncMock(side_effect=[task, None])

        locust_results = {
            "num_requests": 100,
            "num_failures": 2,
            "avg_latency": 150.0,
            "min_latency": 50.0,
            "max_latency": 500.0,
            "median_latency": 120.0,
            "p95_latency": 350.0,
            "rps": 10.0,
            "avg_content_length": 256.0,
            "total_tps": 50.0,
            "completion_tps": 45.0,
            "avg_total_tokens_per_req": 100.0,
            "avg_completion_tokens_per_req": 80.0,
        }

        result = await submit_task_results(
            db=db,
            task_id="task-001",
            engine_id="eng-001",
            locust_results=locust_results,
            final_status="completed",
        )

        assert result is True
        assert task.status == "completed"
        assert db.add.called

    async def test_submit_llm_nested_results(self, db):
        task = MagicMock()
        task.id = "task-llm-001"
        task.engine_id = "eng-001"
        task.status = "running"
        db.get = AsyncMock(side_effect=[task, None])

        locust_results = {
            "locust_stats": [
                {
                    "metric_type": "POST /v1/chat/completions",
                    "num_requests": 42,
                    "num_failures": 1,
                    "avg_latency": 250.0,
                    "min_latency": 100.0,
                    "max_latency": 800.0,
                    "median_latency": 220.0,
                    "p95_latency": 600.0,
                    "rps": 7.5,
                    "avg_content_length": 512.0,
                }
            ],
            "custom_metrics": {
                "reqs_num": 42,
                "req_throughput": 7.5,
                "total_tps": 1200.0,
                "completion_tps": 900.0,
                "avg_total_tokens_per_req": 160.0,
                "avg_completion_tokens_per_req": 120.0,
            },
        }

        result = await submit_task_results(
            db=db,
            task_id="task-llm-001",
            engine_id="eng-001",
            locust_results=locust_results,
            final_status="completed",
        )

        assert result is True
        assert db.add.call_count == 2
        first_record = db.add.call_args_list[0].args[0]
        token_record = db.add.call_args_list[1].args[0]
        assert first_record.num_requests == 42
        assert first_record.avg_latency == 250.0
        assert token_record.metric_type == "token_metrics"
        assert token_record.total_tps == 1200.0

    async def test_submit_http_nested_results(self, db):
        task = MagicMock()
        task.id = "task-http-001"
        task.engine_id = "eng-001"
        task.status = "running"
        db.get = AsyncMock(side_effect=[None, task])

        locust_results = {
            "locust_stats": [
                {
                    "metric_type": "GET /puyu/ip/location",
                    "num_requests": 2186,
                    "num_failures": 0,
                    "avg_latency": 27.0,
                    "min_latency": 23.0,
                    "max_latency": 82.0,
                    "median_latency": 27.0,
                    "p95_latency": 31.0,
                    "rps": 36.59,
                    "avg_content_length": 0.0,
                }
            ],
            "custom_metrics": {},
        }

        result = await submit_task_results(
            db=db,
            task_id="task-http-001",
            engine_id="eng-001",
            locust_results=locust_results,
            final_status="completed",
        )

        assert result is True
        assert db.add.call_count == 1
        record = db.add.call_args.args[0]
        assert record.metric_type == "GET /puyu/ip/location"
        assert record.num_requests == 2186
        assert record.p95_latency == 31.0

    async def test_submit_wrong_engine(self, db):
        task = MagicMock()
        task.id = "task-001"
        task.engine_id = "eng-001"
        db.get = AsyncMock(side_effect=[task, None])

        result = await submit_task_results(
            db=db,
            task_id="task-001",
            engine_id="eng-wrong",
            locust_results={},
            final_status="completed",
        )

        assert result is False


@pytest.mark.asyncio
class TestGetStoppingTasks:
    async def test_returns_stopping_task_ids(self, db):
        mock_result = MagicMock()
        mock_result.all.return_value = [("task-1",), ("task-2",)]
        db.execute = AsyncMock(return_value=mock_result)

        result = await get_stopping_tasks(
            db=db, engine_id="eng-001", cluster_id="gpu-prod"
        )

        assert "task-1" in result
        assert "task-2" in result


@pytest.mark.asyncio
class TestReconcileDeadEngines:
    async def test_no_stale_engines(self, db):
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        count = await reconcile_dead_engines(db)
        assert count == 0

    async def test_marks_orphaned_tasks_failed(self, db):
        stale_result = MagicMock()
        stale_result.all.return_value = [("eng-dead",)]

        update_result = MagicMock()
        update_result.rowcount = 2

        db.execute = AsyncMock(
            side_effect=[stale_result, update_result, update_result, MagicMock()]
        )

        count = await reconcile_dead_engines(db)
        assert count == 4
