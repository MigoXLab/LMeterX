"""
Test to verify that dataset_loader supports both 'image' and 'image_path' fields.

Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.dataset_loader import load_dataset_string, parse_data_line


def test_image_field():
    """Test parsing data with 'image' field."""
    line = json.dumps(
        {"id": "test1", "prompt": "Describe this image", "image": "test.png"}
    )

    result = parse_data_line(line, 1)
    assert result is not None, "Failed to parse line with 'image' field"
    assert result.id == "test1"
    assert result.prompt == "Describe this image"
    print("✓ Test passed: 'image' field support")


def test_image_path_field():
    """Test parsing data with 'image_path' field."""
    line = json.dumps(
        {
            "id": "test2",
            "prompt": "What is in this picture?",
            "image_path": "./data/pic/15.png",
        }
    )

    result = parse_data_line(line, 1)
    assert result is not None, "Failed to parse line with 'image_path' field"
    assert result.id == "test2"
    assert result.prompt == "What is in this picture?"
    print("✓ Test passed: 'image_path' field support")


def test_image_path_list_format():
    """Test parsing data with 'image_path' as a list."""
    line = json.dumps(
        {
            "id": "CFSLeKg",
            "prompt": ["这个图形的美学价值如何？"],
            "image_path": ["./data/pic/15.png"],
            "language": "cn",
        }
    )

    result = parse_data_line(line, 1)
    assert result is not None, "Failed to parse line with 'image_path' as list"
    assert result.id == "CFSLeKg"
    assert result.prompt == "这个图形的美学价值如何？"
    print("✓ Test passed: 'image_path' list format support")


def test_image_url_field():
    """Test parsing data with image URL."""
    line = json.dumps(
        {
            "id": "test3",
            "prompt": "Analyze this image",
            "image": "https://example.com/image.jpg",
        }
    )

    result = parse_data_line(line, 1)
    assert result is not None, "Failed to parse line with image URL"
    assert result.id == "test3"
    assert result.prompt == "Analyze this image"
    assert result.image_url == "https://example.com/image.jpg"
    print("✓ Test passed: image URL support")


def test_image_priority():
    """Test that 'image' field takes priority over 'image_path'."""
    line = json.dumps(
        {
            "id": "test4",
            "prompt": "Test priority",
            "image": "priority.png",
            "image_path": "fallback.png",
        }
    )

    result = parse_data_line(line, 1)
    assert result is not None, "Failed to parse line with both fields"
    assert result.id == "test4"
    print("✓ Test passed: 'image' field priority over 'image_path'")


def test_jsonl_string_with_image_path():
    """Test loading JSONL string with image_path fields."""
    jsonl_content = "\n".join(
        [
            json.dumps({"id": "1", "prompt": "First prompt", "image_path": "pic1.png"}),
            json.dumps(
                {"id": "2", "prompt": "Second prompt", "image_path": "pic2.png"}
            ),
            json.dumps({"id": "3", "prompt": "Third prompt", "image": "pic3.png"}),
        ]
    )

    prompts = load_dataset_string(jsonl_content)
    assert len(prompts) == 3, f"Expected 3 prompts, got {len(prompts)}"
    assert prompts[0]["prompt"] == "First prompt"
    assert prompts[1]["prompt"] == "Second prompt"
    assert prompts[2]["prompt"] == "Third prompt"
    print("✓ Test passed: JSONL string with mixed image fields")


def test_json_array_with_image_path():
    """Test loading JSON array (ShareGPT format) with image_path."""
    json_content = json.dumps(
        [
            {"id": "1", "prompt": "First prompt", "image_path": ["./pic1.png"]},
            {"id": "2", "prompt": "Second prompt", "image_path": ["./pic2.png"]},
        ]
    )

    prompts = load_dataset_string(json_content)
    assert len(prompts) == 2, f"Expected 2 prompts, got {len(prompts)}"
    assert prompts[0]["prompt"] == "First prompt"
    assert prompts[1]["prompt"] == "Second prompt"
    print("✓ Test passed: JSON array with image_path fields")


def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("Testing image_path field support in dataset_loader")
    print("=" * 60 + "\n")

    tests = [
        test_image_field,
        test_image_path_field,
        test_image_path_list_format,
        test_image_url_field,
        test_image_priority,
        test_jsonl_string_with_image_path,
        test_json_array_with_image_path,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"✗ Test failed: {test_func.__name__} - {e}")
            failed += 1
        except Exception as e:
            print(f"✗ Test error: {test_func.__name__} - {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 60 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
