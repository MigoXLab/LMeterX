"""Tests for rendering API-test streaming responses."""

import pytest

from service.llm_task_service import _handle_streaming_response


class FakeStreamingResponse:
    """Minimal streaming HTTP response used to exercise chunk assembly."""

    status_code = 200
    headers = {"content-type": "text/event-stream"}

    def __init__(self, chunks, error=None):
        """Store streamed chunks and an optional error to raise at the end."""
        self.chunks = chunks
        self.error = error

    async def aiter_text(self):
        for chunk in self.chunks:
            yield chunk
        if self.error:
            raise self.error


@pytest.mark.asyncio
async def test_streaming_response_joins_arbitrary_transport_chunks():
    response = FakeStreamingResponse(
        [
            'event: response.output_text.delta\ndata: {"delta":"Hel',
            'lo"}\n\nevent: response.completed\ndata:',
            ' {"status":"completed"}\n\n',
        ]
    )

    result = await _handle_streaming_response(response, "https://example.test")

    assert result["status"] == "success"
    assert result["response"]["data"] == (
        'event: response.output_text.delta\ndata: {"delta":"Hello"}\n\n'
        'event: response.completed\ndata: {"status":"completed"}\n\n'
    )


@pytest.mark.asyncio
async def test_streaming_response_drops_incomplete_line_after_early_error():
    response = FakeStreamingResponse(
        ['event: message\ndata: {"text":"complete"}\n\ndata: {"text":"part'],
        error=RuntimeError("connection reset"),
    )

    result = await _handle_streaming_response(response, "https://example.test")

    assert result["status"] == "success"
    assert result["response"]["data"] == (
        'event: message\ndata: {"text":"complete"}\n\n'
    )
    assert "connection reset" in result["response"]["warning"]


@pytest.mark.asyncio
async def test_streaming_response_keeps_final_line_at_normal_eof():
    response = FakeStreamingResponse(['data: {"done":true}'])

    result = await _handle_streaming_response(response, "https://example.test")

    assert result["status"] == "success"
    assert result["response"]["data"] == 'data: {"done":true}'
