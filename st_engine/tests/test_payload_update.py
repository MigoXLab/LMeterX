"""
Test payload update logic for different API types.

Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import json

import pytest

from engine.core import GlobalConfig
from engine.request_processor import PayloadBuilder
from utils.logger import logger


class TestPayloadUpdate:
    """Test payload update methods for different API types."""

    @pytest.fixture
    def config_openai(self):
        """OpenAI Chat configuration."""
        config = GlobalConfig()
        config.api_type = "openai-chat"
        config.model_name = "gpt-4"
        config.stream_mode = True
        return config

    @pytest.fixture
    def config_claude(self):
        """Claude Chat configuration."""
        config = GlobalConfig()
        config.api_type = "claude-chat"
        config.model_name = "claude-3"
        config.stream_mode = True
        return config

    @pytest.fixture
    def config_embeddings(self):
        """Embeddings configuration."""
        config = GlobalConfig()
        config.api_type = "embeddings"
        config.model_name = "text-embedding-3"
        return config

    def test_openai_text_only(self, config_openai):
        """Test OpenAI Chat with text-only dataset."""
        builder = PayloadBuilder(config_openai, logger)

        # Original payload with system message
        payload = {
            "model": "gpt-4",
            "stream": True,
            "messages": [{"role": "system", "content": "You are a helpful assistant."}],
        }

        # Dataset with text only
        prompt_data = {
            "prompt": "Hello, how are you?",
            "image_url": "",
            "image_base64": "",
        }

        builder._update_openai_chat_payload(
            payload,
            prompt_data["prompt"],
            prompt_data["image_url"],
            prompt_data["image_base64"],
        )

        # Verify results
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"
        assert payload["messages"][1]["content"] == "Hello, how are you?"
        assert payload["model"] == "gpt-4"
        assert payload["stream"] is True

    def test_openai_multimodal(self, config_openai):
        """Test OpenAI Chat with multimodal dataset."""
        builder = PayloadBuilder(config_openai, logger)

        payload = {"model": "gpt-4", "stream": True, "messages": []}

        prompt_data = {
            "prompt": "What's in this image?",
            "image_url": "https://example.com/image.jpg",
            "image_base64": "",
        }

        builder._update_openai_chat_payload(
            payload,
            prompt_data["prompt"],
            prompt_data["image_url"],
            prompt_data["image_base64"],
        )

        # Verify results
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["role"] == "user"
        assert isinstance(payload["messages"][0]["content"], list)
        assert payload["messages"][0]["content"][0]["type"] == "text"
        assert payload["messages"][0]["content"][0]["text"] == "What's in this image?"
        assert payload["messages"][0]["content"][1]["type"] == "image_url"
        assert (
            payload["messages"][0]["content"][1]["image_url"]["url"]
            == "https://example.com/image.jpg"
        )

    def test_openai_update_existing_user_message(self, config_openai):
        """Test OpenAI Chat updates existing user message."""
        builder = PayloadBuilder(config_openai, logger)

        # Payload with existing user message
        payload = {
            "model": "gpt-4",
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Old message"},
            ],
        }

        prompt_data = {
            "prompt": "New message from dataset",
            "image_url": "",
            "image_base64": "",
        }

        builder._update_openai_chat_payload(
            payload,
            prompt_data["prompt"],
            prompt_data["image_url"],
            prompt_data["image_base64"],
        )

        # Verify user message was updated
        assert len(payload["messages"]) == 2
        assert payload["messages"][1]["content"] == "New message from dataset"

    def test_claude_text_only(self, config_claude):
        """Test Claude Chat with text-only dataset."""
        builder = PayloadBuilder(config_claude, logger)

        payload = {
            "model": "claude-3",
            "max_tokens": 8192,
            "messages": [],
        }

        prompt_data = {
            "prompt": "Explain quantum computing",
            "image_url": "",
            "image_base64": "",
        }

        builder._update_claude_chat_payload(
            payload,
            prompt_data["prompt"],
            prompt_data["image_url"],
            prompt_data["image_base64"],
        )

        # Verify results
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["role"] == "user"
        assert isinstance(payload["messages"][0]["content"], list)
        assert payload["messages"][0]["content"][0]["type"] == "text"
        assert (
            payload["messages"][0]["content"][0]["text"] == "Explain quantum computing"
        )
        assert payload["max_tokens"] == 8192

    def test_claude_multimodal(self, config_claude):
        """Test Claude Chat with multimodal dataset."""
        builder = PayloadBuilder(config_claude, logger)

        payload = {"model": "claude-3", "max_tokens": 4096, "messages": []}

        prompt_data = {
            "prompt": "Describe this image",
            "image_url": "https://example.com/photo.jpg",
            "image_base64": "base64encodeddata",
        }

        builder._update_claude_chat_payload(
            payload,
            prompt_data["prompt"],
            prompt_data["image_url"],
            prompt_data["image_base64"],
        )

        # Verify results
        assert len(payload["messages"]) == 1
        user_content = payload["messages"][0]["content"]
        assert len(user_content) == 3  # text + url image + base64 image
        assert user_content[0]["type"] == "text"
        assert user_content[1]["type"] == "image"
        assert user_content[1]["source"]["type"] == "url"
        assert user_content[2]["type"] == "image"
        assert user_content[2]["source"]["type"] == "base64"

    def test_embeddings_update(self, config_embeddings):
        """Test Embeddings API payload update."""
        builder = PayloadBuilder(config_embeddings, logger)

        payload = {"model": "text-embedding-3", "encoding_format": "float"}

        prompt_data = {"prompt": "Embed this text", "image_url": "", "image_base64": ""}

        builder._update_embeddings_payload(payload, prompt_data["prompt"])

        # Verify results
        assert payload["input"] == "Embed this text"
        assert payload["model"] == "text-embedding-3"
        assert payload["encoding_format"] == "float"

    def test_openai_base64_priority(self, config_openai):
        """Test that base64 image takes priority over URL."""
        builder = PayloadBuilder(config_openai, logger)

        payload = {"model": "gpt-4", "messages": []}

        prompt_data = {
            "prompt": "Test",
            "image_url": "https://example.com/url.jpg",
            "image_base64": "base64data",
        }

        builder._update_openai_chat_payload(
            payload,
            prompt_data["prompt"],
            prompt_data["image_url"],
            prompt_data["image_base64"],
        )

        # Verify base64 is used
        image_url = payload["messages"][0]["content"][1]["image_url"]["url"]
        assert image_url.startswith("data:image/jpeg;base64,")
        assert "base64data" in image_url
