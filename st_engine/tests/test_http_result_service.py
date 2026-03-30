"""
Tests for HttpResultService: insertion of locust stats into the database,
metric_type normalisation, and handling of None / edge-case fields.
"""

from unittest.mock import Mock, call, patch

import pytest

from service.http_result_service import HttpResultService


@pytest.fixture
def result_service():
    return HttpResultService()


def _make_stat_row(task_id="task-001", metric_type="GET /api/test", **overrides):
    """Build a minimal valid stat dict; override individual fields via kwargs."""
    defaults = {
        "task_id": task_id,
        "metric_type": metric_type,
        "num_requests": 100,
        "num_failures": 5,
        "avg_latency": 50.0,
        "min_latency": 10.0,
        "max_latency": 200.0,
        "median_latency": 45.0,
        "p95_latency": 180.0,
        "rps": 20.0,
        "avg_content_length": 512.0,
    }
    defaults.update(overrides)
    return defaults


# =====================================================================
# Normal insertion
# =====================================================================
class TestInsertLocustResults:
    def test_inserts_valid_stats(self, result_service):
        session = Mock()
        locust_result = {
            "locust_stats": [
                _make_stat_row(metric_type="GET /api/users"),
                _make_stat_row(metric_type="total"),
            ]
        }

        result_service.insert_locust_results(session, locust_result, "task-001")

        assert session.add.call_count == 2
        session.commit.assert_called_once()

    def test_skips_invalid_stat_without_task_id(self, result_service):
        session = Mock()
        locust_result = {
            "locust_stats": [
                _make_stat_row(),
                {"metric_type": "orphan"},  # Missing task_id
            ]
        }

        result_service.insert_locust_results(session, locust_result, "task-001")

        # Only the first valid stat should be inserted
        assert session.add.call_count == 1

    def test_skips_empty_stat(self, result_service):
        session = Mock()
        locust_result = {"locust_stats": [{}]}

        result_service.insert_locust_results(session, locust_result, "task-001")
        session.add.assert_not_called()

    def test_empty_stats_list(self, result_service):
        session = Mock()
        locust_result = {"locust_stats": []}

        result_service.insert_locust_results(session, locust_result, "task-001")
        session.add.assert_not_called()
        session.commit.assert_called_once()


# =====================================================================
# metric_type normalisation
# =====================================================================
class TestMetricTypeNormalisation:
    def test_string_metric_type_unchanged(self, result_service):
        session = Mock()
        locust_result = {
            "locust_stats": [_make_stat_row(metric_type="POST /api/create")]
        }

        result_service.insert_locust_results(session, locust_result, "task-001")

        added_obj = session.add.call_args[0][0]
        assert added_obj.metric_type == "POST /api/create"

    def test_tuple_metric_type_normalised(self, result_service):
        """When metric_type is a tuple (from Locust entries key), it should be
        normalised to the first element as a string."""
        session = Mock()
        stat = _make_stat_row(metric_type=("GET /api/users", "GET"))
        locust_result = {"locust_stats": [stat]}

        result_service.insert_locust_results(session, locust_result, "task-001")

        added_obj = session.add.call_args[0][0]
        assert added_obj.metric_type == "GET /api/users"

    def test_list_metric_type_normalised(self, result_service):
        session = Mock()
        stat = _make_stat_row(metric_type=["DELETE /api/item", "DELETE"])
        locust_result = {"locust_stats": [stat]}

        result_service.insert_locust_results(session, locust_result, "task-001")

        added_obj = session.add.call_args[0][0]
        assert added_obj.metric_type == "DELETE /api/item"

    def test_empty_tuple_metric_type(self, result_service):
        session = Mock()
        stat = _make_stat_row(metric_type=())
        locust_result = {"locust_stats": [stat]}

        result_service.insert_locust_results(session, locust_result, "task-001")

        added_obj = session.add.call_args[0][0]
        assert added_obj.metric_type == ""


# =====================================================================
# None / edge-case field handling
# =====================================================================
class TestNoneFieldHandling:
    def test_none_latency_fields_default_to_zero(self, result_service):
        """When num_requests is 0, some latency fields may be None from Locust."""
        session = Mock()
        stat = _make_stat_row(
            num_requests=0,
            num_failures=0,
            avg_latency=None,
            min_latency=None,
            max_latency=None,
            median_latency=None,
            p95_latency=None,
            rps=None,
            avg_content_length=None,
        )
        locust_result = {"locust_stats": [stat]}

        result_service.insert_locust_results(session, locust_result, "task-001")

        added_obj = session.add.call_args[0][0]
        assert added_obj.avg_latency == 0.0
        assert added_obj.min_latency == 0.0
        assert added_obj.max_latency == 0.0
        assert added_obj.median_latency == 0.0
        assert added_obj.p95_latency == 0.0
        assert added_obj.rps == 0.0
        assert added_obj.avg_content_length == 0.0

    def test_none_num_requests_defaults_to_zero(self, result_service):
        session = Mock()
        stat = _make_stat_row(num_requests=None, num_failures=None)
        locust_result = {"locust_stats": [stat]}

        result_service.insert_locust_results(session, locust_result, "task-001")

        added_obj = session.add.call_args[0][0]
        assert added_obj.num_requests == 0
        assert added_obj.num_failures == 0


# =====================================================================
# Error handling
# =====================================================================
class TestErrorHandling:
    def test_rollback_on_exception(self, result_service):
        session = Mock()
        session.add.side_effect = Exception("DB write error")
        locust_result = {"locust_stats": [_make_stat_row()]}

        with pytest.raises(Exception, match="DB write error"):
            result_service.insert_locust_results(session, locust_result, "task-001")

        session.rollback.assert_called_once()
