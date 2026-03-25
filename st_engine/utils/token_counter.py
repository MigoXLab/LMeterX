"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import logging
import math
import re
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any, Callable, Dict, Optional, Tuple, cast

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


def extract_token_from_usage(usage: Any, keywords: list) -> int:
    """Extract the first valid integer from a usage dict via fuzzy key matching.

    Scans all keys in *usage* and returns the first non-negative ``int`` whose
    key contains any of the given *keywords* (case-insensitive substring match).

    Args:
        usage: A dictionary (typically from an LLM API response ``usage`` field).
               Returns 0 immediately if not a dict.
        keywords: List of lowercase substrings to match against dict keys,
                  e.g. ``["input", "prompt"]`` or ``["output", "completion"]``.

    Returns:
        The first matching non-negative integer value, or 0 if none found.
    """
    if not isinstance(usage, dict):
        return 0
    for key in usage:
        if any(kw in str(key).lower() for kw in keywords):
            val = usage[key]
            if isinstance(val, int) and val >= 0:
                return val
    return 0


def compute_token_counts(
    user_prompt: str,
    reasoning_content: str,
    content: str,
    model_name: str,
    input_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
) -> Tuple[int, int, int]:
    """Compute missing token counts using tiktoken, filling in gaps.

    This is a **pure computation** function with no side effects.  It is
    designed to run in an OS thread pool so that the gevent event loop is
    never blocked by CPU-bound BPE encoding.

    Strategy:
    1. If *input_tokens* is 0 and *user_prompt* is non-empty, count via tiktoken.
    2. If *completion_tokens* is 0:
       a. Derive from ``total - input`` when both are available.
       b. Otherwise count *reasoning_content* + *content* via tiktoken.
    3. Ensure *total_tokens* = input + completion if still 0.

    Args:
        user_prompt: The user prompt text.
        reasoning_content: Chain-of-thought / reasoning text from the response.
        content: Main output text from the response.
        model_name: Model name for tokenizer selection.
        input_tokens: Pre-extracted input token count (0 = unknown).
        completion_tokens: Pre-extracted completion token count (0 = unknown).
        total_tokens: Pre-extracted total token count (0 = unknown).

    Returns:
        Tuple of (input_tokens, completion_tokens, total_tokens).
    """
    # Count input tokens if missing
    if input_tokens == 0 and user_prompt:
        input_tokens = count_tokens(str(user_prompt), model_name)

    # Count completion tokens if missing
    if completion_tokens == 0:
        if total_tokens > 0 and input_tokens > 0:
            # Derive completion from total - input
            completion_tokens = max(total_tokens - input_tokens, 0)
        elif content or reasoning_content:
            # Fallback to manual tokenization from response text
            if reasoning_content:
                completion_tokens += count_tokens(str(reasoning_content), model_name)
            if content:
                completion_tokens += count_tokens(str(content), model_name)

    # Ensure total_tokens consistency
    if total_tokens == 0:
        total_tokens = input_tokens + completion_tokens

    return input_tokens, completion_tokens, total_tokens


# ---------------------------------------------------------------------------
# AsyncTokenCounter — non-blocking wrapper using gevent thread pool
# ---------------------------------------------------------------------------

# Lazy gevent imports: gevent may not be available in all contexts (e.g. unit
# tests, standalone scripts).  The class gracefully falls back to synchronous
# execution when gevent is absent.
_gevent = None
_ThreadPool = None
_GreenletGroup = None


def _ensure_gevent():
    """Lazily import gevent modules.  Called once on first use."""
    global _gevent, _ThreadPool, _GreenletGroup
    if _gevent is not None:
        return True
    try:
        import gevent as _g
        from gevent.pool import Group as _GG
        from gevent.threadpool import ThreadPool as _TP

        _gevent = _g
        _ThreadPool = _TP
        _GreenletGroup = _GG
        return True
    except ImportError:
        logger.debug("gevent not available; AsyncTokenCounter will run synchronously")
        return False


class AsyncTokenCounter:
    """Non-blocking token counter backed by a gevent thread pool.

    Offloads CPU-bound tiktoken BPE encoding to real OS threads so the
    gevent event loop stays unblocked for request greenlets.

    Typical usage::

        counter = AsyncTokenCounter()

        # In the request hot path — returns immediately
        counter.count_async(
            user_prompt, reasoning_content, content,
            model_name, usage, on_complete=my_callback,
        )

        # Before final aggregation — wait for stragglers
        counter.join_pending(timeout=5)

    The *on_complete* callback receives ``(input_tokens, completion_tokens,
    total_tokens)`` and is invoked in the gevent context (safe to fire
    Locust events).

    If gevent is not available (e.g. in unit tests), all computation is
    performed synchronously and the callback is invoked immediately.
    """

    _DEFAULT_POOL_SIZE = 2

    def __init__(self, pool_size: int = _DEFAULT_POOL_SIZE) -> None:
        """Initialize the async token counter with the given pool size."""
        self._pool_size = pool_size
        self._pool = None  # lazily created
        self._pending = None  # lazily created

    def _get_pool(self):
        """Get or lazily create the OS thread pool."""
        if self._pool is None and _ensure_gevent():
            self._pool = _ThreadPool(maxsize=self._pool_size)
        return self._pool

    def _get_pending(self):
        """Get or lazily create the GreenletGroup for tracking."""
        if self._pending is None and _ensure_gevent():
            self._pending = _GreenletGroup()
        return self._pending

    @property
    def pending_count(self) -> int:
        """Number of async token counting greenlets still running."""
        pending = self._get_pending()
        return len(pending) if pending is not None else 0

    def count_async(
        self,
        user_prompt: str,
        reasoning_content: str,
        content: str,
        model_name: str,
        usage: Optional[Dict[str, Optional[int]]],
        on_complete: Callable[[int, int, int], None],
        task_logger=None,
    ) -> None:
        """Compute token counts asynchronously and invoke *on_complete*.

        If the API *usage* dict already provides all necessary counts, the
        callback is invoked **synchronously** with zero CPU overhead (fast
        path).  Otherwise a background greenlet + thread pool is used
        (slow path).

        Args:
            user_prompt: The user prompt text.
            reasoning_content: Reasoning / chain-of-thought text.
            content: Main output text.
            model_name: Model name for tokenizer selection.
            usage: Token usage dict from the API response (may be None).
            on_complete: Callback ``(input_tokens, completion_tokens, total_tokens)``.
            task_logger: Optional logger for error reporting.
        """
        _log = task_logger or logger
        try:
            user_prompt = user_prompt or ""
            reasoning_content = reasoning_content or ""
            content = content or ""

            input_tokens = completion_tokens = total_tokens = 0

            # Step 1: Extract from API usage (O(1), no CPU work)
            if usage:
                input_tokens = extract_token_from_usage(usage, ["input", "prompt"])
                completion_tokens = extract_token_from_usage(
                    usage, ["output", "completion"]
                )
                total_tokens = extract_token_from_usage(usage, ["total", "all"])

            # Step 2: Determine whether CPU-bound tiktoken is needed
            needs_tiktoken = False
            if input_tokens == 0 and user_prompt:
                needs_tiktoken = True
            if completion_tokens == 0:
                if total_tokens > 0 and input_tokens > 0:
                    pass  # derivable without tiktoken
                elif content or reasoning_content:
                    needs_tiktoken = True

            if not needs_tiktoken:
                # --- Fast path: all counts available or derivable ---
                if completion_tokens == 0 and total_tokens > 0 and input_tokens > 0:
                    completion_tokens = max(total_tokens - input_tokens, 0)
                if total_tokens == 0:
                    total_tokens = input_tokens + completion_tokens
                on_complete(input_tokens, completion_tokens, total_tokens)
            else:
                # --- Slow path: offload to greenlet + thread pool ---
                pool = self._get_pool()
                pending = self._get_pending()

                if pool is not None and pending is not None:
                    g = _gevent.spawn(
                        self._run_in_thread,
                        pool,
                        user_prompt,
                        reasoning_content,
                        content,
                        model_name,
                        input_tokens,
                        completion_tokens,
                        total_tokens,
                        on_complete,
                        _log,
                    )
                    pending.add(g)
                else:
                    # gevent unavailable — synchronous fallback
                    result = compute_token_counts(
                        user_prompt,
                        reasoning_content,
                        content,
                        model_name,
                        input_tokens,
                        completion_tokens,
                        total_tokens,
                    )
                    on_complete(*result)
        except Exception as e:
            _log.error(f"Token count_async failed: {e}", exc_info=True)

    @staticmethod
    def _run_in_thread(
        pool,
        user_prompt,
        reasoning_content,
        content,
        model_name,
        input_tokens,
        completion_tokens,
        total_tokens,
        on_complete,
        task_logger,
    ) -> None:
        """Background greenlet body: dispatch to thread pool, then callback.

        ``pool.apply()`` suspends this greenlet (without blocking the event
        loop) while tiktoken runs in a real OS thread.  When the thread
        completes, this greenlet resumes in gevent context and invokes
        *on_complete* — which is safe for firing Locust metric events.
        """
        try:
            result = pool.apply(
                compute_token_counts,
                (
                    user_prompt,
                    reasoning_content,
                    content,
                    model_name,
                    input_tokens,
                    completion_tokens,
                    total_tokens,
                ),
            )
            on_complete(*result)
        except Exception as e:
            task_logger.error(f"Async token counting failed: {e}", exc_info=True)

    def join_pending(self, timeout: float = 5) -> int:
        """Wait for all pending async token counting greenlets to finish.

        Args:
            timeout: Maximum seconds to wait.

        Returns:
            Number of greenlets that did NOT complete within *timeout*.
        """
        pending = self._get_pending()
        if pending is None or len(pending) == 0:
            return 0
        pending.join(timeout=timeout)
        return len(pending)


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
