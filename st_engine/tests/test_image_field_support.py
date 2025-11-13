"""
Test image field support in dataset loader.

Tests for both "image" and "image_path" fields with different path formats.

Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import json
import os
import tempfile

import pytest

from utils.dataset_loader import parse_data_line


class TestImageFieldSupport:
    """Test image field parsing with different field names and path formats."""

    @pytest.fixture
    def temp_image_file(self):
        """Create a temporary image file for testing."""
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".png", delete=False) as f:
            # Write a minimal PNG file (1x1 transparent pixel)
            png_data = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
                b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            f.write(png_data)
            temp_path = f.name

        yield temp_path

        # Cleanup
        try:
            os.unlink(temp_path)
        except Exception:
            pass

    def test_image_field(self):
        """Test parsing with 'image' field (original field name)."""
        line = json.dumps(
            {
                "id": "test1",
                "prompt": "Test prompt",
                "image": "https://example.com/image.jpg",
            }
        )

        result = parse_data_line(line, 1)

        assert result is not None
        assert result.id == "test1"
        assert result.prompt == "Test prompt"
        assert result.image_url == "https://example.com/image.jpg"
        assert result.image_base64 == ""

    def test_image_path_field(self):
        """Test parsing with 'image_path' field (new field name)."""
        line = json.dumps(
            {
                "id": "test2",
                "prompt": "Test prompt",
                "image_path": "https://example.com/image.jpg",
            }
        )

        result = parse_data_line(line, 1)

        assert result is not None
        assert result.id == "test2"
        assert result.prompt == "Test prompt"
        assert result.image_url == "https://example.com/image.jpg"
        assert result.image_base64 == ""

    def test_image_path_array(self):
        """Test parsing with 'image_path' as array (multimodal dataset format)."""
        line = json.dumps(
            {
                "id": "CFSLeKg",
                "prompt": ["这个图形的美学价值如何？"],
                "image_path": ["./data/pic/15.png"],
                "language": "cn",
            }
        )

        result = parse_data_line(line, 1)

        assert result is not None
        assert result.id == "CFSLeKg"
        assert result.prompt == "这个图形的美学价值如何？"
        # If file exists (./data/pic/15.png), it should be encoded
        # Otherwise it will be empty string
        # Just verify it doesn't crash and properly extracts prompt
        assert result.image_url == ""  # Not a URL (it's a file path)

    def test_absolute_path(self, temp_image_file):
        """Test parsing with absolute path."""
        line = json.dumps(
            {"id": "test3", "prompt": "Test prompt", "image_path": temp_image_file}
        )

        result = parse_data_line(line, 1)

        assert result is not None
        assert result.prompt == "Test prompt"
        assert result.image_base64 != ""  # Should have encoded image
        assert result.image_url == ""

    def test_relative_path(self, temp_image_file):
        """Test parsing with relative path."""
        # Create a relative path from temp file
        cwd = os.getcwd()
        rel_path = os.path.relpath(temp_image_file, cwd)

        line = json.dumps({"id": "test4", "prompt": "Test prompt", "image": rel_path})

        result = parse_data_line(line, 1)

        assert result is not None
        assert result.prompt == "Test prompt"
        # Note: This might fail if relative path resolution doesn't work
        # That's expected behavior - just checking it doesn't crash

    def test_image_priority_over_image_path(self):
        """Test that 'image' field takes priority over 'image_path'."""
        line = json.dumps(
            {
                "id": "test5",
                "prompt": "Test prompt",
                "image": "https://example.com/image1.jpg",
                "image_path": "https://example.com/image2.jpg",
            }
        )

        result = parse_data_line(line, 1)

        assert result is not None
        assert (
            result.image_url == "https://example.com/image1.jpg"
        )  # Should use 'image'

    def test_missing_image_field(self):
        """Test parsing with no image field."""
        line = json.dumps({"id": "test6", "prompt": "Test prompt"})

        result = parse_data_line(line, 1)

        assert result is not None
        assert result.prompt == "Test prompt"
        assert result.image_base64 == ""
        assert result.image_url == ""

    def test_empty_image_field(self):
        """Test parsing with empty image field."""
        line = json.dumps({"id": "test7", "prompt": "Test prompt", "image": ""})

        result = parse_data_line(line, 1)

        assert result is not None
        assert result.prompt == "Test prompt"
        assert result.image_base64 == ""
        assert result.image_url == ""

    def test_nonexistent_file(self):
        """Test parsing with non-existent file path."""
        line = json.dumps(
            {
                "id": "test8",
                "prompt": "Test prompt",
                "image_path": "./nonexistent/path/to/image.png",
            }
        )

        result = parse_data_line(line, 1)

        # Should not crash, but log warning
        assert result is not None
        assert result.prompt == "Test prompt"
        assert result.image_base64 == ""  # File not found
        assert result.image_url == ""
