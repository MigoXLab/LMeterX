"""
Tests for dataset loading and prompt extraction.
"""

import json
import os
import tempfile

import pytest

from utils.dataset_loader import (
    init_prompt_queue_from_string,
    load_dataset_file,
    load_dataset_string,
    parse_data_line,
)


@pytest.fixture
def temp_image_file():
    """Create a temporary image file for testing."""
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".png", delete=False) as f:
        png_data = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        f.write(png_data)
        temp_path = f.name

    yield temp_path

    try:
        os.unlink(temp_path)
    except Exception:
        pass


def test_parse_sharegpt_json_array():
    sharegpt_data = [
        {
            "id": "test_001",
            "image": "http://example.com/image1.jpg",
            "conversations": [
                {"from": "human", "value": "你好"},
                {"from": "gpt", "value": "你好！有什么我可以帮你的吗？"},
            ],
        },
        {
            "id": "test_002",
            "conversations": [
                {"from": "human", "value": "今天天气怎么样？"},
                {"from": "gpt", "value": "今天天气很好。"},
            ],
        },
    ]

    queue = init_prompt_queue_from_string(json.dumps(sharegpt_data, ensure_ascii=False))

    assert queue.qsize() == 2
    item1 = queue.get()
    assert item1["id"] == "test_001"
    assert item1["prompt"] == "你好"
    assert item1["image_url"] == "http://example.com/image1.jpg"

    item2 = queue.get()
    assert item2["id"] == "test_002"
    assert item2["prompt"] == "今天天气怎么样？"
    assert item2.get("image_url", "") == ""


def test_parse_sharegpt_missing_id():
    sharegpt_data = [{"conversations": [{"from": "human", "value": "测试没有ID"}]}]
    queue = init_prompt_queue_from_string(json.dumps(sharegpt_data, ensure_ascii=False))

    item = queue.get()
    assert item["id"] == 1
    assert item["prompt"] == "测试没有ID"


def test_prompt_priority_order():
    data1 = [
        {
            "id": "test_011",
            "prompt": "最高优先级prompt",
            "conversations": [{"from": "human", "value": "不应使用"}],
            "messages": [{"role": "user", "content": "也不应使用"}],
        }
    ]
    queue1 = init_prompt_queue_from_string(json.dumps(data1, ensure_ascii=False))
    assert queue1.get()["prompt"] == "最高优先级prompt"

    data2 = [
        {
            "id": "test_012",
            "conversations": [{"from": "human", "value": "conversations优先级"}],
            "messages": [{"role": "user", "content": "不应使用"}],
        }
    ]
    queue2 = init_prompt_queue_from_string(json.dumps(data2, ensure_ascii=False))
    assert queue2.get()["prompt"] == "conversations优先级"

    data3 = [
        {"id": "test_013", "messages": [{"role": "user", "content": "messages优先级"}]}
    ]
    queue3 = init_prompt_queue_from_string(json.dumps(data3, ensure_ascii=False))
    assert queue3.get()["prompt"] == "messages优先级"


def test_parse_messages_field():
    openai_data = [
        {
            "id": "test_010",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "从messages提取的prompt"},
            ],
        }
    ]
    queue = init_prompt_queue_from_string(json.dumps(openai_data, ensure_ascii=False))
    assert queue.qsize() == 1
    assert queue.get()["prompt"] == "从messages提取的prompt"


def test_parse_image_as_url():
    line = json.dumps(
        {
            "id": "test_004",
            "image": "http://example.com/test_image.jpg",
            "conversations": [{"from": "human", "value": "图片URL测试"}],
        }
    )
    result = parse_data_line(line, 1)
    assert result is not None
    assert result.image_url == "http://example.com/test_image.jpg"
    assert result.image_base64 == ""


def test_parse_image_path_array():
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
    assert result.prompt == "这个图形的美学价值如何？"
    assert result.image_url == ""


def test_parse_absolute_path_image(temp_image_file):
    line = json.dumps(
        {"id": "test3", "prompt": "Test prompt", "image_path": temp_image_file}
    )
    result = parse_data_line(line, 1)
    assert result is not None
    assert result.prompt == "Test prompt"
    assert result.image_base64 != ""
    assert result.image_url == ""


def test_load_json_array_from_file():
    sharegpt_data = [
        {"id": "file_001", "conversations": [{"from": "human", "value": "文件测试"}]}
    ]
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(sharegpt_data, f, ensure_ascii=False)
        temp_file = f.name

    try:
        data = load_dataset_file(temp_file)
        assert len(data) == 1
        assert data[0]["id"] == "file_001"
        assert data[0]["prompt"] == "文件测试"
    finally:
        os.unlink(temp_file)


def test_load_jsonl_from_file():
    jsonl_content = (
        '{"id": "jsonl_file_001", "prompt": "JSONL文件测试"}\n'
        '{"id": "jsonl_file_002", "prompt": "第二行"}'
    )
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as f:
        f.write(jsonl_content)
        temp_file = f.name

    try:
        data = load_dataset_file(temp_file)
        assert len(data) == 2
        assert data[0]["id"] == "jsonl_file_001"
        assert data[1]["id"] == "jsonl_file_002"
    finally:
        os.unlink(temp_file)


def test_load_dataset_string_skips_empty_prompts():
    sharegpt_data = [
        {"id": "test_006", "conversations": []},
        {"id": "test_007", "conversations": [{"from": "gpt", "value": "只有GPT"}]},
        {
            "id": "test_008",
            "conversations": [{"from": "human", "value": "有效的prompt"}],
        },
    ]
    prompts = load_dataset_string(json.dumps(sharegpt_data, ensure_ascii=False))
    assert len(prompts) == 1
    assert prompts[0]["id"] == "test_008"
    assert prompts[0]["prompt"] == "有效的prompt"
