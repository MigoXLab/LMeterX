from utils.request_headers import (
    merge_headers,
    next_rerun_name,
    redact_header_names_for_copy,
    redact_headers_for_copy,
    redacted_header_keys,
)


def test_redact_headers_keeps_system_content_type_only():
    rows = redact_headers_for_copy(
        {
            "Content-Type": "application/json",
            "Authorization": "Bearer top-secret",
            "X-Custom": "also-secret",
        }
    )

    assert rows[0]["value"] == "application/json"
    assert rows[0]["fixed"] is True
    assert rows[1]["value"] is None
    assert rows[1]["configured"] is True
    assert rows[2]["value"] is None
    assert redacted_header_keys(
        {"Content-Type": "application/json", "Authorization": "secret"}
    ) == ["Authorization"]
    assert redact_header_names_for_copy(["X-Api-Key"])[0]["value"] is None


def test_merge_headers_applies_case_insensitive_overrides():
    assert merge_headers(
        {"Authorization": "Bearer original", "X-Trace": "original"},
        {"authorization": "Bearer replacement"},
    ) == {
        "authorization": "Bearer replacement",
        "X-Trace": "original",
    }
    assert next_rerun_name("load-test-9") == "load-test-10"
