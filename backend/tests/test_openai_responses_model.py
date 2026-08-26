"""Validation tests for OpenAI Responses API task payloads."""

import json

from model.llm_task import TaskTestReq


def test_responses_test_request_generates_input_payload():
    request = TaskTestReq(
        target_host="https://api.example.com",
        api_path="/v1/responses",
        api_type="openai-responses",
        model="gpt-test",
        stream_mode=True,
        request_payload="",
    )

    assert json.loads(request.request_payload) == {
        "model": "gpt-test",
        "stream": True,
        "input": "Hi",
    }
