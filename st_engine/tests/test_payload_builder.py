"""
Tests for request payload building and field mapping.
"""

import json
from unittest.mock import Mock

import pytest

from engine.core import ConfigManager, FieldMapping, GlobalConfig
from engine.request_processor import PayloadBuilder


@pytest.fixture
def task_logger():
    return Mock()


@pytest.fixture
def config_openai():
    config = GlobalConfig()
    config.api_type = "openai-chat"
    config.model_name = "gpt-4"
    config.stream_mode = True
    return config


@pytest.fixture
def config_claude():
    config = GlobalConfig()
    config.api_type = "claude-chat"
    config.model_name = "claude-3"
    config.stream_mode = True
    return config


@pytest.fixture
def config_embeddings():
    config = GlobalConfig()
    config.api_type = "embeddings"
    config.model_name = "text-embedding-3"
    return config


def test_prepare_request_kwargs_generates_default_payload(task_logger):
    config = GlobalConfig()
    config.api_type = "openai-chat"
    config.model_name = "test-model"
    config.stream_mode = True
    config.request_payload = ""

    builder = PayloadBuilder(config, task_logger)
    result, _ = builder.prepare_request_kwargs(None)

    assert result is not None
    payload = result["json"]
    assert payload["model"] == "test-model"
    assert payload["stream"] is True
    assert payload["messages"][0]["role"] == "user"


def test_openai_text_only(config_openai, task_logger):
    builder = PayloadBuilder(config_openai, task_logger)
    payload = {
        "model": "gpt-4",
        "stream": True,
        "messages": [{"role": "system", "content": "You are a helpful assistant."}],
    }

    builder._update_openai_chat_payload(payload, "Hello", "", "")

    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["role"] == "user"
    assert payload["messages"][1]["content"] == "Hello"


def test_openai_multimodal(config_openai, task_logger):
    builder = PayloadBuilder(config_openai, task_logger)
    payload = {"model": "gpt-4", "stream": True, "messages": []}
    builder._update_openai_chat_payload(
        payload, "What's in this image?", "https://example.com/image.jpg", ""
    )

    assert payload["messages"][0]["role"] == "user"
    assert payload["messages"][0]["content"][0]["type"] == "text"
    assert payload["messages"][0]["content"][1]["type"] == "image_url"
    assert (
        payload["messages"][0]["content"][1]["image_url"]["url"]
        == "https://example.com/image.jpg"
    )


def test_openai_base64_priority(config_openai, task_logger):
    builder = PayloadBuilder(config_openai, task_logger)
    payload = {"model": "gpt-4", "messages": []}
    builder._update_openai_chat_payload(
        payload, "Test", "https://example.com/url.jpg", "base64data"
    )
    image_url = payload["messages"][0]["content"][1]["image_url"]["url"]
    assert image_url.startswith("data:image/jpeg;base64,")
    assert "base64data" in image_url


def test_openai_updates_existing_user_message(config_openai, task_logger):
    builder = PayloadBuilder(config_openai, task_logger)
    payload = {
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Old message"},
        ],
    }
    builder._update_openai_chat_payload(payload, "New message", "", "")
    assert payload["messages"][1]["content"] == "New message"


def test_claude_text_only(config_claude, task_logger):
    builder = PayloadBuilder(config_claude, task_logger)
    payload = {"model": "claude-3", "max_tokens": 8192, "messages": []}
    builder._update_claude_chat_payload(payload, "Explain", "", "")

    assert payload["messages"][0]["role"] == "user"
    assert payload["messages"][0]["content"][0]["type"] == "text"


def test_claude_multimodal(config_claude, task_logger):
    builder = PayloadBuilder(config_claude, task_logger)
    payload = {"model": "claude-3", "max_tokens": 4096, "messages": []}
    builder._update_claude_chat_payload(
        payload, "Describe", "https://example.com/photo.jpg", "base64encodeddata"
    )
    user_content = payload["messages"][0]["content"]
    assert len(user_content) == 3
    assert user_content[1]["type"] == "image"
    assert user_content[1]["source"]["type"] == "url"
    assert user_content[2]["source"]["type"] == "base64"


def test_embeddings_update(config_embeddings, task_logger):
    builder = PayloadBuilder(config_embeddings, task_logger)
    payload = {"model": "text-embedding-3", "encoding_format": "float"}
    builder._update_embeddings_payload(payload, "Embed this text")
    assert payload["input"] == "Embed this text"


def test_set_field_value_nested_path(task_logger):
    builder = PayloadBuilder(GlobalConfig(), task_logger)
    payload = {"output": {"text": ""}}
    builder._set_field_value(payload, "output.text", "new_value")
    assert payload["output"]["text"] == "new_value"


def test_set_field_value_list_index(task_logger):
    builder = PayloadBuilder(GlobalConfig(), task_logger)
    payload = {"messages": [{"content": "old_content"}]}
    builder._set_field_value(payload, "messages.0.content", "new_content")
    assert payload["messages"][0]["content"] == "new_content"


def test_update_payload_by_field_mapping(task_logger):
    builder = PayloadBuilder(GlobalConfig(), task_logger)
    payload = {"input": "", "image": ""}
    field_mapping = FieldMapping(prompt="input", image="image")
    builder._update_payload_by_field_mapping(
        payload, "prompt", "http://example.com/img.jpg", "", field_mapping
    )
    assert payload["input"] == "prompt"
    assert payload["image"] == "http://example.com/img.jpg"


def test_parse_field_mapping_defaults():
    mapping = ConfigManager.parse_field_mapping("")
    assert mapping.stream_prefix == "data:"
    assert mapping.data_format == "json"
    assert mapping.stop_flag == "[DONE]"


def test_parse_headers_and_cookies(task_logger):
    headers_json = '{"Authorization": "Bearer token123", "Custom-Header": "value"}'
    cookies_json = '{"session_id": "abc123", "auth_token": "xyz789"}'
    headers = ConfigManager.parse_headers(headers_json, task_logger)
    cookies = ConfigManager.parse_cookies(cookies_json, task_logger)

    assert headers["Authorization"] == "Bearer token123"
    assert headers["Custom-Header"] == "value"
    assert cookies["session_id"] == "abc123"
    assert cookies["auth_token"] == "xyz789"
