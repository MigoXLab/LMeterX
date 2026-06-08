"""Tests for request processor utils and memory release logic."""

import inspect
import time
from unittest.mock import Mock, patch

from engine.core import GlobalConfig
from engine.request_processor import APIClient
from utils.error_handler import _safe_repr_truncate


# =====================================================================
# Tests for _safe_repr_truncate
# =====================================================================
def test_safe_repr_truncate_string():
    """Test truncate logic for string objects."""
    short_str = "hello"
    assert _safe_repr_truncate(short_str, limit=10) == "hello"

    long_str = "abcdefghij"  # len = 10
    assert _safe_repr_truncate(long_str, limit=5) == "abcde... (truncated)"


def test_safe_repr_truncate_dict():
    """Test truncate logic for dictionary objects."""
    # 1. Simple small dict
    small_dict = {"a": 1, "b": 2}
    res = _safe_repr_truncate(small_dict, limit=50)
    assert "'a': 1" in res
    assert "'b': 2" in res

    # 2. Dict with extremely long value
    long_val = "x" * 200
    long_val_dict = {"a": long_val}
    res = _safe_repr_truncate(long_val_dict, limit=150)
    assert "..." in res  # Inside the value
    assert len(res) < 150

    # 3. Dict overshooting total limit
    large_dict = {f"key_{i}": "value" for i in range(100)}
    res = _safe_repr_truncate(large_dict, limit=50)
    assert res.endswith("...}")
    assert len(res) <= 50


def test_safe_repr_truncate_list_tuple():
    """Test truncate logic for list and tuple objects."""
    lst = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    res = _safe_repr_truncate(lst, limit=10)
    assert "truncated" in res

    tup = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
    res = _safe_repr_truncate(tup, limit=10)
    assert "truncated" in res


def test_safe_repr_truncate_unrepresentable():
    """Test fallback when object representation raises Exception."""

    class BadRepr:
        def __repr__(self):
            raise ValueError("bad repr")

    assert _safe_repr_truncate(BadRepr()) == "<unrepresentable>"


# =====================================================================
# Tests for request_kwargs payload release (memory optimization)
# =====================================================================
class FakeResponse:
    """Fake response context manager for testing."""

    def __init__(self):
        """Initialize FakeResponse."""
        self.status_code = 200
        self.headers = {}

        # Verify request_kwargs is popped before response.success() completes
        def success_side_effect():
            frame = inspect.currentframe().f_back
            if "request_kwargs" in frame.f_locals:
                req_kwargs = frame.f_locals["request_kwargs"]
                assert "json" not in req_kwargs
                assert "data" not in req_kwargs
            else:
                raise AssertionError("request_kwargs not found")

        self.success = Mock(side_effect=success_side_effect)
        self.failure = Mock()

    def __enter__(self):
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc, tb):
        """Exit context manager."""
        return False

    def json(self):
        """Return fake response json."""
        return {"choices": [{"message": {"content": "response text"}}]}


class FakeClient:
    """Fake HTTP client to verify that post() popped json and data."""

    def __init__(self, response):
        """Initialize FakeClient."""
        self.response = response
        self.called_with_kwargs = None

    def post(self, url, **kwargs):
        """Mock post request."""
        self.called_with_kwargs = kwargs
        return self.response


@patch(
    "engine.request_processor.EventManager.fire_failure_event",
    lambda *args, **kwargs: None,
)
@patch(
    "engine.request_processor.EventManager.fire_metric_event",
    lambda *args, **kwargs: None,
)
def test_handle_non_stream_request_releases_payload(monkeypatch):
    """Verify handle_non_stream_request pops json and data."""
    config = GlobalConfig()
    config.api_type = "openai-chat"
    config.stream_mode = False
    config.api_path = "/v1/chat/completions"

    api_client = APIClient(config, Mock())

    fake_response = FakeResponse()
    fake_client = FakeClient(fake_response)

    request_kwargs = {
        "json": {
            "model": "test",
            "messages": [{"role": "user", "content": "hi" * 100}],
        },
        "data": "some_raw_data",
        "headers": {},
    }

    # Execute request
    _, _, _ = api_client.handle_non_stream_request(
        fake_client,
        request_kwargs,
        time.perf_counter(),
    )

    # Note that in APIClient, the original request_kwargs passed to
    # handle_non_stream_request is a base_request_kwargs dictionary.
    # The success_side_effect assertion verifies that it is mutated.
    fake_response.success.assert_called_once()
