"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.

"""

import time
from typing import Any, Dict, List, Optional, Tuple

import orjson

from config.base import DEFAULT_PROMPT
from config.business import METRIC_TTOC, METRIC_TTT
from engine.core import (
    ConfigManager,
    FieldMapping,
    GlobalConfig,
    GlobalStateManager,
    StreamMetrics,
)
from utils.common import safe_int_convert
from utils.error_handler import ErrorResponse
from utils.event_handler import EventManager

global_state = GlobalStateManager()


# === STREAM PROCESSING ===
class StreamProcessor:
    """Handles streaming response processing."""

    @staticmethod
    def get_field_value(data: Dict[str, Any], path: str) -> Any:
        """Get value from nested dictionary using dot-separated path."""
        if not path or not isinstance(data, dict):
            return ""

        try:
            keys = path.split(".")
            current = data

            for key in keys:
                # Check if key is a valid integer (including negative numbers)
                try:
                    index = int(key)
                    if isinstance(current, list):
                        current = current[index]
                    else:
                        return ""
                except ValueError:
                    # Key is not an integer, treat as dict key
                    if isinstance(current, list) and current:
                        if isinstance(current[0], dict):
                            current = current[0].get(key, {})
                        else:
                            return ""
                    elif isinstance(current, dict):
                        current = current.get(key, {})
                    else:
                        return ""

            # Return the actual value, preserve original type
            if current is None:
                return ""
            return current
        except (KeyError, IndexError, TypeError, ValueError):
            return ""

    @staticmethod
    def is_sse_event_line(chunk_str: str) -> bool:
        """Check if the line is an SSE event line (not data line) that should be skipped.
        Only skip event control lines, not data lines that start with 'data: '.
        """
        chunk_str = chunk_str.strip()

        # Check for SSE event control prefixes that should be skipped
        # Only 'event:', 'id:', 'retry:' are control lines, 'data:' contains actual data
        control_prefixes = ["event:", "event: ", "id:", "id: ", "retry:", "retry: "]

        for prefix in control_prefixes:
            if chunk_str.startswith(prefix):
                return True

        return False

    @staticmethod
    def remove_chunk_prefix(chunk_str: str, field_mapping: FieldMapping) -> str:
        """Remove prefix from chunk string based on field mapping configuration."""
        result = chunk_str.strip()
        if field_mapping.end_prefix and result.startswith(field_mapping.end_prefix):
            result = result[len(field_mapping.end_prefix) :].strip()
        elif field_mapping.stream_prefix and chunk_str.startswith(
            field_mapping.stream_prefix
        ):
            result = result[len(field_mapping.stream_prefix) :].strip()
        elif chunk_str.startswith("data: "):
            result = result[len("data: ") :].strip()
        elif chunk_str.startswith("event: "):
            result = result[len("event: ") :].strip()
        return result

    @staticmethod
    def check_stop_flag(processed_chunk: str, field_mapping: FieldMapping) -> bool:
        """Check if the processed chunk matches the stop flag."""
        stop_flag = (
            field_mapping.stop_flag.strip() if field_mapping.stop_flag else "[DONE]"
        )
        return processed_chunk == stop_flag

    @staticmethod
    def check_end_field_stop(
        processed_chunk: Dict[str, Any], field_mapping: FieldMapping
    ) -> bool:
        """Check if end_field value matches stop flag."""
        if not field_mapping.end_field:
            return False

        stop_flag = (
            field_mapping.stop_flag.strip() if field_mapping.stop_flag else "[DONE]"
        )
        end_value = StreamProcessor.get_field_value(
            processed_chunk, field_mapping.end_field
        )
        # Convert to string for comparison
        end_value = str(end_value) if end_value else ""
        return end_value == stop_flag

    @staticmethod
    def extract_metrics_from_chunk(
        chunk_data: Dict[str, Any],
        field_mapping: FieldMapping,
        metrics: StreamMetrics,
        start_time: float,
        task_logger,
    ) -> StreamMetrics:
        """Extract and update metrics from chunk data."""
        # Initialize usage dict if not present
        if metrics.usage is None:
            metrics.usage = {}
        # Extract usage tokens
        usage_extracted = False

        # Update prompt tokens if field mapping exists
        if field_mapping.prompt_tokens:
            prompt_tokens_value = safe_int_convert(
                StreamProcessor.get_field_value(chunk_data, field_mapping.prompt_tokens)
            )

            if prompt_tokens_value > 0:
                metrics.usage["prompt_tokens"] = prompt_tokens_value

        # Update completion tokens if field mapping exists
        if field_mapping.completion_tokens:
            completion_tokens_value = safe_int_convert(
                StreamProcessor.get_field_value(
                    chunk_data, field_mapping.completion_tokens
                )
            )
            if completion_tokens_value > 0:
                metrics.usage["completion_tokens"] = completion_tokens_value
                usage_extracted = True

        # Update total tokens if field mapping exists
        if field_mapping.total_tokens:
            total_tokens_value = safe_int_convert(
                StreamProcessor.get_field_value(chunk_data, field_mapping.total_tokens)
            )
            if total_tokens_value > 0:
                metrics.usage["total_tokens"] = total_tokens_value
                usage_extracted = True

        # Extract content
        if field_mapping.content:
            content_chunk = StreamProcessor.get_field_value(
                chunk_data, field_mapping.content
            )
            # Convert to string for content fields
            content_chunk = str(content_chunk) if content_chunk else ""
            if (
                content_chunk
                and isinstance(content_chunk, str)
                and content_chunk.strip()
            ):

                if not metrics.first_token_received:
                    metrics.first_token_received = True
                    metrics.first_output_token_time = time.time()
                    if start_time > 0 and metrics.first_output_token_time:
                        ttfot = (metrics.first_output_token_time - start_time) * 1000
                        EventManager.fire_metric_event(
                            "Time_to_first_output_token", ttfot, 0
                        )
                if not usage_extracted:
                    metrics.content += content_chunk

        # Extract reasoning content
        if field_mapping.reasoning_content:
            reasoning_chunk = StreamProcessor.get_field_value(
                chunk_data, field_mapping.reasoning_content
            )
            # Convert to string for reasoning content fields
            reasoning_chunk = str(reasoning_chunk) if reasoning_chunk else ""
            if (
                reasoning_chunk
                and isinstance(reasoning_chunk, str)
                and reasoning_chunk.strip()
            ):

                if not metrics.reasoning_is_active:
                    metrics.reasoning_is_active = True
                if not metrics.first_thinking_received:
                    metrics.first_thinking_received = True
                    metrics.first_thinking_token_time = time.time()
                    if start_time > 0 and metrics.first_thinking_token_time:
                        ttfrt = (metrics.first_thinking_token_time - start_time) * 1000
                        EventManager.fire_metric_event(
                            "Time_to_first_reasoning_token", ttfrt, 0
                        )
                if not usage_extracted:
                    metrics.reasoning_content += reasoning_chunk

            elif (
                metrics.reasoning_is_active
                and not reasoning_chunk
                and not metrics.reasoning_ended
                and field_mapping.content  # Only if we have content in this chunk
            ):
                content_chunk = StreamProcessor.get_field_value(
                    chunk_data, field_mapping.content
                )
                # Convert to string for content check
                content_chunk = str(content_chunk) if content_chunk else ""
                if (
                    content_chunk
                    and metrics.first_thinking_received
                    and metrics.first_thinking_token_time
                ):
                    metrics.reasoning_ended = True
                    current_time = time.time()
                    ttrc = (current_time - metrics.first_thinking_token_time) * 1000
                    EventManager.fire_metric_event(
                        "Time_to_reasoning_completion", ttrc, 0
                    )

        return metrics

    @staticmethod
    def process_stream_chunk(
        chunk: bytes,
        field_mapping: FieldMapping,
        start_time: float,
        metrics: StreamMetrics,
        task_logger,
    ) -> Tuple[bool, Optional[str], StreamMetrics]:
        """
        Process a single stream chunk according to the specified logic.

        Returns:
            (should_break, error_message, updated_metrics)
            - should_break: True if should exit the stream loop
            - error_message: Error message if there's an error, None otherwise
            - updated_metrics: Updated metrics object
        """
        if not chunk:
            return False, None, metrics

        try:
            chunk_str = chunk.decode("utf-8", errors="replace").strip()
        except UnicodeDecodeError as e:
            task_logger.warning(f"Failed to decode chunk: {e}")
            return False, None, metrics

        if not chunk_str:
            return False, None, metrics

        # Remove prefix if present
        processed_chunk = StreamProcessor.remove_chunk_prefix(chunk_str, field_mapping)

        if not processed_chunk:
            return False, None, metrics

        # Check if matches stop_flag directly
        if StreamProcessor.check_stop_flag(processed_chunk, field_mapping):
            return True, None, metrics  # Normal stream end

        if StreamProcessor.is_sse_event_line(chunk_str):
            return False, None, metrics
        # Check if data format is JSON
        if field_mapping.data_format == "json":
            try:
                chunk_data = orjson.loads(processed_chunk)
            except (orjson.JSONDecodeError, TypeError) as e:
                task_logger.error(
                    f"Failed to parse chunk as JSON: {e} | Chunk: {processed_chunk}"
                )
                return True, f"JSON parsing error: {e}", metrics

            # Check end_field stop condition
            if StreamProcessor.check_end_field_stop(chunk_data, field_mapping):
                return True, None, metrics  # Normal stream end

            # Check for JSON errors
            error_msg = ErrorResponse._handle_json_error(chunk_data)
            if error_msg:
                return True, error_msg, metrics  # Error occurred

            # Extract and update metrics
            metrics = StreamProcessor.extract_metrics_from_chunk(
                chunk_data, field_mapping, metrics, start_time, task_logger
            )
        else:
            # For non-JSON format, treat processed_chunk as content
            metrics.content += processed_chunk
            if not metrics.first_token_received:
                metrics.first_token_received = True
                metrics.first_output_token_time = time.time()
                if start_time > 0 and metrics.first_output_token_time:
                    ttfot = (metrics.first_output_token_time - start_time) * 1000
                    EventManager.fire_metric_event(
                        "Time_to_first_output_token", ttfot, 0
                    )
        return False, None, metrics


# === REQUEST HANDLERS ===
class PayloadBuilder:
    """Handles different types of API requests with dataset integration.

    Architecture:
    - Type-specific updaters: Each API type (openai-chat, claude-chat, embeddings)
      has a dedicated method that understands its specific payload format
    - Preservation of user config: All methods preserve original payload parameters
      (model, stream, max_tokens, etc.) and only update dataset-related fields
    - Separation of concerns: Each updater method handles one API type independently
    - Fallback support: Custom-chat uses field mapping for flexible API support

    Payload Update Strategy by API Type:
    1. openai-chat: Updates messages array, preserves system messages, adds/updates user message
    2. claude-chat: Updates messages array, preserves all params, adds/updates user message
    3. embeddings: Only updates input field, preserves model and other params
    4. custom-chat: Uses field_mapping for flexible field updates
    """

    def __init__(self, config: GlobalConfig, task_logger) -> None:
        """Initialize the PayloadBuilder with configuration and logger.

        Args:
            config: Global configuration object
            task_logger: Task-specific logger instance
        """
        self.config = config
        self.task_logger = task_logger

    def prepare_request_kwargs(
        self, prompt_data: Optional[Dict[str, Any]]
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Handle API requests with user-provided payload."""
        try:
            # Ensure request_payload is available - generate default if empty
            request_payload = self.config.request_payload
            if not request_payload or not request_payload.strip():
                # Generate default payload
                default_payload = {
                    "model": self.config.model_name or "your-model-name",
                    "stream": self.config.stream_mode,
                    "messages": [{"role": "user", "content": "Hi"}],
                }
                request_payload = orjson.dumps(default_payload).decode("utf-8")
                self.task_logger.info(
                    "Generated default request payload as none was provided"
                )

            try:
                payload = orjson.loads(str(request_payload))
            except orjson.JSONDecodeError as e:
                self.task_logger.error(f"Invalid JSON in request payload: {e}")
                return None, None

            user_prompt = ""

            # Check if we're in dataset mode
            is_dataset_mode = bool(
                self.config.test_data and self.config.test_data.strip()
            )

            if not is_dataset_mode:
                # No dataset mode - use payload directly
                user_prompt = self._extract_prompt_from_payload(payload)
            else:
                # Dataset mode - update payload with prompt data
                if prompt_data is None:
                    self.task_logger.error(
                        "Dataset mode enabled but no prompt data provided"
                    )
                    return None, None

                user_prompt = prompt_data.get("prompt", DEFAULT_PROMPT)
                # Unified payload handling for all APIs
                self._update_payload_with_prompt_data(payload, prompt_data)

            # Set request name based on API path
            request_name = self.config.api_path

            base_request_kwargs = {
                "json": payload,
                "headers": self.config.headers,
                "catch_response": True,
                "name": request_name,
                "verify": False,
            }

            if self.config.cookies:
                base_request_kwargs["cookies"] = self.config.cookies

            return base_request_kwargs, user_prompt

        except Exception as e:
            self.task_logger.error(
                f"Failed to prepare custom API request: {e}", exc_info=True
            )
            return None, None

    def _update_payload_with_prompt_data(
        self, payload: Dict[str, Any], prompt_data: Dict[str, Any]
    ) -> None:
        """Unified method to update payload with prompt data based on API type.

        Strategy (prioritized):
        1. For standard API types (openai-chat, claude-chat, embeddings): Use type-specific updaters
        2. For custom-chat: Use field mapping to update payload
        3. Fallback: Use original payload without dataset integration

        Args:
            payload: The request payload to update
            prompt_data: Dictionary containing prompt, image_url, and image_base64
        """
        try:
            # Extract prompt data
            user_prompt = prompt_data.get("prompt", DEFAULT_PROMPT)
            image_url = prompt_data.get("image_url", "")
            image_base64 = prompt_data.get("image_base64", "")

            # Get API type
            api_type = getattr(self.config, "api_type", "")

            # Route to appropriate updater based on API type
            if api_type == "openai-chat":
                self._update_openai_chat_payload(
                    payload, user_prompt, image_url, image_base64
                )
            elif api_type == "claude-chat":
                self._update_claude_chat_payload(
                    payload, user_prompt, image_url, image_base64
                )
            elif api_type == "embeddings":
                self._update_embeddings_payload(payload, user_prompt)
            elif api_type == "custom-chat":
                # For custom-chat, use field mapping
                field_mapping = ConfigManager.parse_field_mapping(
                    self.config.field_mapping or ""
                )
                if field_mapping.prompt or field_mapping.image:
                    self._update_payload_by_field_mapping(
                        payload, user_prompt, image_url, image_base64, field_mapping
                    )
                else:
                    self.task_logger.warning(
                        "custom-chat requires field_mapping configuration for dataset integration"
                    )
            else:
                # Fallback: No dataset integration for unknown types
                self.task_logger.debug(
                    f"Unknown api_type '{api_type}', using original request_payload without dataset integration"
                )

        except Exception as e:
            self.task_logger.error(f"Failed to update payload with prompt data: {e}")

    def _update_payload_by_field_mapping(
        self,
        payload: Dict[str, Any],
        user_prompt: str,
        image_url: str,
        image_base64: str,
        field_mapping: FieldMapping,
    ) -> None:
        """Update payload using field mapping configuration.

        Args:
            payload: The request payload to update
            user_prompt: The prompt text
            image_url: Image URL if available
            image_base64: Base64 encoded image if available
            field_mapping: Parsed field mapping configuration
        """
        # Update prompt field
        if field_mapping.prompt:
            try:
                self._set_field_value(payload, field_mapping.prompt, user_prompt)
            except Exception as e:
                self.task_logger.warning(f"Failed to update prompt in payload: {e}")
        else:
            self.task_logger.debug("No prompt field mapping configured")

        # Update image field
        if field_mapping.image:
            if image_url:
                # Use image URL
                try:
                    self._set_field_value(payload, field_mapping.image, image_url)
                except Exception as e:
                    self.task_logger.warning(
                        f"Failed to update image URL in payload: {e}"
                    )
            elif image_base64:
                # Use base64 encoded image
                try:
                    image_data_uri = f"data:image/jpeg;base64,{image_base64}"
                    self._set_field_value(payload, field_mapping.image, image_data_uri)
                except Exception as e:
                    self.task_logger.warning(
                        f"Failed to update image base64 in payload: {e}"
                    )

    def _update_openai_chat_payload(
        self,
        payload: Dict[str, Any],
        user_prompt: str,
        image_url: str,
        image_base64: str,
    ) -> None:
        """Update payload for OpenAI Chat API format.

        Preserves existing payload parameters (model, stream, etc.) and only updates
        the messages array to include user content from dataset.

        Args:
            payload: The request payload to update
            user_prompt: The prompt text from dataset
            image_url: Image URL from dataset if available
            image_base64: Base64 encoded image from dataset if available
        """
        # Get existing messages or create new list
        messages = payload.get("messages", [])
        if not isinstance(messages, list):
            messages = []

        # Build user message content based on whether images are present
        has_image = bool(image_base64 or image_url)

        if has_image:
            # Multimodal: use array format with text and image
            user_content: List[Dict[str, Any]] = [{"type": "text", "text": user_prompt}]

            # Add image (prioritize base64 over URL)
            if image_base64:
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                    }
                )
            elif image_url:
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url},
                    }
                )

            user_message = {"role": "user", "content": user_content}
        else:
            # Text-only: use simple string format
            user_message = {"role": "user", "content": user_prompt}

        # Find and update existing user message, or append new one
        user_message_found = False
        for i, msg in enumerate(messages):
            if isinstance(msg, dict) and msg.get("role") == "user":
                # Update existing user message
                messages[i] = user_message
                user_message_found = True
                break

        if not user_message_found:
            # Append new user message
            messages.append(user_message)

        # Update messages in payload (preserves all other parameters)
        payload["messages"] = messages

    def _update_claude_chat_payload(
        self,
        payload: Dict[str, Any],
        user_prompt: str,
        image_url: str,
        image_base64: str,
    ) -> None:
        """Update payload for Claude Chat API format.

        Preserves existing payload parameters (model, max_tokens, etc.) and only updates
        the messages array to include user content from dataset.

        Args:
            payload: The request payload to update
            user_prompt: The prompt text from dataset
            image_url: Image URL from dataset if available
            image_base64: Base64 encoded image from dataset if available
        """
        # Get existing messages or create new list
        messages = payload.get("messages", [])
        if not isinstance(messages, list):
            messages = []

        # Build user message content
        user_content: List[Dict[str, Any]] = [{"type": "text", "text": user_prompt}]

        # Add images if available
        if image_url:
            user_content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "url",
                        "url": image_url,
                    },
                }
            )

        if image_base64:
            user_content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_base64,
                    },
                }
            )

        # Find and update existing user message, or append new one
        user_message_found = False
        for i, msg in enumerate(messages):
            if isinstance(msg, dict) and msg.get("role") == "user":
                # Update existing user message
                messages[i]["content"] = user_content
                user_message_found = True
                break

        if not user_message_found:
            # Append new user message
            messages.append({"role": "user", "content": user_content})

        # Update messages in payload (preserves all other parameters)
        payload["messages"] = messages

    def _update_embeddings_payload(
        self, payload: Dict[str, Any], user_prompt: str
    ) -> None:
        """Update payload for Embeddings API format.

        Only updates the input/prompt field, preserves all other parameters.

        Args:
            payload: The request payload to update
            user_prompt: The prompt text from dataset
        """
        # Update input field (most embeddings APIs use "input")
        payload["input"] = user_prompt

    def _extract_prompt_from_payload(self, payload: Dict[str, Any]) -> str:
        """Extract prompt content from custom payload using field mapping."""
        try:
            field_mapping = ConfigManager.parse_field_mapping(
                self.config.field_mapping or ""
            )

            # Auto-generate field mapping for standard API types if not configured
            if not field_mapping.prompt and hasattr(self.config, "api_type"):
                api_type = getattr(self.config, "api_type", "")
                if api_type in ("openai-chat", "claude-chat", "embeddings"):
                    field_mapping = ConfigManager.generate_field_mapping_by_api_type(
                        api_type, self.config.stream_mode
                    )

            if field_mapping.prompt:
                prompt_value = StreamProcessor.get_field_value(
                    payload, field_mapping.prompt
                )
                return str(prompt_value) if prompt_value else ""
            return ""
        except Exception:
            return ""

    def _set_field_value(self, data: Dict[str, Any], path: str, value: str) -> None:
        """Set value in nested dictionary using dot-separated path."""
        if not path or not isinstance(data, dict):
            return

        try:
            keys = path.split(".")
            current = data
            # Navigate to the parent of the target field
            for key in keys[:-1]:
                current = self._navigate_to_key(current, key)
                if current is None:
                    return

            # Set the final field value
            self._set_final_value(current, keys[-1], value)

        except (KeyError, IndexError, TypeError, ValueError):
            # If we can't set the nested field, log a warning but don't fail
            pass

    def _navigate_to_key(self, current: Any, key: str) -> Any:
        """Navigate to a key in nested data structure."""
        # Check if key is a valid integer (including negative numbers)
        try:
            index = int(key)
            if isinstance(current, list):
                return current[index]
            else:
                return None
        except ValueError:
            # Key is not an integer, treat as dict key
            if isinstance(current, list) and current:
                if isinstance(current[0], dict):
                    return current[0].setdefault(key, {})
                else:
                    return None
            elif isinstance(current, dict):
                return current.setdefault(key, {})
            else:
                return None

    def _set_final_value(self, current: Any, final_key: str, value: str) -> None:
        """Set the final value in the data structure."""
        try:
            final_index = int(final_key)
            if isinstance(current, list):
                # For negative indices, ensure we're within bounds
                if -len(current) <= final_index < len(current):
                    current[final_index] = value
        except ValueError:
            # Final key is not an integer, treat as dict key
            if isinstance(current, dict):
                current[final_key] = value
            elif isinstance(current, list) and current and isinstance(current[0], dict):
                current[0][final_key] = value


# === STREAM HANDLERS ===
class APIClient:
    """Handles streaming and non-streaming request processing."""

    def __init__(self, config: GlobalConfig, task_logger) -> None:
        """Initialize the APIClient with configuration and logger.

        Args:
            config: Global configuration object
            task_logger: Task-specific logger instance
        """
        self.config = config
        self.task_logger = task_logger
        # Create ErrorResponse instance
        self.error_handler = ErrorResponse(config, task_logger)

    def _iter_stream_lines(self, response) -> Any:
        """Yield complete SSE lines using \n\n as delimiter. Robust version for HttpUser."""
        # For HttpUser, response is a requests.Response object
        if not hasattr(response, "iter_lines"):
            self.task_logger.error("Response object does not support streaming.")
            return

        try:
            for line in response.iter_lines(
                chunk_size=8192, decode_unicode=False, delimiter=b"\n"
            ):
                if not line:
                    continue
                # Ensure line is bytes
                if isinstance(line, str):
                    line = line.encode("utf-8", errors="ignore")
                yield line
        except Exception as e:
            self.task_logger.error(f"Error iterating over stream lines: {e}")
            # Propagate the exception so callers can record the failure properly.
            raise

    def handle_stream_request(
        self, client, base_request_kwargs: Dict[str, Any], start_time: float
    ) -> Tuple[str, str]:
        """Handle streaming API request with comprehensive metrics collection."""
        metrics = StreamMetrics()
        request_kwargs = {**base_request_kwargs, "stream": True}
        field_mapping = ConfigManager.parse_field_mapping(
            self.config.field_mapping or ""
        )

        # Auto-generate field mapping for standard API types if not configured
        if not field_mapping.prompt and hasattr(self.config, "api_type"):
            api_type = getattr(self.config, "api_type", "")
            self.task_logger.debug(f"handle_stream_request-api_type: {api_type}")
            if api_type in ("openai-chat", "claude-chat", "embeddings"):
                field_mapping = ConfigManager.generate_field_mapping_by_api_type(
                    api_type, self.config.stream_mode
                )
        response = None
        actual_start_time = 0.0
        request_name = base_request_kwargs.get("name", "failure")
        usage: Dict[str, Optional[int]] = {
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        try:
            actual_start_time = time.time()
            with client.post(self.config.api_path, **request_kwargs) as response:
                if self.error_handler._handle_status_code_error(
                    response, start_time, request_name
                ):
                    return "", "", usage

                try:
                    # Process as streaming response
                    for chunk in self._iter_stream_lines(response):
                        should_break, error_message, metrics = (
                            StreamProcessor.process_stream_chunk(
                                chunk,
                                field_mapping,
                                actual_start_time,
                                metrics,
                                self.task_logger,
                            )
                        )

                        if should_break:
                            if error_message:
                                # Error occurred, mark failure and exit
                                self.error_handler._handle_general_exception_event(
                                    error_msg=error_message,
                                    response=response,
                                    response_time=(time.time() - start_time) * 1000,
                                    additional_context={
                                        "chunk_preview": (
                                            chunk if chunk else "No chunk data"
                                        ),
                                        "api_path": self.config.api_path,
                                        "request_name": request_name,
                                    },
                                )
                                return "", "", usage
                            # Normal end of stream, break the loop
                            break

                    # Fire completion events for streaming
                    try:
                        current_time = time.time()
                        total_time = (
                            (current_time - actual_start_time) * 1000
                            if actual_start_time is not None and actual_start_time > 0
                            else 0
                        )

                        completion_time = 0
                        if (
                            metrics.first_token_received
                            and metrics.first_output_token_time is not None
                            and metrics.first_output_token_time > 0
                        ):
                            completion_time = (
                                current_time - metrics.first_output_token_time
                            ) * 1000
                            EventManager.fire_metric_event(
                                METRIC_TTOC, completion_time, 0
                            )
                        EventManager.fire_metric_event(METRIC_TTT, total_time, 0)
                        response.success()

                    except Exception as e:
                        self.task_logger.error(
                            f"Error calculating streaming metrics: {e}"
                        )
                        response.success()  # Still mark as success since we got response

                except OSError as e:
                    self.error_handler._handle_stream_error(
                        e, response, start_time, request_name
                    )
                    return "", "", usage
                except (orjson.JSONDecodeError, ValueError) as e:
                    response_time = (time.time() - start_time) * 1000
                    self.error_handler._handle_general_exception_event(
                        error_msg=f"Stream data parsing error: {e}",
                        response=response,
                        response_time=response_time,
                        additional_context={
                            "api_path": self.config.api_path,
                            "request_name": request_name,
                        },
                    )
                    return "", "", usage
        except (ConnectionError, TimeoutError) as e:
            response_time = (time.time() - start_time) * 1000
            self.error_handler._handle_general_exception_event(
                error_msg=f"Connection error: {e}",
                response=response,
                response_time=response_time,
                additional_context={
                    "api_path": self.config.api_path,
                    "request_name": request_name,
                },
            )
            return "", "", usage
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.task_logger.error(f"Stream processing error: {e}")
            self.error_handler._handle_general_exception_event(
                error_msg=f"Unexpected error: {e}",
                response=response,
                response_time=response_time,
                additional_context={
                    "api_path": self.config.api_path,
                    "request_name": request_name,
                },
            )
            return "", "", usage
        return metrics.reasoning_content, metrics.content, metrics.usage

    @staticmethod
    def _extract_usage_from_response(
        resp_json: Dict[str, Any], field_mapping: FieldMapping
    ) -> Dict[str, Optional[int]]:
        """
        Extract usage from response JSON using FieldMapping.
        Similar to extract_metrics_from_chunk but for non-streaming responses.
        """
        usage: Dict[str, Optional[int]] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        # Update prompt tokens if field mapping exists
        if field_mapping.prompt_tokens:
            prompt_tokens_value = safe_int_convert(
                StreamProcessor.get_field_value(resp_json, field_mapping.prompt_tokens)
            )
            if prompt_tokens_value > 0:
                usage["prompt_tokens"] = prompt_tokens_value

        # Update completion tokens if field mapping exists
        if field_mapping.completion_tokens:
            completion_tokens_value = safe_int_convert(
                StreamProcessor.get_field_value(
                    resp_json, field_mapping.completion_tokens
                )
            )
            if completion_tokens_value > 0:
                usage["completion_tokens"] = completion_tokens_value

        # Update total tokens if field mapping exists
        if field_mapping.total_tokens:
            total_tokens_value = safe_int_convert(
                StreamProcessor.get_field_value(resp_json, field_mapping.total_tokens)
            )
            if total_tokens_value > 0:
                usage["total_tokens"] = total_tokens_value

        # Fallback: try to extract from usage field if mappings are not provided
        if (
            usage["prompt_tokens"] == 0
            and usage["completion_tokens"] == 0
            and usage["total_tokens"] == 0
        ):
            if "usage" in resp_json and isinstance(resp_json["usage"], dict):
                response_usage = resp_json["usage"]
                if "prompt_tokens" in response_usage:
                    usage["prompt_tokens"] = safe_int_convert(
                        response_usage["prompt_tokens"]
                    )
                if "input_tokens" in response_usage:
                    usage["prompt_tokens"] = safe_int_convert(
                        response_usage["input_tokens"]
                    )
                if "completion_tokens" in response_usage:
                    usage["completion_tokens"] = safe_int_convert(
                        response_usage["completion_tokens"]
                    )
                if "output_tokens" in response_usage:
                    usage["completion_tokens"] = safe_int_convert(
                        response_usage["output_tokens"]
                    )
                if "total_tokens" in response_usage:
                    usage["total_tokens"] = safe_int_convert(
                        response_usage["total_tokens"]
                    )
                if "all_tokens" in response_usage:
                    usage["total_tokens"] = safe_int_convert(
                        response_usage["all_tokens"]
                    )

        return usage

    def handle_non_stream_request(
        self, client, base_request_kwargs: Dict[str, Any], start_time: float
    ) -> Tuple[str, str, Dict[str, Optional[int]]]:
        """Handle non-streaming API request."""

        json_payload = base_request_kwargs.get("json", {})
        if isinstance(json_payload, dict) and json_payload.get("stream") is True:
            error_msg = (
                "Payload contains 'stream': true, but task is configured for non-streaming mode (stream_mode=False). "
                "Please either set stream_mode=True in task config, or remove 'stream' field from payload."
            )
            self.task_logger.error(error_msg)
            response_time = (time.time() - start_time) * 1000
            self.error_handler._handle_general_exception_event(
                error_msg=error_msg,
                response=None,
                response_time=response_time,
                additional_context={
                    "api_path": self.config.api_path,
                    "request_name": base_request_kwargs.get(
                        "name", "non_stream_mismatch"
                    ),
                },
            )
            return (
                "",
                "",
                {
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            )

        request_kwargs = {**base_request_kwargs, "stream": False}
        content, reasoning_content = "", ""
        field_mapping = ConfigManager.parse_field_mapping(
            self.config.field_mapping or ""
        )

        # Auto-generate field mapping for standard API types if not configured
        if not field_mapping.prompt and hasattr(self.config, "api_type"):
            api_type = getattr(self.config, "api_type", "")
            if api_type in ("openai-chat", "claude-chat", "embeddings"):
                field_mapping = ConfigManager.generate_field_mapping_by_api_type(
                    api_type, self.config.stream_mode
                )
        request_name = base_request_kwargs.get("name", "failure")
        usage: Dict[str, Optional[int]] = {
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        try:
            with client.post(self.config.api_path, **request_kwargs) as response:
                total_time = (time.time() - start_time) * 1000

                if self.error_handler._handle_status_code_error(
                    response, start_time, request_name
                ):
                    return "", "", usage

                try:
                    resp_json = response.json()
                    # self.task_logger.info(f"resp_json: {resp_json}")
                except (orjson.JSONDecodeError, KeyError) as e:
                    self.task_logger.error(f"Failed to parse response JSON: {e}")
                    self.error_handler._handle_general_exception_event(
                        error_msg=str(e),
                        response=response,
                        response_time=total_time,
                        additional_context={
                            "api_path": self.config.api_path,
                            "request_name": request_name,
                        },
                    )
                    return "", "", usage

                error_msg = ErrorResponse._handle_json_error(resp_json)
                if error_msg:
                    self.error_handler._handle_general_exception_event(
                        error_msg=error_msg,
                        response=response,
                        response_time=total_time,
                        additional_context={
                            "response_preview": (
                                str(resp_json) if resp_json else "No response data"
                            ),
                            "api_path": self.config.api_path,
                            "request_name": request_name,
                        },
                    )
                    return "", "", usage

                EventManager.fire_metric_event(
                    METRIC_TTT,
                    total_time,
                    0,
                )

                # Extract usage and content using FieldMapping
                usage = self._extract_usage_from_response(resp_json, field_mapping)

                if field_mapping.content:
                    content = StreamProcessor.get_field_value(
                        resp_json, field_mapping.content
                    )
                if field_mapping.reasoning_content:
                    reasoning_content = StreamProcessor.get_field_value(
                        resp_json, field_mapping.reasoning_content
                    )
                response.success()
                return reasoning_content, content, usage

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.error_handler._handle_general_exception_event(
                error_msg=f"Unexpected error: {e}",
                response=response,
                response_time=response_time,
                additional_context={
                    "api_path": self.config.api_path,
                    "request_name": request_name,
                },
            )
            return "", "", usage
