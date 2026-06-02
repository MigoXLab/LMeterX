"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import json
import os
import queue
from typing import Any, Dict, List, Optional, Set

from config.base import DATA_DIR, MAX_QUEUE_SIZE
from utils.common import is_url
from utils.logger import logger

# === BUILT-IN DATASET CONFIGURATION ===
# Mapping between chat_type (dataset selector) and concrete dataset filenames.
# 0 -> Pure text dataset (self-built), JSONL format
# 1 -> Pure text ShareGPT dataset, JSON array format
# 2 -> Comprehensive dataset (self-built), JSONL format
BUILTIN_DATASET_FILES: Dict[int, str] = {
    0: "text_self-built.jsonl",
    1: "ShareGPT_V3_partial.json",
    2: "comprehensive_self-build.jsonl",
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
        image_path: str = "",
        messages: Optional[List[Dict[str, Any]]] = None,
        raw_data: Optional[Dict[str, Any]] = None,
    ):
        """Initialize the PromptData object."""
        self.id = prompt_id
        self.prompt = prompt
        self.image_base64 = image_base64
        self.image_url = image_url
        self.image_path = image_path
        self.messages = messages or []
        self.raw_data = raw_data or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        result = {"id": self.id, "prompt": self.prompt}
        if self.image_base64:
            result["image_base64"] = self.image_base64
        if self.image_url:
            result["image_url"] = self.image_url
        if self.image_path:
            result["image_path"] = self.image_path
        if self.messages:
            result["messages"] = self.messages
        if self.raw_data:
            result["raw_data"] = self.raw_data
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptData":
        """Create from dictionary."""
        return cls(
            prompt_id=data.get("id", "unknown"),
            prompt=data.get("prompt", ""),
            image_base64=data.get("image_base64", ""),
            image_url=data.get("image_url", ""),
            image_path=data.get("image_path", ""),
            messages=data.get("messages", []),
            raw_data=data.get("raw_data", {}),
        )


# === FIELD NORMALIZATION ===
def normalize_prompt_field(prompt: Any) -> str:
    """Normalize prompt field to string.

    Supports multiple input formats:
    - String: returned as-is
    - Simple list: first element converted to string
    - Object/dict: JSON serialized
    """
    if isinstance(prompt, str):
        return prompt
    elif isinstance(prompt, list) and prompt:
        return str(prompt[0])
    elif isinstance(prompt, dict):
        try:
            return json.dumps(prompt, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as e:
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


# === PROMPT EXTRACTION ===
def _extract_first_user_message(
    items: Any,
    role_key: str,
    content_key: str,
    valid_roles: Set[str],
) -> str:
    """Extract the first user/human message from a message list.

    Args:
        items: List of message dicts
        role_key: Key name for the role field (e.g. "from" or "role")
        content_key: Key name for the content field (e.g. "value" or "content")
        valid_roles: Set of role values that identify user messages

    Returns:
        str: The first matching message content, or empty string
    """
    if not isinstance(items, list):
        return ""

    for item in items:
        if isinstance(item, dict):
            role = item.get(role_key, "")
            if role in valid_roles:
                content = item.get(content_key, "")
                if isinstance(content, str):
                    return content

    return ""


def extract_prompt_from_conversations(conversations: List[Dict[str, str]]) -> str:
    """Extract the first human message from conversations list (ShareGPT format)."""
    return _extract_first_user_message(
        conversations, "from", "value", {"human", "user"}
    )


def extract_prompt_from_messages(messages: List[Dict[str, str]]) -> str:
    """Extract the first user message from messages list (OpenAI format)."""
    return _extract_first_user_message(messages, "role", "content", {"user", "human"})


# === LINE PARSING ===
def _parse_json_obj(
    json_obj: Dict[str, Any], line_num: int, api_type: str = "", task_logger=None
) -> Optional[PromptData]:
    """Parse a JSON object into PromptData.

    This is the core parsing logic used by both parse_data_line (for JSONL)
    and directly for pre-parsed JSON array items.

    Args:
        json_obj: The parsed JSON object
        line_num: Line/index number for ID fallback
        api_type: API type for format-specific handling
        task_logger: Optional logger for this task

    Returns:
        PromptData object or None if parsing fails
    """
    effective_logger = task_logger if task_logger else logger

    prompt_id = json_obj.get("id", line_num)

    prompt = ""
    raw_prompt = json_obj.get("prompt")
    messages_list = None

    if "messages" in json_obj:
        messages = json_obj.get("messages")
        if isinstance(messages, list):
            messages_list = messages

    # Priority: prompt field > conversations field > messages field
    if raw_prompt:
        prompt = normalize_prompt_field(raw_prompt)
    elif "conversations" in json_obj:
        conversations = json_obj.get("conversations")
        if isinstance(conversations, list):
            prompt = extract_prompt_from_conversations(conversations)
    elif messages_list:
        prompt = extract_prompt_from_messages(messages_list)

    if not prompt and not messages_list:
        # For embeddings and custom-chat, allow items with no prompt/messages
        # as long as json_obj has actual data (passed via raw_data).
        if api_type in ("embeddings", "custom-chat"):
            if len(json_obj) == 0:
                return None
        else:
            return None

    # Handle images
    image_url = ""
    image_path = ""

    if api_type not in ("embeddings", "custom-chat"):
        image_field_value = json_obj.get("image") or json_obj.get("image_path")

        if image_field_value:
            image_value = normalize_image_path(image_field_value)

            if image_value:
                if is_url(image_value):
                    image_url = image_value
                else:
                    if os.path.exists(image_value):
                        image_path = image_value
                    else:
                        effective_logger.warning(
                            f"Image file not found in dataset: {image_value}"
                        )

    return PromptData(
        prompt_id,
        prompt,
        "",  # image_base64: always empty at parse time (lazy encoding at request time)
        image_url,
        image_path,
        messages_list,
        json_obj,
    )


def parse_data_line(
    line: str, line_num: int, api_type: str = "", task_logger=None
) -> Optional[PromptData]:
    """Parse a single JSONL line into PromptData.

    Args:
        line: The JSON line to parse
        line_num: Line number for error reporting
        api_type: API type for format-specific handling
        task_logger: Optional logger for this task

    Returns:
        PromptData object or None if parsing fails
    """
    effective_logger = task_logger if task_logger else logger

    try:
        json_obj = json.loads(line.strip())
        return _parse_json_obj(json_obj, line_num, api_type, task_logger)
    except json.JSONDecodeError as e:
        effective_logger.error(
            f"JSON decode error in line {line_num}: {line}. Error: {e}"
        )
        return None
    except Exception as e:
        effective_logger.error(f"Unexpected error parsing line {line_num}: {e}")
        return None


# === FILE/STRING LOADING ===
def load_dataset_string(
    content: str, api_type: str = "", task_logger=None
) -> List[Dict[str, Any]]:
    """Load dataset from string content.

    Supports both JSONL format and JSON array format (ShareGPT).

    Args:
        content: JSONL or JSON array format string content
        api_type: API type for format-specific handling
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

                    prompt_data = _parse_json_obj(json_obj, idx, api_type, task_logger)
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

                prompt_data = parse_data_line(line, line_num, api_type, task_logger)
                if prompt_data:
                    prompts.append(prompt_data.to_dict())

    except Exception as e:
        effective_logger.error(f"Error loading prompts from string content: {e}")

    return prompts


def load_dataset_file(
    data_file: str, api_type: str = "", task_logger=None
) -> List[Dict[str, Any]]:
    """Load all stress test data from file.

    Supports both JSONL format (one JSON object per line) and JSON array format (ShareGPT).

    Args:
        data_file (str): Path to the JSONL or JSON file containing ids and prompts.
        api_type: API type for format-specific handling.
        task_logger: Optional task-specific logger instance.

    Returns:
        List[Dict[str, Any]]: A list of prompt data dictionaries.
    """
    effective_logger = task_logger if task_logger else logger

    if not os.path.exists(data_file):
        effective_logger.error(f"Data file not found: {data_file}")
        return []

    try:
        with open(data_file, "r", encoding="utf-8") as f:
            content = f.read()
    except IOError as e:
        effective_logger.error(f"Error reading file {data_file}: {e}")
        return []

    if not content.strip():
        effective_logger.warning(f"Empty data file: {data_file}")
        return []

    return load_dataset_string(content, api_type, task_logger)


# === DATASET ROUTING ===
def _resolve_dataset_items(
    chat_type: int = 0,
    test_data: str = "",
    api_type: str = "",
    task_logger=None,
) -> Optional[List[Dict[str, Any]]]:
    """Resolve test_data into a list of prompt dicts.

    Returns:
        None — no-dataset mode (empty test_data)
        List[Dict] — parsed items (may be empty if parsing failed)

    Raises:
        ValueError: If test_data is invalid or file not found.
    """
    effective_logger = task_logger if task_logger else logger

    # Case 1: Empty test_data — no dataset mode
    if not test_data or test_data.strip() == "":
        return None

    # Case 2: "default" — use built-in dataset based on chat_type
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

        data_file = os.path.join(DATA_DIR, dataset_filename)

        if not os.path.exists(data_file):
            raise ValueError(f"Default data file not found: {data_file}")

        return load_dataset_file(data_file, api_type, task_logger)

    # Case 3: JSONL content string (starts with "{") or JSON array (starts with "[")
    if test_data.strip().startswith("{") or test_data.strip().startswith("["):
        return load_dataset_string(test_data, api_type, task_logger)

    # Case 4: File path
    if os.path.exists(test_data):
        return load_dataset_file(test_data, api_type, task_logger)

    raise ValueError(
        f"Invalid test_data provided: '{test_data}'. "
        f"Expected empty string, 'default', JSONL/JSON content string, or valid file path."
    )


# === QUEUE INITIALIZATION ===
def init_prompt_queue_from_string(
    content: str, api_type: str = "", task_logger=None
) -> queue.Queue:
    """Initializes the test data queue from JSONL or JSON array string content.

    Args:
        content (str): JSONL or JSON array format string content.
        task_logger: An optional task-specific logger instance.

    Returns:
        queue.Queue: A queue containing the data.

    Raises:
        ValueError: If no valid prompts are found.
        RuntimeError: If queue initialization fails due to unexpected errors.
    """
    effective_logger = task_logger if task_logger else logger

    if not content.strip():
        raise ValueError("Empty content provided")

    try:
        prompts = load_dataset_string(content, api_type, task_logger)

        if not prompts:
            raise ValueError("No valid prompts were parsed from the content")

        if len(prompts) > MAX_QUEUE_SIZE:
            effective_logger.warning(
                f"Large dataset ({len(prompts)} items), consider splitting"
            )

        q: queue.Queue = queue.Queue()
        for prompt_dict in prompts:
            q.put_nowait(prompt_dict)

        return q

    except ValueError:
        raise
    except Exception as e:
        effective_logger.error(f"Failed to initialize prompt queue from content: {e}")
        raise RuntimeError(f"Failed to initialize prompt queue from content: {e}")


def init_prompt_queue_from_file(
    file_path: str, api_type: str = "", task_logger=None
) -> queue.Queue:
    """Initializes the test data queue from a custom file.

    Args:
        file_path (str): Path to the JSONL or JSON file.
        task_logger: An optional task-specific logger instance.

    Returns:
        queue.Queue: A queue containing the data.

    Raises:
        ValueError: If file not found or no prompts loaded.
        RuntimeError: If queue initialization fails due to unexpected errors.
    """
    effective_logger = task_logger if task_logger else logger

    if not os.path.exists(file_path):
        raise ValueError(f"Custom data file not found: {file_path}")

    try:
        prompts = load_dataset_file(file_path, api_type, task_logger)
        if not prompts:
            raise ValueError("No prompts were loaded from the custom data file")

        q: queue.Queue = queue.Queue()
        for prompt_data in prompts:
            q.put_nowait(prompt_data)

        return q

    except ValueError:
        raise
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
    api_type: str = "",
    task_logger=None,
) -> queue.Queue:
    """Initializes the test data queue based on the chat type and custom test data.

    Args:
        chat_type (int): The chat type, 0 for text-only, 1 for multimodal.
        test_data (str, optional): Custom test data - can be JSONL/JSON string content,
            file path, "default", or empty.
        api_type: API type for format-specific handling.
        task_logger: An optional task-specific logger instance.

    Returns:
        queue.Queue: A queue containing the data.
    """
    items = _resolve_dataset_items(chat_type, test_data, api_type, task_logger)

    # None means no-dataset mode
    if items is None:
        return queue.Queue()

    if not items:
        raise ValueError("No valid prompts were parsed from test_data")

    effective_logger = task_logger if task_logger else logger
    if len(items) > MAX_QUEUE_SIZE:
        effective_logger.warning(
            f"Large dataset ({len(items)} items), consider splitting"
        )

    q: queue.Queue = queue.Queue()
    for prompt_dict in items:
        q.put_nowait(prompt_dict)

    return q


def init_shared_dataset(
    chat_type: int = 0,
    test_data: str = "",
    api_type: str = "",
    task_logger=None,
):
    """Initialize dataset as a shared mmap reader for multiprocess mode.

    Returns a SharedDatasetReader instance, or None if no dataset is configured
    or if creation fails (caller should use queue-based fallback).
    """
    from utils.shared_dataset import SharedDatasetReader

    effective_logger = task_logger or logger

    try:
        items = _resolve_dataset_items(chat_type, test_data, api_type, task_logger)

        if not items:
            return None

        if len(items) > MAX_QUEUE_SIZE:
            effective_logger.warning(
                f"Dataset ({len(items)} items) exceeds MAX_QUEUE_SIZE={MAX_QUEUE_SIZE}; truncating."
            )
            items = items[:MAX_QUEUE_SIZE]

        return SharedDatasetReader.from_items(items, task_logger)
    except Exception as e:
        effective_logger.warning(
            f"Failed to create shared dataset reader: {e}. Falling back to queue."
        )
        return None
