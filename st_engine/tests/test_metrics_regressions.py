"""Regression tests for request outcome and performance metric accounting."""

from collections import Counter
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

from engine.core import FieldMapping, GlobalConfig, GlobalStateManager, StreamMetrics
from engine.llm_locustfile import _has_token_data, _should_report_token_stats
from engine.request_processor import APIClient, RequestUsage, StreamProcessor
from service.llm_result_service import LlmResultService
from utils.error_handler import ErrorResponse
from utils.event_handler import EventManager
from utils.realtime_metrics import collect_realtime_snapshot
from utils.stats_manager import StatsManager


def test_malformed_json_stream_chunk_is_a_failure_signal():
    logger = MagicMock()
    should_break, error, _metrics = StreamProcessor.process_stream_chunk(
        b"data: {broken",
        FieldMapping(content="choices.0.delta.content"),
        1.0,
        StreamMetrics(),
        logger,
        "openai-chat",
    )

    assert should_break is True
    assert "Failed to parse stream chunk as JSON" in error
    logger.warning.assert_called_once()


def test_failed_stream_does_not_publish_partial_latency_metrics(monkeypatch):
    fire_metric = Mock()
    monkeypatch.setattr(EventManager, "fire_metric_event", fire_metric)
    metrics = StreamMetrics()
    mapping = FieldMapping(content="choices.0.delta.content")

    should_break, error, metrics = StreamProcessor.process_stream_chunk(
        b'data: {"choices":[{"delta":{"content":"partial"}}]}',
        mapping,
        1.0,
        metrics,
        MagicMock(),
        "openai-chat",
    )
    assert should_break is False
    assert error is None
    should_break, error, _ = StreamProcessor.process_stream_chunk(
        b"data: {broken", mapping, 1.0, metrics, MagicMock(), "openai-chat"
    )
    assert should_break is True
    assert error
    fire_metric.assert_not_called()


def test_stream_content_limit_is_reported_as_failure(monkeypatch):
    monkeypatch.setattr("engine.request_processor.MAX_STREAM_CONTENT_SIZE", 3)
    should_break, error, _ = StreamProcessor.process_stream_chunk(
        b"abcd",
        FieldMapping(data_format="text"),
        1.0,
        StreamMetrics(),
        MagicMock(),
    )
    assert should_break is True
    assert "exceeded 3 byte limit" in error


def test_sse_multiline_data_is_joined_into_one_event():
    response = MagicMock()
    response.iter_lines.return_value = iter(
        [b'data: {"choices": [', b'data: {"delta": {"content": "ok"}}]}', b""]
    )
    client = APIClient(GlobalConfig(), MagicMock())

    assert list(client._iter_stream_lines(response)) == [
        b'data: {"choices": [\n{"delta": {"content": "ok"}}]}'
    ]


def test_all_2xx_status_codes_are_accepted():
    handler = ErrorResponse(GlobalConfig(), MagicMock())
    for status_code in (200, 201, 202, 204, 299):
        response = MagicMock(status_code=status_code)
        assert handler._handle_status_code_error(response) is False
        response.failure.assert_not_called()


def test_fallback_failure_uses_real_request_name(monkeypatch):
    fire_failure = Mock()
    monkeypatch.setattr(EventManager, "fire_failure_event", fire_failure)
    handler = ErrorResponse(GlobalConfig(api_path="/configured"), MagicMock())

    handler._handle_general_exception_event(
        "connect failed", response=None, request_name="/actual"
    )

    assert fire_failure.call_args.kwargs["name"] == "/actual"


def test_failed_empty_result_has_no_token_data():
    assert _has_token_data("", "", {"completion_tokens": 0, "total_tokens": 0}) is False
    assert _has_token_data("", "", {"total_tokens": None}) is False
    assert _has_token_data("", "", {"total_tokens": 12}) is True
    assert _has_token_data("", "answer", {}) is True


def test_failed_request_with_usage_or_partial_content_does_not_report_tokens():
    failed_usage = RequestUsage(
        {"prompt_tokens": 9, "completion_tokens": 2, "total_tokens": 11}
    )

    assert _should_report_token_stats("", "partial", failed_usage) is False
    assert _should_report_token_stats("", "", failed_usage) is False


def test_successful_request_reports_available_input_and_completion_tokens():
    successful_usage = RequestUsage(
        {"prompt_tokens": 9, "completion_tokens": 2, "total_tokens": 11},
        request_succeeded=True,
    )

    assert _should_report_token_stats("", "answer", successful_usage) is True


class _Entry:
    def __init__(self, count, failures, response_times, current_rps, fail_rps):
        self.num_requests = count
        self.num_failures = failures
        self.response_times = Counter(response_times)
        self.total_response_time = sum(k * v for k, v in response_times.items())
        self.min_response_time = min(response_times) if response_times else None
        self.max_response_time = max(response_times) if response_times else None
        self.current_rps = current_rps
        self.current_fail_per_sec = fail_rps
        self.avg_response_time = self.total_response_time / count if count else 0


def test_realtime_totals_exclude_custom_metric_events():
    request = _Entry(2, 1, {100: 1, 200: 1}, 2.0, 1.0)
    metric = _Entry(10, 0, {999: 10}, 10.0, 0.0)
    environment = SimpleNamespace(
        stats=SimpleNamespace(
            entries={("/chat", "POST"): request, ("Total_time", "metric"): metric}
        ),
        runner=SimpleNamespace(user_count=3),
    )

    snapshot = collect_realtime_snapshot(environment, include_entries=True)

    assert snapshot["total_requests"] == 2
    assert snapshot["total_failures"] == 1
    assert snapshot["current_rps"] == 2.0
    assert snapshot["avg_response_time"] == 150.0
    assert snapshot["p95_response_time"] == 200.0
    assert "Total_time" in snapshot["metrics"]


def test_final_stats_uses_captured_end_time():
    state = GlobalStateManager()
    old_start, old_end, old_stats = state.start_time, state.end_time, state._token_stats
    try:
        state.start_time = 10.0
        state.end_time = 14.0
        state._token_stats = SimpleNamespace(
            reqs_count=4, completion_tokens=40, total_tokens=80
        )
        result = StatsManager().get_final_stats()
        assert result["execution_time"] == 4.0
        assert result["req_throughput"] == 1.0
        assert result["completion_tps"] == 10.0
    finally:
        state.start_time, state.end_time, state._token_stats = (
            old_start,
            old_end,
            old_stats,
        )


def test_llm_result_service_persists_reqs_count():
    session = MagicMock()
    LlmResultService().insert_locust_results(
        session,
        {"custom_metrics": {"reqs_count": 7}, "locust_stats": []},
        "task-1",
    )

    persisted = session.add.call_args.args[0]
    assert persisted.num_requests == 7
    session.commit.assert_called_once()
