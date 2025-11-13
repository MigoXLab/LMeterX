"""
Dataset loading and parsing utilities.

Handles loading and parsing of different dataset formats (JSONL, JSON/ShareGPT).

Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import json
import os
import queue
from typing import Any, Dict, List, Optional

from config.base import IMAGES_DIR, MAX_QUEUE_SIZE, PROMPTS_DIR
from utils.common import encode_image, is_url
from utils.logger import logger

# === BUILT-IN DATASET CONFIGURATION ===
# Mapping between chat_type (dataset selector) and concrete dataset filenames.
# 0 -> Pure text dataset (self-built), JSONL format
# 1 -> Pure text ShareGPT dataset, JSON array format
# 2 -> Multimodal (vision) dataset (self-built), JSONL format
BUILTIN_DATASET_FILES: Dict[int, str] = {
    0: "text_self-built.jsonl",
    1: "ShareGPT_V3_partial.json",
    2: "vision_self-built.jsonl",
}

DEFAULT_CHAT_TYPE = 0


# === DATA CLASSES ===
class PromptData:
    """Structured prompt data representation."""

    def __init__(
        self,
        prompt_id: str | int,
        prompt: str,
        image_base64: str = "",
        image_url: str = "",
    ):
        """Initialize PromptData with prompt information and optional image data.

        Args:
            prompt_id: Unique identifier for the prompt
            prompt: The text prompt content
            image_base64: Base64 encoded image data (optional)
            image_url: URL to image (optional)
        """
        self.id = prompt_id
        self.prompt = prompt
        self.image_base64 = image_base64
        self.image_url = image_url

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        result = {"id": self.id, "prompt": self.prompt}
        if self.image_base64:
            result["image_base64"] = self.image_base64
        if self.image_url:
            result["image_url"] = self.image_url
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptData":
        """Create from dictionary."""
        return cls(
            prompt_id=data.get("id", "unknown"),
            prompt=data.get("prompt", ""),
            image_base64=data.get("image_base64", ""),
            image_url=data.get("image_url", ""),
        )


# === FIELD NORMALIZATION ===
def normalize_prompt_field(prompt: Any) -> str:
    """Normalize prompt field to string.

    Supports multiple input formats:
    - String: returned as-is
    - Simple list: first element converted to string
    - Object with 'messages' key: JSON serialized (for chat-like formats)
    - Other objects: JSON serialized
    """
    if isinstance(prompt, str):
        return prompt
    elif isinstance(prompt, list) and prompt:
        # Handle simple list format like ["prompt text"]
        return str(prompt[0])
    elif isinstance(prompt, dict):
        # Handle complex object formats
        try:
            # Special handling for chat-like formats with messages
            if "messages" in prompt:
                # This handles formats like {"messages": [{"role": "user", "content": "..."}]}
                return json.dumps(prompt, ensure_ascii=False, separators=(",", ":"))
            else:
                # Handle other dictionary formats
                return json.dumps(prompt, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as e:
            # Fallback to string representation if JSON serialization fails
            logger.warning(
                f"Failed to serialize prompt object to JSON: {e}, using string representation"
            )
            return str(prompt)
    else:
        return ""


def normalize_image_path(image_path: Any) -> Optional[str]:
    """Normalize image path field."""
    if isinstance(image_path, str):
        return image_path
    elif isinstance(image_path, list) and image_path:
        return str(image_path[0])
    else:
        return None


def extract_prompt_from_conversations(conversations: List[Dict[str, str]]) -> str:
    """Extract the first human message from conversations list (ShareGPT format).

    Args:
        conversations: List of conversation turns with 'from' and 'value' keys

    Returns:
        str: The first human message content, or empty string if not found
    """
    if not isinstance(conversations, list):
        return ""

    for turn in conversations:
        if isinstance(turn, dict):
            from_field = turn.get("from", "")
            if from_field in ("human", "user"):
                value = turn.get("value", "")
                if isinstance(value, str):
                    return value

    return ""


def extract_prompt_from_messages(messages: List[Dict[str, str]]) -> str:
    """Extract the first user message from messages list (OpenAI format).

    Args:
        messages: List of message objects with 'role' and 'content' keys

    Returns:
        str: The first user message content, or empty string if not found
    """
    if not isinstance(messages, list):
        return ""

    for message in messages:
        if isinstance(message, dict):
            role = message.get("role", "")
            if role in ("user", "human"):
                content = message.get("content", "")
                if isinstance(content, str):
                    return content

    return ""


# === LINE PARSING ===
def parse_data_line(line: str, line_num: int, task_logger=None) -> Optional[PromptData]:
    """Parse a single data line (JSONL or JSON object) into PromptData.

    Supports both standard JSONL format and ShareGPT format.

    Args:
        line: The JSON line to parse
        line_num: Line number for error reporting
        task_logger: Optional logger for this task

    Returns:
        PromptData object or None if parsing fails
    """
    effective_logger = task_logger if task_logger else logger

    try:
        json_obj = json.loads(line.strip())

        # Extract ID - use line_num if id field is missing (no error)
        prompt_id = json_obj.get("id", line_num)

        # Extract and normalize prompt
        # Priority: prompt field > conversations field > messages field
        prompt = ""
        raw_prompt = json_obj.get("prompt")

        if raw_prompt:
            # Priority 1: prompt field (string or list)
            prompt = normalize_prompt_field(raw_prompt)
        elif "conversations" in json_obj:
            # Priority 2: conversations field (ShareGPT format)
            conversations = json_obj.get("conversations")
            if isinstance(conversations, list):
                prompt = extract_prompt_from_conversations(conversations)
        elif "messages" in json_obj:
            # Priority 3: messages field (OpenAI format)
            messages = json_obj.get("messages")
            if isinstance(messages, list):
                prompt = extract_prompt_from_messages(messages)

        if not prompt:
            # Skip silently without error for missing prompt
            return None

        # Handle images - unified image field processing
        # Support both "image" and "image_path" fields
        image_base64 = ""
        image_url = ""

        # Try "image" field first, then "image_path" as fallback
        image_field_value = json_obj.get("image") or json_obj.get("image_path")

        if image_field_value:
            # Extract image value (string or list)
            image_value = normalize_image_path(image_field_value)

            if image_value:
                # Check if it's a URL
                if is_url(image_value):
                    image_url = image_value
                else:
                    # Treat as file path - encode_image will handle path resolution
                    try:
                        image_base64 = encode_image(image_value)
                    except FileNotFoundError as e:
                        effective_logger.warning(
                            f"Image file not found in dataset: {image_value} - {e}"
                        )
                    except IOError as e:
                        effective_logger.warning(
                            f"Failed to encode image from dataset: {image_value} - {e}"
                        )

        return PromptData(prompt_id, prompt, image_base64, image_url)

    except json.JSONDecodeError as e:
        effective_logger.error(
            f"JSON decode error in line {line_num}: {line}. Error: {e}"
        )
        return None
    except Exception as e:
        effective_logger.error(f"Unexpected error parsing line {line_num}: {e}")
        return None


# === FILE LOADING ===
def load_dataset_file(data_file: str, task_logger=None) -> List[Dict[str, Any]]:
    """Load all stress test data from file.

    Supports both JSONL format (one JSON object per line) and JSON array format (ShareGPT).

    Args:
        data_file (str): Path to the JSONL or JSON file containing ids and prompts.
        task_logger: Optional task-specific logger instance.

    Returns:
        List[Dict[str, Any]]: A list of prompt data dictionaries.
    """
    effective_logger = task_logger if task_logger else logger
    prompts: List[Dict[str, Any]] = []

    if not os.path.exists(data_file):
        effective_logger.error(f"Data file not found: {data_file}")
        return prompts

    try:
        with open(data_file, "r", encoding="utf-8") as f:
            content = f.read().strip()

        if not content:
            effective_logger.warning(f"Empty data file: {data_file}")
            return prompts

        # Try to detect if it's a JSON array format (ShareGPT) or JSONL format
        if content.startswith("["):
            # JSON array format (ShareGPT)
            try:
                json_array = json.loads(content)
                if not isinstance(json_array, list):
                    effective_logger.error(
                        f"Expected JSON array in {data_file}, got {type(json_array).__name__}"
                    )
                    return prompts

                for idx, json_obj in enumerate(json_array, 1):
                    if not isinstance(json_obj, dict):
                        effective_logger.warning(
                            f"Skipping non-dict item at index {idx} in {data_file}"
                        )
                        continue

                    # Convert dict to JSON string for parse_data_line
                    line = json.dumps(json_obj, ensure_ascii=False)
                    prompt_data = parse_data_line(line, idx, task_logger)
                    if prompt_data:
                        prompts.append(prompt_data.to_dict())

            except json.JSONDecodeError as e:
                effective_logger.error(
                    f"Failed to parse JSON array in {data_file}: {e}"
                )
                return prompts
        else:
            # JSONL format (one JSON object per line)
            lines = content.split("\n")
            for line_num, line in enumerate(lines, 1):
                if not line.strip():
                    continue

                prompt_data = parse_data_line(line, line_num, task_logger)
                if prompt_data:
                    prompts.append(prompt_data.to_dict())

    except IOError as e:
        effective_logger.error(f"Error reading file {data_file}: {e}")
    except Exception as e:
        effective_logger.error(f"Error loading prompts from {data_file}: {e}")

    return prompts


def load_dataset_string(content: str, task_logger=None) -> List[Dict[str, Any]]:
    """Load dataset from string content.

    Supports both JSONL format and JSON array format (ShareGPT).

    Args:
        content: JSONL or JSON array format string content
        task_logger: Optional task-specific logger instance

    Returns:
        List[Dict[str, Any]]: A list of prompt data dictionaries
    """
    effective_logger = task_logger if task_logger else logger
    prompts: List[Dict[str, Any]] = []

    if not content.strip():
        return prompts

    try:
        content = content.strip()

        # Detect format: JSON array or JSONL
        if content.startswith("["):
            # JSON array format (ShareGPT)
            try:
                json_array = json.loads(content)
                if not isinstance(json_array, list):
                    effective_logger.error(
                        f"Expected JSON array, got {type(json_array).__name__}"
                    )
                    return prompts

                for idx, json_obj in enumerate(json_array, 1):
                    if not isinstance(json_obj, dict):
                        effective_logger.warning(
                            f"Skipping non-dict item at index {idx}"
                        )
                        continue

                    # Convert dict to JSON string for parse_data_line
                    line = json.dumps(json_obj, ensure_ascii=False)
                    prompt_data = parse_data_line(line, idx, task_logger)
                    if prompt_data:
                        prompts.append(prompt_data.to_dict())

            except json.JSONDecodeError as e:
                effective_logger.error(f"Failed to parse JSON array: {e}")
                return prompts
        else:
            # JSONL format (one JSON object per line)
            lines = content.split("\n")
            for line_num, line in enumerate(lines, 1):
                if not line.strip():
                    continue

                prompt_data = parse_data_line(line, line_num, task_logger)
                if prompt_data:
                    prompts.append(prompt_data.to_dict())

    except Exception as e:
        effective_logger.error(f"Error loading prompts from string content: {e}")

    return prompts


# === QUEUE INITIALIZATION ===
def init_prompt_queue_from_string(content: str, task_logger=None) -> queue.Queue:
    """Initializes the test data queue from JSONL or JSON array string content.

    Supports both JSONL format (one JSON object per line) and JSON array format (ShareGPT).

    Args:
        content (str): JSONL or JSON array format string content.
        task_logger: An optional task-specific logger instance.

    Returns:
        queue.Queue: A queue containing the data.

    Raises:
        ValueError: If no valid prompts are found.
        RuntimeError: If queue initialization fails.
    """
    effective_logger = task_logger if task_logger else logger

    if not content.strip():
        raise ValueError("Empty content provided")

    try:
        prompts = load_dataset_string(content, task_logger)

        if not prompts:
            raise ValueError("No valid prompts were parsed from the content")

        # Add to queue with size validation
        if len(prompts) > MAX_QUEUE_SIZE:
            effective_logger.warning(
                f"Large dataset ({len(prompts)} items), consider splitting"
            )

        q: queue.Queue = queue.Queue()
        for prompt_dict in prompts:
            q.put_nowait(prompt_dict)

        return q

    except Exception as e:
        effective_logger.error(f"Failed to initialize prompt queue from content: {e}")
        raise RuntimeError(f"Failed to initialize prompt queue from content: {e}")


def init_prompt_queue_from_file(file_path: str, task_logger=None) -> queue.Queue:
    """Initializes the test data queue from a custom file.

    Supports both JSONL format and JSON array format (ShareGPT).

    Args:
        file_path (str): Path to the JSONL or JSON file.
        task_logger: An optional task-specific logger instance.

    Returns:
        queue.Queue: A queue containing the data.

    Raises:
        ValueError: If file not found or no prompts loaded.
        RuntimeError: If queue initialization fails.
    """
    effective_logger = task_logger if task_logger else logger

    if not os.path.exists(file_path):
        raise ValueError(f"Custom data file not found: {file_path}")

    try:
        prompts = load_dataset_file(file_path, task_logger)
        if not prompts:
            raise ValueError("No prompts were loaded from the custom data file")

        q: queue.Queue = queue.Queue()
        for prompt_data in prompts:
            q.put_nowait(prompt_data)

        return q

    except Exception as e:
        effective_logger.error(
            f"Failed to initialize prompt queue from file {file_path}: {e}"
        )
        raise RuntimeError(
            f"Failed to initialize prompt queue from file {file_path}: {e}"
        )


def init_prompt_queue(
    chat_type: int = 0,
    test_data: str = "",
    task_logger=None,
) -> queue.Queue:
    """Initializes the test data queue based on the chat type and custom test data.

    Supports both JSONL format and JSON array format (ShareGPT).

    Args:
        chat_type (int): The chat type, 0 for text-only, 1 for multimodal.
        test_data (str, optional): Custom test data - can be JSONL/JSON string content, file path, "default", or empty.
        task_logger: An optional task-specific logger instance.

    Returns:
        queue.Queue: A queue containing the data.
    """
    effective_logger = task_logger if task_logger else logger

    # Case 1: Empty test_data - no dataset mode, use request_payload directly
    if not test_data or test_data.strip() == "":
        # Return empty queue for no-dataset mode
        return queue.Queue()

    # Case 2: test_data is "default" - use built-in dataset based on chat_type
    if test_data.strip().lower() == "default":
        dataset_index = DEFAULT_CHAT_TYPE
        try:
            dataset_index = int(chat_type)
        except (TypeError, ValueError):
            effective_logger.warning(
                "Invalid chat_type '%s' detected, fallback to default dataset index %s",
                chat_type,
                DEFAULT_CHAT_TYPE,
            )

        dataset_filename = BUILTIN_DATASET_FILES.get(dataset_index)
        if not dataset_filename:
            effective_logger.warning(
                "Unsupported built-in dataset index '%s', fallback to default dataset '%s'",
                chat_type,
                BUILTIN_DATASET_FILES[DEFAULT_CHAT_TYPE],
            )
            dataset_filename = BUILTIN_DATASET_FILES[DEFAULT_CHAT_TYPE]

        data_file = os.path.join(PROMPTS_DIR, dataset_filename)

        if not os.path.exists(data_file):
            raise ValueError(f"Default data file not found: {data_file}")

        return init_prompt_queue_from_file(data_file, task_logger)

    # Case 3: test_data is JSONL content string (starts with "{") or JSON array (starts with "[")
    if test_data.strip().startswith("{") or test_data.strip().startswith("["):
        return init_prompt_queue_from_string(test_data, task_logger)

    # Case 4: test_data is a file path - handle both absolute and relative paths
    # Try to resolve the path using FilePathUtils for upload files
    try:
        return init_prompt_queue_from_file(test_data, task_logger)
    except (ValueError, FileNotFoundError) as e:
        effective_logger.warning(f"Failed to resolve as upload file path: {e}")

        # Fallback: try as direct file path for backward compatibility
        if os.path.exists(test_data):
            return init_prompt_queue_from_file(test_data, task_logger)

    # Invalid test_data provided
    raise ValueError(
        f"Invalid test_data provided: '{test_data}'. "
        f"Expected empty string, 'default', JSONL/JSON content string, or valid file path."
    )
