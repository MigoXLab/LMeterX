"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import base64
import hashlib
import json
import os
import queue
import re
import threading
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple, Union

import tiktoken

from utils.config import (
    DEFAULT_TOKEN_RATIO,
    IMAGES_DIR,
    MAX_QUEUE_SIZE,
    PROMPTS_DIR,
    SENSITIVE_KEYS,
    TOKEN_COUNT_CACHE_SIZE,
    TOKENIZER_CACHE_SIZE,
)
from utils.logger import logger

# Lightweight LRU cache for token counts to avoid repeated tokenization cost
_token_count_cache: Dict[Tuple[str, str], int] = {}
_token_count_cache_order: List[Tuple[str, str]] = []
_token_count_cache_lock = threading.Lock()


# === DATA CLASSES ===
class PromptData:
    """Structured prompt data representation."""

    def __init__(
        self,
        prompt_id: Union[str, int],
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


# === UTILITY FUNCTIONS ===
def mask_sensitive_data(data: Union[dict, list]) -> Union[dict, list]:
    """Masks sensitive information for safe logging.

    Args:
        data (Union[dict, list]): The data to mask.

    Returns:
        Union[dict, list]: The masked data.
    """
    if isinstance(data, dict):
        safe_dict: Dict[Any, Any] = {}
        try:
            for key, value in data.items():
                if isinstance(key, str) and key.lower() in SENSITIVE_KEYS:
                    safe_dict[key] = "****"
                else:
                    safe_dict[key] = mask_sensitive_data(value)
        except Exception as e:
            logger.warning(f"Error masking sensitive data: {str(e)}")
            return data
        return safe_dict
    elif isinstance(data, list):
        return [mask_sensitive_data(item) for item in data]
    else:
        return data


def mask_sensitive_command(command_list: list) -> list:
    """Masks sensitive command for safe logging.

    Args:
        command_list (list): The list of commands to mask.

    Returns:
        list: The masked command list.
    """
    if not isinstance(command_list, list):
        return command_list

    safe_list = []
    try:
        for item in command_list:
            new_item = re.sub(
                r'("Authorization"\s*:\s*").*?(")',
                r"\1********\2",
                item,
                flags=re.IGNORECASE,
            )
            safe_list.append(new_item)
        return safe_list
    except Exception as e:
        logger.warning(f"Error masking sensitive command: {str(e)}")
        return command_list


def encode_image(image_path: str) -> str:
    """Encodes an image file into a base64 string.

    Args:
        image_path (str): The path to the image file to encode.

    Returns:
        str: The base64 encoded image string.

    Raises:
        FileNotFoundError: If the image file doesn't exist.
        IOError: If there's an issue reading the file.
    """
    image_full_path = os.path.join(IMAGES_DIR, image_path)

    if not os.path.exists(image_full_path):
        raise FileNotFoundError(f"Image file not found: {image_full_path}")

    try:
        with open(image_full_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    except IOError as e:
        raise IOError(f"Failed to read image file {image_full_path}: {e}")


# === DATA PROCESSING ===
def _normalize_prompt_field(prompt: Any) -> str:
    """Normalize prompt field to string."""
    if isinstance(prompt, str):
        return prompt
    elif isinstance(prompt, list) and prompt:
        return str(prompt[0])
    else:
        return ""


def _normalize_image_path(image_path: Any) -> Optional[str]:
    """Normalize image path field."""
    if isinstance(image_path, str):
        return image_path
    elif isinstance(image_path, list) and image_path:
        return str(image_path[0])
    else:
        return None


def _parse_jsonl_line(
    line: str, line_num: int, task_logger=None
) -> Optional[PromptData]:
    """Parse a single JSONL line into PromptData.

    Args:
        line: The JSONL line to parse
        line_num: Line number for error reporting
        task_logger: Optional logger for this task

    Returns:
        PromptData object or None if parsing fails
    """
    effective_logger = task_logger if task_logger else logger

    try:
        json_obj = json.loads(line.strip())

        # Extract ID
        prompt_id = json_obj.get("id", line_num)

        # Extract and normalize prompt
        prompt = _normalize_prompt_field(json_obj.get("prompt"))
        if not prompt:
            effective_logger.warning(f"Empty prompt in line {line_num}: {line}")
            return None

        # Handle images
        image_base64 = ""
        image_url = ""

        # Process image_path for base64 encoding
        image_path = _normalize_image_path(json_obj.get("image_path"))
        if image_path:
            try:
                image_base64 = encode_image(image_path)
            except IOError as e:
                effective_logger.warning(f"Failed to encode image {image_path}: {e}")

        # Process image_url
        if "image_url" in json_obj:
            image_url_raw = json_obj["image_url"]
            if isinstance(image_url_raw, list) and image_url_raw:
                image_url = str(image_url_raw[0])
            elif isinstance(image_url_raw, str):
                image_url = image_url_raw

        return PromptData(prompt_id, prompt, image_base64, image_url)

    except json.JSONDecodeError as e:
        effective_logger.error(
            f"JSON decode error in line {line_num}: {line}. Error: {e}"
        )
        return None
    except Exception as e:
        effective_logger.error(f"Unexpected error parsing line {line_num}: {e}")
        return None


def load_data(data_file: str, task_logger=None) -> List[Dict[str, Any]]:
    """Load all stress test data from file.

    Args:
        data_file (str): Path to the JSONL file containing ids and prompts.
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
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue

                prompt_data = _parse_jsonl_line(line, line_num, task_logger)
                if prompt_data:
                    prompts.append(prompt_data.to_dict())

    except IOError as e:
        effective_logger.error(f"Error reading file {data_file}: {e}")
    except Exception as e:
        effective_logger.error(f"Error loading prompts from {data_file}: {e}")

    return prompts


def init_prompt_queue_from_string(jsonl_content: str, task_logger=None) -> queue.Queue:
    """Initializes the test data queue from JSONL string content.

    Args:
        jsonl_content (str): JSONL format string content.
        task_logger: An optional task-specific logger instance.

    Returns:
        queue.Queue: A queue containing the data.

    Raises:
        ValueError: If no valid prompts are found.
        RuntimeError: If queue initialization fails.
    """
    effective_logger = task_logger if task_logger else logger
    q: queue.Queue = queue.Queue()

    if not jsonl_content.strip():
        raise ValueError("Empty JSONL content provided")

    try:
        lines = jsonl_content.strip().split("\n")
        prompts: List[Dict[str, Any]] = []

        for line_num, line in enumerate(lines, 1):
            if not line.strip():
                continue

            prompt_data = _parse_jsonl_line(line, line_num, task_logger)
            if prompt_data:
                prompts.append(prompt_data.to_dict())

        if not prompts:
            raise ValueError("No valid prompts were parsed from the JSONL content")

        # Add to queue with size validation
        if len(prompts) > MAX_QUEUE_SIZE:
            effective_logger.warning(
                f"Large dataset ({len(prompts)} items), consider splitting"
            )

        for prompt_dict in prompts:
            q.put_nowait(prompt_dict)

        return q

    except Exception as e:
        effective_logger.error(
            f"Failed to initialize prompt queue from JSONL content: {e}"
        )
        raise RuntimeError(f"Failed to initialize prompt queue from JSONL content: {e}")


def init_prompt_queue_from_file(file_path: str, task_logger=None) -> queue.Queue:
    """Initializes the test data queue from a custom file.

    Args:
        file_path (str): Path to the JSONL file.
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

    q: queue.Queue = queue.Queue()

    try:
        prompts = load_data(file_path, task_logger)
        if not prompts:
            raise ValueError("No prompts were loaded from the custom data file")

        for prompt_data in prompts:
            q.put_nowait(prompt_data)

        # effective_logger.info(
        #     f"Successfully initialized queue with {q.qsize()} prompts from file: {file_path}"
        # )
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

    Args:
        chat_type (int): The chat type, 0 for text-only, 1 for multimodal.
        test_data (str, optional): Custom test data - can be JSONL string content, file path, "default", or empty.
        task_logger: An optional task-specific logger instance.

    Returns:
        queue.Queue: A queue containing the data.
    """
    effective_logger = task_logger if task_logger else logger

    # Case 1: Empty test_data - no dataset mode, use request_payload directly
    if not test_data or test_data.strip() == "":
        # effective_logger.info(
        #     "No test_data provided, will use request_payload directly"
        # )
        # Return empty queue for no-dataset mode
        return queue.Queue()

    # Case 2: test_data is "default" - use built-in dataset based on chat_type
    if test_data.strip().lower() == "default":
        # effective_logger.info(f"Using default dataset for chat_type={chat_type}")
        filename = "0.jsonl" if chat_type == 0 else "1.jsonl"
        data_file = os.path.join(PROMPTS_DIR, filename)

        if not os.path.exists(data_file):
            raise ValueError(f"Default data file not found: {data_file}")

        return init_prompt_queue_from_file(data_file, task_logger)

    # Case 3: test_data is JSONL content string (starts with "{")
    if test_data.strip().startswith("{"):
        # effective_logger.info("Processing test_data as JSONL content string")
        return init_prompt_queue_from_string(test_data, task_logger)

    # Case 4: test_data is a file path - handle both absolute and relative paths
    # effective_logger.info(f"Processing test_data as file path: {test_data}")

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
        f"Expected empty string, 'default', JSONL content string, or valid file path."
    )


# === TOKEN PROCESSING ===
@lru_cache(maxsize=TOKENIZER_CACHE_SIZE)
def get_tokenizer(model_name: str) -> Optional[tiktoken.Encoding]:
    """Gets the tokenizer for a specified model, using LRU cache to reduce creation overhead.

    Args:
        model_name (str): The name of the model to get the tokenizer for.

    Returns:
        tiktoken.Encoding: The tokenizer for the specified model, or None if failed.
    """
    try:
        # Get the appropriate encoder based on the model name
        if "gpt-4" in model_name.lower():
            return tiktoken.encoding_for_model("gpt-4")
        elif "gpt-3.5" in model_name.lower():
            return tiktoken.encoding_for_model("gpt-3.5-turbo")
        elif "claude" in model_name.lower():
            # Claude uses tokenization similar to GPT-4
            return tiktoken.encoding_for_model("gpt-4")
        else:
            # Default to gpt-3.5-turbo encoder
            return tiktoken.encoding_for_model("gpt-3.5-turbo")
    except Exception as e:
        logger.warning(
            f"Failed to get tokenizer for {model_name}: {e}, will use simple estimation"
        )
        return None


def count_tokens(text: str, model_name: str = "gpt-3.5-turbo") -> int:
    """Calculates the number of tokens in a text.

    Args:
        text (str): The text to calculate the number of tokens for.
        model_name (str): The name of the model to use for tokenization.

    Returns:
        int: The number of tokens in the text.
    """
    try:
        text_key = hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()
        cache_key = (text_key, model_name)
        with _token_count_cache_lock:
            cached = _token_count_cache.get(cache_key)
            if cached is not None:
                return cached

        tokenizer = get_tokenizer(model_name)
        if tokenizer:
            tokens_len = len(tokenizer.encode(text))
        else:
            tokens_len = max(1, len(text) // DEFAULT_TOKEN_RATIO)

        with _token_count_cache_lock:
            if cache_key not in _token_count_cache:
                _token_count_cache[cache_key] = tokens_len
                _token_count_cache_order.append(cache_key)
                if len(_token_count_cache_order) > TOKEN_COUNT_CACHE_SIZE:
                    old_key = _token_count_cache_order.pop(0)
                    _token_count_cache.pop(old_key, None)

        return tokens_len
    except Exception as e:
        logger.warning(
            f"Token counting failed for {model_name}: {e}, using simple estimation"
        )
        return max(1, len(text) // DEFAULT_TOKEN_RATIO)


# === METRICS PROCESSING ===
def _drain_queue(q: queue.Queue) -> List[int]:
    """Safely drain all items from a queue."""
    items = []
    while not q.empty():
        try:
            items.append(q.get_nowait())
        except queue.Empty:
            break
    return items


def calculate_custom_metrics(
    task_id: str, global_task_queue: Dict[str, queue.Queue], exc_time: float
) -> Dict[str, float]:
    """Calculates custom performance metrics.

    Args:
        task_id: Task identifier
        global_task_queue: Dictionary containing token queues
        exc_time: Execution time in seconds

    Returns:
        Dictionary containing calculated metrics
    """
    task_logger = logger.bind(task_id=task_id)

    # Initialize metrics
    metrics = {
        "reqs_num": 0,
        "req_throughput": 0.0,
        "completion_tps": 0.0,
        "total_tps": 0.0,
        "avg_total_tokens_per_req": 0.0,
        "avg_completion_tokens_per_req": 0.0,
    }

    try:
        # Process completion tokens
        completion_tokens_list = _drain_queue(
            global_task_queue["completion_tokens_queue"]
        )
        completion_tokens = sum(completion_tokens_list)
        metrics["reqs_num"] = len(completion_tokens_list)

        # Process all tokens
        all_tokens_list = _drain_queue(global_task_queue["all_tokens_queue"])
        all_tokens = sum(all_tokens_list)

        # Calculate throughput metrics
        if exc_time and exc_time > 0:
            metrics["completion_tps"] = completion_tokens / exc_time
            metrics["total_tps"] = all_tokens / exc_time
            metrics["req_throughput"] = metrics["reqs_num"] / exc_time
        else:
            task_logger.warning(
                f"Invalid execution time ({exc_time}s), throughput metrics set to 0"
            )

        # Calculate average tokens per request
        if completion_tokens_list:
            metrics["avg_completion_tokens_per_req"] = completion_tokens / len(
                completion_tokens_list
            )

        if all_tokens_list:
            metrics["avg_total_tokens_per_req"] = all_tokens / len(all_tokens_list)

        # task_logger.info(f"Custom metrics calculated: {metrics}")
        return metrics

    except Exception as e:
        task_logger.error(f"Failed to calculate custom metrics: {e}")
        return metrics


def get_locust_stats(task_id: str, environment_stats) -> List[Dict[str, Any]]:
    """Gets and formats Locust statistics for database use.

    Args:
        task_id: Task identifier
        environment_stats: Locust environment statistics

    Returns:
        List of formatted metrics dictionaries
    """
    task_logger = logger.bind(task_id=task_id)
    all_metrics_list = []

    try:
        from datetime import datetime

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for name, endpoint in environment_stats.entries.items():
            raw_params = {
                "task_id": task_id,
                "metric_type": endpoint.name,
                "num_requests": endpoint.num_requests,
                "num_failures": endpoint.num_failures,
                "avg_latency": endpoint.avg_response_time,
                "min_latency": endpoint.min_response_time,
                "max_latency": endpoint.max_response_time,
                "median_latency": endpoint.median_response_time,
                "p90_latency": endpoint.get_response_time_percentile(0.9),
                "avg_content_length": endpoint.avg_content_length,
                "rps": endpoint.total_rps,
                "created_at": current_time,
            }
            all_metrics_list.append(raw_params)

        return all_metrics_list

    except Exception as e:
        task_logger.error(f"Failed to get Locust statistics: {e}")
        raise RuntimeError(f"Failed to get Locust statistics: {e}")
