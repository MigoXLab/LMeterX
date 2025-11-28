"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import logging
import math
import re
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any, Optional, cast

tiktoken: Optional[Any] = None

try:
    import tiktoken
except ImportError:
    pass

logger = logging.getLogger(__name__)


TOKENIZER_CACHE_SIZE = 16  # Cache size for tokenizer instances
DEFAULT_TOKEN_RATIO_EN = 4  # Estimate: 1 token ≈ 4 bytes UTF-8
DEFAULT_TOKEN_RATIO_CJK = 3  # Estimate: 1 token ≈ 3 bytes UTF-8
DEFAULT_ENCODING = "cl100k_base"

# Known model aliases (lowercase) → canonical model names
_MODEL_ALIASES = {
    "gpt35-turbo": "gpt-3.5-turbo",
    "gpt-35-turbo": "gpt-3.5-turbo",
    "gpt-35-turbo-16k": "gpt-3.5-turbo-16k",
    "gpt-4-turbo-preview": "gpt-4-turbo",
    "gpt-4-1106-preview": "gpt-4-turbo",
    "gpt-4-0125-preview": "gpt-4o",
}

# Model prefix → encoding hints (ordered by priority)
_MODEL_ENCODING_HINTS = (
    ("gpt-4o", "o200k_base"),
    ("gpt-4.1", "o200k_base"),
    ("gpt-4-turbo", "cl100k_base"),
    ("gpt-4", "cl100k_base"),
    ("gpt-3.5", "cl100k_base"),
    ("text-embedding-3", "cl100k_base"),
    ("text-embedding-ada-002", "cl100k_base"),
    ("text-davinci-003", "p50k_base"),
    ("text-davinci-002", "p50k_base"),
    ("davinci", "r50k_base"),
    ("curie", "r50k_base"),
    ("babbage", "r50k_base"),
    ("ada", "r50k_base"),
)


class TokenCounter(ABC):
    """Common interface for token counters with built-in fallback estimation."""

    def count_tokens(self, text: str) -> int:
        """Count tokens for the provided text with a safe fallback."""
        if not text or not text.strip():
            return 0

        try:
            return self._count_tokens(text)
        except Exception as exc:
            logger.warning(
                "Tokenization failed with %s: %s. Falling back to heuristic estimate.",
                self.__class__.__name__,
                exc,
            )
            return self._fallback_token_estimate(text)

    @abstractmethod
    def _count_tokens(self, text: str) -> int:
        """Implementors provide a token count for the given text."""
        raise NotImplementedError

    def encode(self, text: str) -> list[int]:
        """Optional helper for implementations that expose concrete token IDs."""
        raise NotImplementedError("encode() is not implemented for this counter")

    def _fallback_token_estimate(self, text: str) -> int:
        return estimate_tokens_via_bytes(text)


class TikTokenCounter(TokenCounter):
    """Token counter backed by tiktoken encoders."""

    def __init__(self, model_name: str):
        """Initialize the counter with a resolved tiktoken encoding."""
        if tiktoken is None:
            raise ValueError("tiktoken not installed")

        self.model_name = model_name
        self.encoding = self._load_encoding(model_name)

    @staticmethod
    def _load_encoding(model_name: str):
        """Resolve a tiktoken encoding for the given model."""
        normalized = _normalize_model_name(model_name)
        tk = cast(Any, tiktoken)

        try:
            return tk.encoding_for_model(model_name)
        except KeyError:
            logger.debug(
                "encoding_for_model failed for '%s', trying normalized name", model_name
            )

        if normalized and normalized != model_name:
            try:
                return tk.encoding_for_model(normalized)
            except KeyError:
                logger.debug(
                    "encoding_for_model failed for normalized name '%s'", normalized
                )

        encoding_name = _resolve_encoding_name(normalized or model_name)
        logger.debug(
            "Falling back to encoding '%s' for model '%s'", encoding_name, model_name
        )
        return tk.get_encoding(encoding_name)

    def encode(self, text: str) -> list[int]:
        return self.encoding.encode(text, disallowed_special=())

    def _count_tokens(self, text: str) -> int:
        return len(self.encode(text))


class RegexTokenCounter(TokenCounter):
    """
    Lightweight heuristic counter using a Unicode-aware regex.
    Provides a predictable upper bound when tiktoken is unavailable.
    """

    _TOKENIZER_REGEX = re.compile(
        r"\d+\.\d+|"  # decimal numbers
        r"[A-Za-z0-9]+(?:['`][A-Za-z0-9]+)?|"  # words with optional apostrophes/backticks
        r"[\u4E00-\u9FFF]|"  # CJK Unified Ideographs
        r"[^\s]",  # catch-all for remaining non-whitespace chars (emoji, symbols, punctuation)
        re.UNICODE,
    )

    def _count_tokens(self, text: str) -> int:
        tokens = self._TOKENIZER_REGEX.findall(text)
        return len(tokens)


# === Global Tokenizer factory (thread-safe + LRU cache)===
@lru_cache(maxsize=TOKENIZER_CACHE_SIZE)
def get_token_counter(model_name: str) -> TokenCounter:
    """
    Get the token counter for the corresponding model.
    """
    try:
        # Use tiktoken
        if tiktoken:
            try:
                logger.debug("Using tiktoken for model: %s", model_name)
                return TikTokenCounter(model_name)
            except Exception as exc:
                logger.info(
                    "tiktoken failed for '%s': %s. Falling back to regex counter.",
                    model_name,
                    exc,
                )

        logger.debug("Using regex-based token counter for model: %s", model_name)
        return RegexTokenCounter()

    except Exception as exc:
        logger.warning("Failed to initialize tokenizer: %s, using regex counter", exc)
        return RegexTokenCounter()


# === Core function: Efficient token counting (without caching the text itself!)===
def count_tokens(text: str, model_name: str = "gpt-3.5-turbo") -> int:
    """
    Args:
        text (str): Input text
        model_name (str): Model name (determines tokenizer type)

    Returns:
        int: Number of tokens
    """
    if not text or not text.strip():
        return 0

    try:
        counter = get_token_counter(model_name)
        return counter.count_tokens(text)
    except Exception as exc:
        logger.warning(
            "Token counting failed for model '%s': %s. Using byte-ratio fallback.",
            model_name,
            exc,
        )
        return estimate_tokens_via_bytes(text)


def _normalize_model_name(model_name: str) -> str:
    if not model_name:
        return ""

    normalized = model_name.strip().lower()
    if "/" in normalized:
        normalized = normalized.split("/")[-1]
    if ":" in normalized:
        normalized = normalized.split(":")[-1]

    return _MODEL_ALIASES.get(normalized, normalized)


def _resolve_encoding_name(model_name: str) -> str:
    if not model_name:
        return DEFAULT_ENCODING

    for prefix, encoding in _MODEL_ENCODING_HINTS:
        if model_name.startswith(prefix):
            return encoding
    return DEFAULT_ENCODING


def estimate_tokens_via_bytes(text: str) -> int:
    """Heuristic: estimate tokens from UTF-8 byte length."""
    if not text:
        return 0

    utf8_bytes = len(text.encode("utf-8", errors="ignore"))
    if utf8_bytes == 0:
        return 0

    cjk_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    cjk_tokens = cjk_chars

    remaining_bytes = max(0, utf8_bytes - cjk_chars * DEFAULT_TOKEN_RATIO_CJK)
    latin_tokens = (
        math.ceil(remaining_bytes / DEFAULT_TOKEN_RATIO_EN) if remaining_bytes else 0
    )

    estimated = cjk_tokens + latin_tokens
    return max(1, estimated)
