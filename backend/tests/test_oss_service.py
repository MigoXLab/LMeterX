"""Unit tests for backend OSS service helpers."""

from service.oss_service import _is_object_not_found_error


class TestOssErrorClassification:
    def test_detects_404_response_metadata(self):
        error = Exception("not found")
        error.response = {  # type: ignore[attr-defined]
            "ResponseMetadata": {"HTTPStatusCode": 404}
        }

        assert _is_object_not_found_error(error) is True

    def test_detects_no_such_key_code(self):
        error = Exception("not found")
        error.response = {"Error": {"Code": "NoSuchKey"}}  # type: ignore[attr-defined]

        assert _is_object_not_found_error(error) is True

    def test_regular_exception_is_not_not_found(self):
        assert _is_object_not_found_error(RuntimeError("network down")) is False
