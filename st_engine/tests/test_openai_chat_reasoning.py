"""OpenAI-compatible Chat Completions reasoning field tests."""

from unittest.mock import MagicMock

import orjson
import pytest

from engine.core import ConfigManager, GlobalConfig, StreamMetrics
from engine.request_processor import StreamProcessor


def _process(delta, mapping, metrics, logger, start_time=10.0):
    chunk = b"data: " + orjson.dumps({"choices": [{"delta": delta}]})
    return StreamProcessor.process_stream_chunk(
        chunk, mapping, start_time, metrics, logger, "openai-chat"
    )


@pytest.mark.parametrize(
    "reasoning_delta",
    [
        {"reasoning_content": "thinking"},
        {"reasoning": "thinking"},
        {"reasoning_content": "", "reasoning": "thinking"},
    ],
)
def test_openai_chat_reasoning_fields_record_first_reasoning_token(
    monkeypatch, reasoning_delta
):
    mapping = ConfigManager.generate_field_mapping_by_api_type("openai-chat", True)
    assert mapping.reasoning_content_aliases == ("choices.0.delta.reasoning",)
    metrics = StreamMetrics()
    logger = MagicMock()
    perf_values = iter([10.5, 13.0, 13.0])
    monkeypatch.setattr(
        "engine.request_processor.time.perf_counter", lambda: next(perf_values)
    )

    should_break, error, metrics = _process(reasoning_delta, mapping, metrics, logger)
    assert not should_break
    assert error is None
    assert metrics.reasoning_content == "thinking"
    assert metrics.time_to_first_reasoning_token_ms == pytest.approx(500)
    assert metrics.time_to_first_output_token_ms is None

    _, error, metrics = _process({"content": "answer"}, mapping, metrics, logger)
    assert error is None
    assert metrics.time_to_first_reasoning_token_ms == pytest.approx(500)
    assert metrics.time_to_first_output_token_ms == pytest.approx(3000)


def test_openai_chat_reasoning_alias_does_not_override_custom_mapping():
    config = GlobalConfig(
        api_type="openai-chat",
        field_mapping=(
            '{"content":"choices.0.delta.content",'
            '"reasoning_content":"choices.0.delta.custom_reasoning"}'
        ),
    )
    mapping = ConfigManager.resolve_field_mapping(config, required_fields=("content",))
    assert mapping.reasoning_content_aliases == ()

    _, error, metrics = _process(
        {"reasoning": "ignored"},
        mapping,
        StreamMetrics(),
        MagicMock(),
    )

    assert error is None
    assert metrics.reasoning_content == ""
    assert metrics.time_to_first_reasoning_token_ms is None


def test_explicit_default_mapping_keeps_openai_chat_reasoning_alias():
    config = GlobalConfig(
        api_type="openai-chat",
        field_mapping=(
            '{"content":"choices.0.delta.content",'
            '"reasoning_content":"choices.0.delta.reasoning_content"}'
        ),
    )

    mapping = ConfigManager.resolve_field_mapping(config, required_fields=("content",))

    assert mapping.reasoning_content_aliases == ("choices.0.delta.reasoning",)
