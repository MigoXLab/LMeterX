"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import json
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple, Union

from gevent import queue
from gevent.lock import Semaphore

from config.base import DEFAULT_API_PATH, DEFAULT_CONTENT_TYPE
from utils.logger import logger


# === DATA CLASSES ===
@dataclass
class StreamMetrics:
    """Metrics for streaming responses."""

    first_token_received: bool = False
    first_thinking_received: bool = False
    reasoning_is_active: bool = False
    reasoning_ended: bool = False
    first_output_token_time: Optional[float] = None
    first_thinking_token_time: Optional[float] = None
    content: str = ""
    reasoning_content: str = ""
    usage: Optional[Dict[str, Optional[int]]] = field(default_factory=dict)


@dataclass
class GlobalConfig:
    """Global configuration for all users."""

    task_id: str = ""
    api_type: str = "openai-chat"  # API type for auto-generating field mapping
    api_path: str = DEFAULT_API_PATH
    headers: Dict[str, str] = field(
        default_factory=lambda: {"Content-Type": DEFAULT_CONTENT_TYPE}
    )
    cookies: Optional[Dict[str, str]] = None
    request_payload: Optional[str] = None
    model_name: Optional[str] = None
    user_prompt: Optional[str] = None
    stream_mode: bool = True
    chat_type: int = 0  # Built-in dataset selector (0=text, 1=ShareGPT, 2=vision)
    cert_file: Optional[str] = None
    key_file: Optional[str] = None
    cert_config: Optional[Union[str, Tuple[str, str]]] = None
    field_mapping: Optional[str] = None
    test_data: Optional[str] = None
    duration: int = 60


@dataclass
class FieldMapping:
    """Field mapping configuration for custom APIs."""

    stream_prefix: str = "data:"
    data_format: str = "json"
    stop_flag: str = "[DONE]"
    end_prefix: str = ""
    end_field: str = ""
    content: str = ""
    reasoning_content: str = ""
    prompt: str = ""
    image: str = ""
    prompt_tokens: str = ""
    completion_tokens: str = ""
    total_tokens: str = ""


@dataclass
class TokenStats:
    """Token stats for each request."""

    reqs_count: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


# === GLOBAL STATE MANAGEMENT ===
class GlobalStateManager:
    """Manages global state for Locust testing."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize global state."""
        self._config: Optional[GlobalConfig] = None
        self._start_time: Optional[float] = None
        self._token_stats = TokenStats()
        self._logger_cache: Dict[str, Any] = {}
        self._ssl_context: Optional[Any] = None
        self._task_queue: Optional[Dict[str, queue.Queue]] = None
        self._gevent_lock: Optional[Semaphore] = None
        self._file_lock = threading.Lock()

        self._worker_count: int = 0
        self._concurrent_users: int = 0

        # Initialize gevent lock
        try:
            self._gevent_lock = Semaphore(1)
        except Exception as e:
            logger.warning(f"Failed to create gevent semaphore: {e}")
            self._gevent_lock = SimpleLock()

    @property
    def config(self) -> GlobalConfig:
        """Get global configuration."""
        if self._config is None:
            self._config = GlobalConfig()
        return self._config

    @property
    def start_time(self) -> Optional[float]:
        """Get test start time."""
        return self._start_time

    @start_time.setter
    def start_time(self, value: float):
        """Set test start time."""
        self._start_time = value

    @property
    def token_stats(self) -> TokenStats:
        """Get token stats."""
        return self._token_stats

    @property
    def worker_count(self) -> int:
        return self._worker_count

    @worker_count.setter
    def worker_count(self, value: int):
        self._worker_count = value

    @property
    def concurrent_users(self) -> int:
        return self._concurrent_users

    @concurrent_users.setter
    def concurrent_users(self, value: int):
        self._concurrent_users = value

    def get_task_logger(self, task_id: str = ""):
        """Get task logger."""
        if not task_id:
            return logger

        if self._gevent_lock is not None:
            with self._gevent_lock:
                if task_id not in self._logger_cache:
                    self._logger_cache[task_id] = logger.bind(task_id=task_id)
                return self._logger_cache[task_id]
        else:
            # Fallback when lock is None
            if task_id not in self._logger_cache:
                self._logger_cache[task_id] = logger.bind(task_id=task_id)
            return self._logger_cache[task_id]


class SimpleLock:
    """Simple lock implementation as fallback when multiprocessing fails."""

    def __enter__(self):
        pass

    def __exit__(self, *args):
        pass


# === CONFIGURATION MANAGEMENT ===
class ConfigManager:
    """Manages configuration parsing and validation."""

    @staticmethod
    def parse_headers(
        headers_input: Union[str, Dict[str, str]], task_logger
    ) -> Dict[str, str]:
        """Parse headers from string or dict input."""
        default_headers = {"Content-Type": DEFAULT_CONTENT_TYPE}

        if isinstance(headers_input, dict):
            return headers_input

        if isinstance(headers_input, str) and headers_input.strip():
            try:
                parsed_headers = json.loads(headers_input)
                if not isinstance(parsed_headers, dict):
                    raise ValueError("Headers must be a JSON object")
                return parsed_headers
            except (json.JSONDecodeError, ValueError) as e:
                task_logger.error(
                    f"Failed to parse headers JSON '{headers_input}': {e}"
                )
                return default_headers

        return default_headers

    @staticmethod
    def parse_cookies(
        cookies_input: Union[str, Dict[str, str]], task_logger
    ) -> Optional[Dict[str, str]]:
        """Parse cookies from string or dict input."""
        if isinstance(cookies_input, dict):
            return cookies_input

        if isinstance(cookies_input, str) and cookies_input.strip():
            try:
                parsed_cookies = json.loads(cookies_input)
                if not isinstance(parsed_cookies, dict):
                    raise ValueError("Cookies must be a JSON object")
                return parsed_cookies
            except (json.JSONDecodeError, ValueError) as e:
                task_logger.error(
                    f"Failed to parse cookies JSON '{cookies_input}': {e}"
                )
                return None

        return None

    @staticmethod
    def parse_field_mapping(field_mapping_str: str) -> FieldMapping:
        """Parse field mapping configuration."""
        if not field_mapping_str:
            return FieldMapping()

        try:
            mapping_dict = json.loads(str(field_mapping_str))
            if not isinstance(mapping_dict, dict):
                return FieldMapping()

            field_mapping = FieldMapping()
            for key, value in mapping_dict.items():
                if hasattr(field_mapping, key) and value is not None:
                    setattr(field_mapping, key, value)

            return field_mapping
        except (json.JSONDecodeError, TypeError):
            return FieldMapping()

    @staticmethod
    def generate_field_mapping_by_api_type(
        api_type: str, stream_mode: bool = True
    ) -> FieldMapping:
        """Generate default field mapping based on API type.

        Args:
            api_type: The API type (openai-chat, claude-chat, embeddings, custom-chat)
            stream_mode: Whether the API is in streaming mode

        Returns:
            FieldMapping with appropriate defaults for the API type
        """
        if api_type == "openai-chat":
            return FieldMapping(
                stream_prefix="data:",
                data_format="json",
                stop_flag="[DONE]",
                end_prefix="data:",
                end_field="",
                content=(
                    "choices.0.delta.content"
                    if stream_mode
                    else "choices.0.message.content"
                ),
                reasoning_content=(
                    "choices.0.delta.reasoning_content"
                    if stream_mode
                    else "choices.0.message.reasoning_content"
                ),
                prompt="messages.0.content.0.text",
                image="messages.0.content.-1.image_url.url",
                prompt_tokens="usage.prompt_tokens",
                completion_tokens="usage.completion_tokens",
                total_tokens="usage.total_tokens",
            )
        elif api_type == "claude-chat":
            return FieldMapping(
                stream_prefix="data:",
                data_format="json",
                stop_flag="message_stop",
                end_prefix="data:",
                end_field="type",
                content="delta.text" if stream_mode else "content.-1.text",
                reasoning_content=(
                    "delta.thinking" if stream_mode else "content.0.thinking"
                ),
                prompt="messages.0.content.0.text",
                image="messages.0.content.-1.source.data",
                prompt_tokens="usage.input_tokens",
                completion_tokens="usage.output_tokens",
                total_tokens="",
            )
        elif api_type == "embeddings":
            return FieldMapping(
                stream_prefix="",
                data_format="json",
                stop_flag="",
                end_prefix="",
                end_field="",
                content="",
                reasoning_content="",
                prompt="input",
                image="",
                prompt_tokens="",
                completion_tokens="",
                total_tokens="",
            )
        else:
            # For custom-chat or unknown types, return empty field mapping
            return FieldMapping()


# === CERTIFICATE MANAGEMENT ===
class CertificateManager:
    """Manages SSL certificate configuration."""

    @staticmethod
    def configure_certificates(
        cert_file: Optional[str], key_file: Optional[str], task_logger
    ) -> Optional[Union[str, Tuple[str, str]]]:
        """Configure client certificate and key for SSL connections.

        Args:
            cert_file (Optional[str]): Path to certificate file
            key_file (Optional[str]): Path to key file
            task_logger: Logger instance for task-specific logging

        Returns:
            Optional[Union[str, Tuple[str, str]]]:
                - None if no certificates provided
                - str if only cert_file provided (for combined cert+key files)
                - Tuple[str, str] if both cert and key files provided

        Raises:
            ValueError: If certificate configuration is invalid
        """
        if not cert_file and not key_file:
            return None

        if cert_file and not key_file:
            # Single file contains both certificate and key
            return cert_file

        if cert_file and key_file:
            # Separate certificate and key files
            return (cert_file, key_file)

        if not cert_file and key_file:
            # Key file without certificate file is invalid, but don't fail
            return None

        return None


# === VALIDATION ===
class ValidationManager:
    """Handles configuration validation."""

    @staticmethod
    def validate_config(config: GlobalConfig, task_logger) -> bool:
        """Validate global configuration before starting tests."""
        if not config.task_id:
            task_logger.error("Task ID is required but not provided")
            return False

        if not config.model_name:
            task_logger.error("Model name is required")
            return False

        if not config.request_payload:
            task_logger.error("Request payload is required for all API endpoints")
            return False

        return True
