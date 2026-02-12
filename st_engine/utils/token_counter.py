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
# Default to the latest OpenAI BPE encoding (o200k_base).
# New / unknown models automatically use this — no manual updates needed.
DEFAULT_ENCODING = "o200k_base"

# Known model aliases (lowercase) → canonical model names
_MODEL_ALIASES = {
    "gpt35-turbo": "gpt-3.5-turbo",
    "gpt-35-turbo": "gpt-3.5-turbo",
    "gpt-35-turbo-16k": "gpt-3.5-turbo-16k",
    "gpt-4-turbo-preview": "gpt-4-turbo",
    "gpt-4-1106-preview": "gpt-4-turbo",
    "gpt-4-0125-preview": "gpt-4o",
    "o1-preview": "o1",
    "o1-mini-2024-09-12": "o1-mini",
    "o3-mini-2025-01-31": "o3-mini",
}

# Legacy model prefix → encoding overrides.
# Only models that do NOT use the latest DEFAULT_ENCODING (o200k_base) are
# listed here. Any model not matched below falls through to o200k_base,
# so new models (o-series, gpt-4o, gpt-4.1, gpt-4.5, …) need NO changes.
_MODEL_ENCODING_HINTS = (
    # GPT-4 / GPT-3.5 era — cl100k_base
    ("gpt-4-turbo", "cl100k_base"),
    ("gpt-4-", "cl100k_base"),  # gpt-4-0613, gpt-4-32k, etc. (but NOT gpt-4o*)
    ("gpt-3.5", "cl100k_base"),
    # Embeddings — cl100k_base
    ("text-embedding-3", "cl100k_base"),
    ("text-embedding-ada-002", "cl100k_base"),
    # Legacy completions models
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
        if not text or text.isspace():
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

        # Step 1: Try normalized name first (handles aliases, path prefixes, etc.)
        if normalized:
            try:
                return tk.encoding_for_model(normalized)
            except KeyError:
                logger.debug(
                    "encoding_for_model failed for normalized name '%s'", normalized
                )

        # Step 2: Try original name as fallback
        if normalized != model_name:
            try:
                return tk.encoding_for_model(model_name)
            except KeyError:
                logger.debug(
                    "encoding_for_model failed for original name '%s'", model_name
                )

        # Step 3: Resolve encoding by prefix hints
        encoding_name = _resolve_encoding_name(normalized or model_name)
        logger.debug(
            "Falling back to encoding '%s' for model '%s'", encoding_name, model_name
        )
        return tk.get_encoding(encoding_name)

    def encode(self, text: str) -> list[int]:
        """Encode text into token IDs using the resolved tokenizer."""
        return self.encoding.encode(text, disallowed_special=())

    def _count_tokens(self, text: str) -> int:
        return len(self.encode(text))


class RegexTokenCounter(TokenCounter):
    """
    Lightweight heuristic counter using a Unicode-aware regex.
    Applies a subword compensation factor to approximate BPE tokenization
    when tiktoken is unavailable.
    """

    # Subword compensation: BPE splits long words into subwords, so raw word
    # count underestimates real token count. 1.3 is an empirical factor that
    # brings regex estimates closer to tiktoken results on mixed EN/CJK text.
    _SUBWORD_FACTOR = 1.3

    _TOKENIZER_REGEX = re.compile(
        r"\d+\.\d+|"  # decimal numbers
        r"[A-Za-z0-9]+(?:['`][A-Za-z0-9]+)?|"  # words with optional apostrophes/backticks
        r"[\u3040-\u30FF]|"  # Japanese Hiragana + Katakana
        r"[\u4E00-\u9FFF\u3400-\u4DBF]|"  # CJK Unified Ideographs (basic + Ext-A)
        r"[\uAC00-\uD7AF]|"  # Korean Hangul Syllables
        r"[^\s]",  # catch-all for remaining non-whitespace chars (emoji, symbols, punctuation)
        re.UNICODE,
    )

    # Characters that are typically 1 token each in BPE (no subword splitting)
    _CJK_LIKE_RE = re.compile(r"[\u3040-\u30FF\u4E00-\u9FFF\u3400-\u4DBF\uAC00-\uD7AF]")

    def _count_tokens(self, text: str) -> int:
        tokens = self._TOKENIZER_REGEX.findall(text)
        raw_count = len(tokens)
        if raw_count == 0:
            return 0

        # CJK / Kana / Hangul characters are typically 1 token each, no subword factor
        cjk_count = len(self._CJK_LIKE_RE.findall(text))
        non_cjk_count = raw_count - cjk_count

        # Apply subword compensation only to non-CJK tokens
        estimated = cjk_count + math.ceil(non_cjk_count * self._SUBWORD_FACTOR)
        return max(1, estimated)


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


# === Core function: Efficient token counting ===
def count_tokens(text: str, model_name: str = "gpt-4o") -> int:
    """
    Args:
        text (str): Input text
        model_name (str): Model name (determines tokenizer type)

    Returns:
        int: Number of tokens
    """
    if not text or text.isspace():
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
    """Heuristic: estimate tokens from UTF-8 byte length.

    Uses empirical ratios:
    - CJK characters: ~0.7 tokens per character (BPE often merges common bigrams)
    - Latin/other: ~1 token per 4 UTF-8 bytes
    """
    if not text:
        return 0

    utf8_bytes = len(text.encode("utf-8", errors="ignore"))
    if utf8_bytes == 0:
        return 0

    # Count CJK-like characters (CJK Unified basic + Ext-A, Kana, Hangul)
    cjk_chars = sum(
        1
        for char in text
        if (
            "\u4e00" <= char <= "\u9fff"
            or "\u3400" <= char <= "\u4dbf"
            or "\u3040" <= char <= "\u30ff"
            or "\uac00" <= char <= "\ud7af"
        )
    )
    # BPE tokenizers commonly merge frequent CJK bigrams → ~0.7 tokens/char
    cjk_tokens = math.ceil(cjk_chars * 0.7)

    remaining_bytes = max(0, utf8_bytes - cjk_chars * DEFAULT_TOKEN_RATIO_CJK)
    latin_tokens = (
        math.ceil(remaining_bytes / DEFAULT_TOKEN_RATIO_EN) if remaining_bytes else 0
    )

    estimated = cjk_tokens + latin_tokens
    return max(1, estimated)
