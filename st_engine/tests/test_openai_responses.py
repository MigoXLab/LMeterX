"""OpenAI Responses API streaming protocol tests."""

import json
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from engine.core import ConfigManager, GlobalConfig, StreamMetrics
from engine.request_processor import APIClient, PayloadBuilder, ResponsesStreamProcessor
from utils.dataset_loader import parse_data_line
from utils.realtime_metrics import collect_realtime_snapshot


def _sse(event):
    return f"data: {json.dumps(event)}".encode()


class StreamingResponse:
    """Fake streaming response for Responses API tests."""

    def __init__(self, events):
        """Initialize with SSE events to yield."""
        self.status_code = 200
        self._events = events
        self.success = Mock()
        self.failure = Mock()

    def __enter__(self):
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc, tb):
        """Exit context manager."""
        return False

    def iter_lines(self, **kwargs):
        """Yield encoded SSE lines for the stored events."""
        yield from (_sse(event) for event in self._events)


class FakeClient:
    """Fake HTTP client that returns a prepared response."""

    def __init__(self, response):
        """Initialize FakeClient."""
        self.response = response

    def post(self, *args, **kwargs):
        """Simulate a POST request."""
        return self.response


def test_responses_tracks_multi_item_lifecycles_and_first_delta(monkeypatch):
    fired = []
    monkeypatch.setattr(
        "engine.request_processor.EventManager.fire_metric_event",
        lambda name, response_time, response_length: fired.append(name),
    )
    mapping = ConfigManager.generate_field_mapping_by_api_type("openai-responses", True)
    metrics = StreamMetrics()
    start = time.perf_counter()

    events = [
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {"id": "rs_1", "type": "reasoning"},
        },
        {
            "type": "response.reasoning_summary_text.delta",
            "item_id": "rs_1",
            "output_index": 0,
            "delta": "thinking",
        },
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {"id": "rs_1", "type": "reasoning"},
        },
        {
            "type": "response.output_item.added",
            "output_index": 1,
            "item": {"id": "msg_1", "type": "message"},
        },
        {
            "type": "response.output_text.delta",
            "item_id": "msg_1",
            "output_index": 1,
            "delta": "answer",
        },
        {
            "type": "response.output_item.done",
            "output_index": 1,
            "item": {"id": "msg_1", "type": "message"},
        },
        {
            "type": "response.output_item.added",
            "output_index": 2,
            "item": {"id": "fc_1", "type": "function_call"},
        },
        {
            "type": "response.function_call_arguments.delta",
            "item_id": "fc_1",
            "output_index": 2,
            "delta": '{"city":"Paris"}',
        },
        {
            "type": "response.output_item.done",
            "output_index": 2,
            "item": {"id": "fc_1", "type": "function_call"},
        },
        {
            "type": "response.completed",
            "response": {
                "status": "completed",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 7,
                    "total_tokens": 17,
                },
            },
        },
    ]

    for event in events:
        should_break, error, metrics = ResponsesStreamProcessor.process_stream_chunk(
            _sse(event), mapping, start, metrics, Mock()
        )

    assert should_break is True
    assert error is None
    assert fired.count("Time_to_first_output_token") == 1
    assert "Output_item_0_lifecycle" not in fired
    assert "Output_item_1_lifecycle" not in fired
    assert "Output_item_2_lifecycle" not in fired
    assert "Output_item_reasoning_lifecycle" in fired
    assert "Output_item_message_lifecycle" in fired
    assert "Output_item_tool_call_lifecycle" in fired
    assert set(metrics.output_items) == {"rs_1", "msg_1", "fc_1"}
    assert metrics.reasoning_content == "thinking"
    assert "answer" in metrics.content
    assert metrics.usage == {
        "prompt_tokens": 10,
        "completion_tokens": 7,
        "total_tokens": 17,
    }


def test_empty_delta_does_not_record_first_output(monkeypatch):
    fired = []
    monkeypatch.setattr(
        "engine.request_processor.EventManager.fire_metric_event",
        lambda name, response_time, response_length: fired.append(name),
    )
    mapping = ConfigManager.generate_field_mapping_by_api_type("openai-responses", True)
    metrics = StreamMetrics()
    ResponsesStreamProcessor.process_stream_chunk(
        _sse(
            {
                "type": "response.output_text.delta",
                "item_id": "msg_1",
                "delta": "",
            }
        ),
        mapping,
        time.perf_counter(),
        metrics,
        Mock(),
    )
    assert "Time_to_first_output_token" not in fired


def test_api_client_counts_total_time_only_on_completed(monkeypatch):
    fired = []
    monkeypatch.setattr(
        "engine.request_processor.EventManager.fire_metric_event",
        lambda name, response_time, response_length: fired.append(name),
    )
    monkeypatch.setattr(
        "engine.request_processor.EventManager.fire_failure_event",
        lambda *args, **kwargs: None,
    )
    config = GlobalConfig(
        api_type="openai-responses",
        api_path="/v1/responses",
        stream_mode=True,
    )
    response = StreamingResponse(
        [
            {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "usage": {
                        "input_tokens": 2,
                        "output_tokens": 3,
                        "total_tokens": 5,
                    },
                },
            }
        ]
    )
    _, _, usage = APIClient(config, Mock()).handle_stream_request(
        FakeClient(response),
        {"json": {"model": "test", "input": "Hi"}, "name": "/v1/responses"},
        time.perf_counter(),
    )

    response.success.assert_called_once()
    response.failure.assert_not_called()
    assert "Total_time" in fired
    assert usage["completion_tokens"] == 3
    assert usage["total_tokens"] == 5


@pytest.mark.parametrize(
    "terminal_event",
    [
        {
            "type": "response.failed",
            "response": {"status": "failed", "error": {"message": "boom"}},
        },
        {
            "type": "response.incomplete",
            "response": {
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
            },
        },
        {"type": "error", "error": {"message": "stream error"}},
    ],
)
def test_responses_terminal_errors_mark_main_request_failed(
    terminal_event, monkeypatch
):
    fired = []
    monkeypatch.setattr(
        "engine.request_processor.EventManager.fire_metric_event",
        lambda name, response_time, response_length: fired.append(name),
    )
    monkeypatch.setattr(
        "engine.request_processor.EventManager.fire_failure_event",
        lambda *args, **kwargs: None,
    )
    config = GlobalConfig(
        api_type="openai-responses",
        api_path="/v1/responses",
        stream_mode=True,
    )
    response = StreamingResponse([terminal_event])
    APIClient(config, Mock()).handle_stream_request(
        FakeClient(response),
        {"json": {"model": "test", "input": "Hi"}, "name": "/v1/responses"},
        time.perf_counter(),
    )

    response.failure.assert_called_once()
    response.success.assert_not_called()
    assert "Total_time" not in fired


def test_responses_payload_uses_input_for_default_and_dataset():
    config = GlobalConfig(
        api_type="openai-responses",
        request_payload="",
        model_name="test",
        test_data="dataset.jsonl",
    )
    builder = PayloadBuilder(config, Mock())
    kwargs, prompt = builder.prepare_request_kwargs({"prompt": "dataset prompt"})

    assert kwargs["json"]["input"] == "dataset prompt"
    assert "messages" not in kwargs["json"]
    assert prompt == "dataset prompt"


def test_responses_dataset_accepts_native_input_rows():
    parsed = parse_data_line(
        json.dumps({"id": "row_1", "input": "native input"}),
        1,
        api_type="openai-responses",
    )
    assert parsed is not None

    config = GlobalConfig(
        api_type="openai-responses",
        request_payload=json.dumps(
            {"model": "test", "stream": True, "input": "template"}
        ),
        test_data="dataset.jsonl",
    )
    kwargs, prompt = PayloadBuilder(config, Mock()).prepare_request_kwargs(
        parsed.to_dict()
    )
    assert kwargs["json"]["input"] == "native input"
    assert prompt == "native input"


def test_realtime_rps_uses_only_main_http_request_entry():
    main = SimpleNamespace(
        num_requests=10,
        num_failures=1,
        avg_response_time=100,
        current_rps=5.0,
        current_fail_per_sec=0.5,
    )
    item_metric = SimpleNamespace(
        num_requests=30,
        num_failures=0,
        avg_response_time=50,
        current_rps=15.0,
        current_fail_per_sec=0,
    )
    total = SimpleNamespace(
        current_rps=20.0,
        current_fail_per_sec=0.5,
        avg_response_time=60,
        min_response_time=10,
        max_response_time=200,
        median_response_time=50,
        num_requests=40,
        num_failures=1,
        get_response_time_percentile=lambda percentile: 150,
    )
    environment = SimpleNamespace(
        stats=SimpleNamespace(
            total=total,
            entries={
                ("/v1/responses", "POST"): main,
                ("Output_item_message_lifecycle", "metric"): item_metric,
            },
        ),
        runner=SimpleNamespace(user_count=2),
    )

    snapshot = collect_realtime_snapshot(environment, include_entries=True)

    assert snapshot["current_rps"] == 5.0
    assert snapshot["total_requests"] == 10
    assert snapshot["total_failures"] == 1
    assert snapshot["metrics"]["Output_item_message_lifecycle"]["current_rps"] == 15.0
