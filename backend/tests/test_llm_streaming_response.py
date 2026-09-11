"""Tests for rendering API-test streaming responses."""

import httpx
import pytest

from service.llm_task_service import _handle_streaming_response


class ChunkedAsyncStream(httpx.AsyncByteStream):
    """HTTPX byte stream with caller-controlled transport chunk boundaries."""

    def __init__(self, chunks, error=None) -> None:
        """Store streamed chunks and an optional error to raise at the end."""
        self.chunks = chunks
        self.error = error

    async def __aiter__(self):
        """Yield encoded chunks and optionally fail like a broken transport."""
        for chunk in self.chunks:
            yield chunk.encode("utf-8")
        if self.error:
            raise self.error


def _streaming_response(chunks, error=None) -> httpx.Response:
    """Build a real HTTPX response so its line decoder is exercised."""
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        stream=ChunkedAsyncStream(chunks, error),
        request=httpx.Request("POST", "https://example.test"),
    )


@pytest.mark.asyncio
async def test_streaming_response_joins_arbitrary_transport_chunks():
    response = _streaming_response(
        [
            'event: response.output_text.delta\ndata: {"delta":"Hel',
            'lo"}\n\nevent: response.completed\ndata:',
            ' {"status":"completed"}\n\n',
        ]
    )

    result = await _handle_streaming_response(response, "https://example.test")

    assert result["status"] == "success"
    assert result["response"]["data"] == [
        "event: response.output_text.delta",
        'data: {"delta":"Hello"}',
        "event: response.completed",
        'data: {"status":"completed"}',
    ]


@pytest.mark.asyncio
async def test_streaming_response_drops_incomplete_line_after_early_error():
    response = _streaming_response(
        ['event: message\ndata: {"text":"complete"}\n\ndata: {"text":"part'],
        error=RuntimeError("connection reset"),
    )

    result = await _handle_streaming_response(response, "https://example.test")

    assert result["status"] == "success"
    assert result["response"]["data"] == [
        "event: message",
        'data: {"text":"complete"}',
    ]
    assert "connection reset" in result["response"]["warning"]


@pytest.mark.asyncio
async def test_streaming_response_keeps_final_line_at_normal_eof():
    response = _streaming_response(['data: {"done":true}'])

    result = await _handle_streaming_response(response, "https://example.test")

    assert result["status"] == "success"
    assert result["response"]["data"] == ['data: {"done":true}']
