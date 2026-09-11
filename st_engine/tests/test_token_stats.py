"""Tests for Input_tokens reporting: failed requests must not be counted."""

from unittest.mock import Mock

from engine.llm_locustfile import _has_token_data, _report_token_stats
from utils.token_counter import AsyncTokenCounter


class TestHasTokenData:
    def test_failed_request_zeroed_usage_is_not_countable(self):
        assert not _has_token_data(
            "",
            "",
            {"completion_tokens": 0, "total_tokens": 0},
        )

    def test_failed_request_none_total_is_not_countable(self):
        assert not _has_token_data(
            "",
            "",
            {"completion_tokens": 0, "total_tokens": None},
        )

    def test_empty_or_missing_usage_is_not_countable(self):
        assert not _has_token_data("", "", {})
        assert not _has_token_data("", "", None)

    def test_response_text_is_countable(self):
        assert _has_token_data("", "hello", {"completion_tokens": 0})
        assert _has_token_data("thinking", "", {"completion_tokens": 0})

    def test_api_usage_tokens_are_countable(self):
        assert _has_token_data("", "", {"prompt_tokens": 12})
        assert _has_token_data("", "", {"input_tokens": 8})
        assert _has_token_data("", "", {"completion_tokens": 3})
        assert _has_token_data("", "", {"total_tokens": 20})


class TestReportTokenStats:
    def test_zero_tokens_do_not_fire_input_tokens(self, monkeypatch):
        fired = []
        monkeypatch.setattr(
            "engine.llm_locustfile.EventManager.fire_metric_event",
            lambda name, response_time, response_length: fired.append(name),
        )
        env = Mock()
        env.runner = None
        _report_token_stats(16, 0, 0, env, Mock())
        assert "Input_tokens" not in fired

    def test_successful_request_fires_input_tokens(self, monkeypatch):
        fired = []
        monkeypatch.setattr(
            "engine.llm_locustfile.EventManager.fire_metric_event",
            lambda name, response_time, response_length: fired.append(
                (name, response_time)
            ),
        )
        env = Mock()
        env.runner = None
        _report_token_stats(16, 4, 20, env, Mock())
        assert ("Input_tokens", 16) in fired
        assert ("Completion_tokens", 4) in fired


class TestCountAsyncExcludesFailedRequests:
    def test_prompt_only_failed_request_does_not_estimate_input(self):
        results = []
        AsyncTokenCounter().count_async(
            user_prompt="count these prompt tokens please",
            reasoning_content="",
            content="",
            model_name="gpt-4o",
            usage={"completion_tokens": 0, "total_tokens": 0},
            on_complete=lambda *args: results.append(args),
        )
        assert results == [(0, 0, 0)]

    def test_successful_usage_still_reports_input(self):
        results = []
        AsyncTokenCounter().count_async(
            user_prompt="ignored when usage is present",
            reasoning_content="",
            content="",
            model_name="gpt-4o",
            usage={"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
            on_complete=lambda *args: results.append(args),
        )
        assert results == [(11, 5, 16)]
