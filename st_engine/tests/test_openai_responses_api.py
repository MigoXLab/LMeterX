"""OpenAI Responses API payload and streaming metric tests."""

from unittest.mock import MagicMock, call

import pytest

from engine.core import ConfigManager, GlobalConfig, StreamMetrics
from engine.request_processor import APIClient, PayloadBuilder, StreamProcessor
from utils.event_handler import EventManager


def _process(event, metrics, mapping, logger, start_time=9.0):
    import orjson

    return StreamProcessor.process_stream_chunk(
        b"data: " + orjson.dumps(event),
        mapping,
        start_time,
        metrics,
        logger,
        "openai-responses",
    )


def test_responses_default_field_mapping():
    mapping = ConfigManager.generate_field_mapping_by_api_type(
        "openai-responses", stream_mode=True
    )

    assert mapping.prompt == "input"
    assert mapping.end_field == "type"
    assert mapping.stop_flag == "response.completed"
    assert mapping.content == ""
    assert mapping.prompt_tokens == "response.usage.input_tokens"


def test_responses_payload_uses_input():
    config = GlobalConfig()
    config.api_type = "openai-responses"
    config.model_name = "gpt-test"
    config.stream_mode = True
    config.request_payload = ""
    builder = PayloadBuilder(config, MagicMock())

    request_kwargs, prompt = builder.prepare_request_kwargs(None)

    assert request_kwargs["json"] == {
        "model": "gpt-test",
        "stream": True,
        "input": "Hi",
    }
    assert prompt == "Hi"


def test_responses_dataset_updates_input():
    config = GlobalConfig()
    config.api_type = "openai-responses"
    builder = PayloadBuilder(config, MagicMock())
    payload = {"model": "gpt-test", "stream": True, "input": "old"}

    builder._update_openai_responses_payload(
        payload, "new prompt", "", "", {"prompt": "new prompt"}
    )

    assert payload["input"] == "new prompt"


def test_first_item_delta_sets_ttft_and_item_durations(monkeypatch):
    mapping = ConfigManager.generate_field_mapping_by_api_type(
        "openai-responses", stream_mode=True
    )
    metrics = StreamMetrics()
    logger = MagicMock()
    metric_event = MagicMock()
    monkeypatch.setattr(EventManager, "fire_metric_event", metric_event)
    perf_values = iter([10.0, 10.2, 10.3, 10.7])
    monkeypatch.setattr(
        "engine.request_processor.time.perf_counter", lambda: next(perf_values)
    )

    should_break, error, metrics = _process(
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {"id": "call_1", "type": "function_call"},
        },
        metrics,
        mapping,
        logger,
    )
    assert not should_break
    assert error is None

    # Tool arguments are output item content too, so their first non-empty
    # delta defines TTFT when they arrive before text/reasoning deltas.
    _, _, metrics = _process(
        {
            "type": "response.function_call_arguments.delta",
            "item_id": "call_1",
            "output_index": 0,
            "delta": '{"city":',
        },
        metrics,
        mapping,
        logger,
    )
    _, _, metrics = _process(
        {
            "type": "response.output_text.delta",
            "item_id": "call_1",
            "output_index": 0,
            "delta": "hello",
        },
        metrics,
        mapping,
        logger,
    )
    _, _, metrics = _process(
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {"id": "call_1", "type": "function_call"},
        },
        metrics,
        mapping,
        logger,
    )

    assert metrics.time_to_first_output_token_ms == pytest.approx(1200)
    assert metrics.content == "hello"
    assert metric_event.call_args_list == [
        call("Output_item_tool_call_lifecycle", pytest.approx(700), 0),
    ]


def test_multiple_output_items_are_timed_independently(monkeypatch):
    mapping = ConfigManager.generate_field_mapping_by_api_type(
        "openai-responses", stream_mode=True
    )
    metrics = StreamMetrics()
    logger = MagicMock()
    metric_event = MagicMock()
    monkeypatch.setattr(EventManager, "fire_metric_event", metric_event)
    perf_values = iter([1.0, 1.1, 1.2, 1.4, 1.5, 1.9])
    monkeypatch.setattr(
        "engine.request_processor.time.perf_counter", lambda: next(perf_values)
    )

    events = [
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {"id": "reason_1", "type": "reasoning"},
        },
        {
            "type": "response.reasoning_summary_text.delta",
            "item_id": "reason_1",
            "output_index": 0,
            "delta": "thinking",
        },
        {
            "type": "response.output_item.added",
            "output_index": 1,
            "item": {"id": "msg_1", "type": "message"},
        },
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {"id": "reason_1", "type": "reasoning"},
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
    ]
    for event in events:
        _, error, metrics = _process(event, metrics, mapping, logger, 0.5)
        assert error is None

    item_metric_names = [
        metric_call.args[0]
        for metric_call in metric_event.call_args_list
        if metric_call.args[0].startswith("Output_item_")
    ]
    assert item_metric_names.count("Output_item_reasoning_lifecycle") == 1
    assert item_metric_names.count("Output_item_message_lifecycle") == 1
    assert "Output_item_reasoning_duration" not in item_metric_names
    assert "Output_item_message_duration" not in item_metric_names
    assert "Output_item_duration" not in item_metric_names
    assert "Output_item_lifecycle_duration" not in item_metric_names


def test_same_output_index_different_item_id_are_tracked_separately(monkeypatch):
    mapping = ConfigManager.generate_field_mapping_by_api_type(
        "openai-responses", stream_mode=True
    )
    metrics = StreamMetrics()
    logger = MagicMock()
    metric_event = MagicMock()
    monkeypatch.setattr(EventManager, "fire_metric_event", metric_event)
    perf_values = iter([1.0, 1.1, 1.2, 1.4, 1.5, 1.8])
    monkeypatch.setattr(
        "engine.request_processor.time.perf_counter", lambda: next(perf_values)
    )

    events = [
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "content_index": 0,
            "item": {"id": "rs_1", "type": "reasoning"},
        },
        {
            "type": "response.reasoning_text.delta",
            "item_id": "rs_1",
            "output_index": 0,
            "content_index": 0,
            "delta": "think",
        },
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "content_index": 0,
            "item": {"id": "msg_1", "type": "message"},
        },
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "content_index": 0,
            "item": {"id": "rs_1", "type": "reasoning"},
        },
        {
            "type": "response.output_text.delta",
            "item_id": "msg_1",
            "output_index": 0,
            "content_index": 0,
            "delta": "answer",
        },
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "content_index": 0,
            "item": {"id": "msg_1", "type": "message"},
        },
    ]
    for event in events:
        _, error, metrics = _process(event, metrics, mapping, logger, 0.5)
        assert error is None

    lifecycle_calls = [
        metric_call
        for metric_call in metric_event.call_args_list
        if metric_call.args[0]
        in {"Output_item_reasoning_lifecycle", "Output_item_message_lifecycle"}
    ]
    assert [metric_call.args[0] for metric_call in lifecycle_calls] == [
        "Output_item_reasoning_lifecycle",
        "Output_item_message_lifecycle",
    ]
    assert lifecycle_calls[0].args[1] == pytest.approx(400)
    assert lifecycle_calls[1].args[1] == pytest.approx(600)


def test_completed_event_extracts_usage_and_terminates():
    mapping = ConfigManager.generate_field_mapping_by_api_type(
        "openai-responses", stream_mode=True
    )

    should_break, error, metrics = _process(
        {
            "type": "response.completed",
            "response": {
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 8,
                    "total_tokens": 20,
                }
            },
        },
        StreamMetrics(),
        mapping,
        MagicMock(),
    )

    assert should_break
    assert error is None
    assert metrics.usage == {
        "prompt_tokens": 12,
        "completion_tokens": 8,
        "total_tokens": 20,
    }


def test_responses_stream_completes_request_and_returns_usage(monkeypatch):
    config = GlobalConfig()
    config.api_type = "openai-responses"
    config.api_path = "/v1/responses"
    config.stream_mode = True
    client = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.headers = {}
    response.iter_lines.return_value = iter(
        [
            b'data: {"type":"response.output_item.added","output_index":0,'
            b'"item":{"id":"msg_1","type":"message"}}',
            b"",
            b'data: {"type":"response.output_text.delta","item_id":"msg_1",'
            b'"output_index":0,"delta":"hello"}',
            b"",
            b'data: {"type":"response.output_item.done","output_index":0,'
            b'"item":{"id":"msg_1","type":"message"}}',
            b"",
            b'data: {"type":"response.completed","response":{"usage":'
            b'{"input_tokens":2,"output_tokens":1,"total_tokens":3}}}',
            b"",
        ]
    )
    client.post.return_value.__enter__.return_value = response
    client.post.return_value.__exit__.return_value = False
    metric_event = MagicMock()
    monkeypatch.setattr(EventManager, "fire_metric_event", metric_event)

    reasoning, content, usage = APIClient(config, MagicMock()).handle_stream_request(
        client,
        {
            "json": {"model": "gpt-test", "stream": True, "input": "Hi"},
            "headers": {"Content-Type": "application/json"},
            "catch_response": True,
            "name": "/v1/responses",
            "verify": False,
        },
        1.0,
    )

    assert reasoning == ""
    assert content == "hello"
    assert usage == {
        "prompt_tokens": 2,
        "completion_tokens": 1,
        "total_tokens": 3,
    }
    assert usage.request_succeeded is True
    response.success.assert_called_once()
    response.failure.assert_not_called()
    emitted_names = [metric_call.args[0] for metric_call in metric_event.call_args_list]
    assert "Time_to_first_output_token" in emitted_names
    assert "Output_item_message_lifecycle" in emitted_names
    assert "Output_item_message_duration" not in emitted_names
    assert "Total_time" in emitted_names
