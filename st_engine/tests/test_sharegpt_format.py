"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import json
import os
import tempfile
from typing import Any, Dict

import pytest

from utils.dataset_loader import (
    init_prompt_queue,
    init_prompt_queue_from_file,
    init_prompt_queue_from_string,
    load_dataset_file,
)


class TestShareGPTFormat:
    """Test ShareGPT format data loading."""

    def test_parse_sharegpt_json_array(self):
        """Test parsing ShareGPT JSON array format."""
        sharegpt_data = [
            {
                "id": "test_001",
                "image": "http://example.com/image1.jpg",
                "conversations": [
                    {"from": "human", "value": "你好"},
                    {"from": "gpt", "value": "你好！有什么我可以帮你的吗？"},
                    {"from": "human", "value": "描述这个图片"},
                    {"from": "gpt", "value": "这是一张美丽的图片。"},
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

        json_str = json.dumps(sharegpt_data, ensure_ascii=False)
        queue = init_prompt_queue_from_string(json_str)

        # Verify queue has 2 items
        assert queue.qsize() == 2

        # Check first item
        item1 = queue.get()
        assert item1["id"] == "test_001"
        assert item1["prompt"] == "你好"
        assert item1["image_url"] == "http://example.com/image1.jpg"

        # Check second item
        item2 = queue.get()
        assert item2["id"] == "test_002"
        assert item2["prompt"] == "今天天气怎么样？"
        assert item2.get("image_url", "") == ""

    def test_parse_sharegpt_with_local_image(self):
        """Test parsing ShareGPT format with local image path."""
        sharegpt_data = [
            {
                "id": "test_003",
                "image": "data/pic/test.jpg",
                "conversations": [{"from": "human", "value": "描述这个图片"}],
            }
        ]

        json_str = json.dumps(sharegpt_data, ensure_ascii=False)
        queue = init_prompt_queue_from_string(json_str)

        # Verify queue has 1 item
        assert queue.qsize() == 1

        item = queue.get()
        assert item["id"] == "test_003"
        assert item["prompt"] == "描述这个图片"
        # Image path should be processed (will fail if file doesn't exist, but that's expected)

    def test_parse_sharegpt_missing_id(self):
        """Test parsing ShareGPT format without id field."""
        sharegpt_data = [
            {"conversations": [{"from": "human", "value": "测试没有ID的情况"}]}
        ]

        json_str = json.dumps(sharegpt_data, ensure_ascii=False)
        queue = init_prompt_queue_from_string(json_str)

        assert queue.qsize() == 1
        item = queue.get()
        # Should use line number as ID
        assert item["id"] == 1
        assert item["prompt"] == "测试没有ID的情况"

    def test_parse_standard_jsonl_format(self):
        """Test parsing standard JSONL format still works."""
        jsonl_str = '{"id": "jsonl_001", "prompt": "这是标准JSONL格式"}\n{"id": "jsonl_002", "prompt": "第二条数据"}'
        queue = init_prompt_queue_from_string(jsonl_str)

        assert queue.qsize() == 2

        item1 = queue.get()
        assert item1["id"] == "jsonl_001"
        assert item1["prompt"] == "这是标准JSONL格式"

        item2 = queue.get()
        assert item2["id"] == "jsonl_002"
        assert item2["prompt"] == "第二条数据"

    def test_parse_image_as_url(self):
        """Test image field with URL value is correctly parsed as image_url."""
        sharegpt_data = [
            {
                "id": "test_004",
                "image": "http://example.com/test_image.jpg",
                "conversations": [{"from": "human", "value": "图片URL测试"}],
            }
        ]

        json_str = json.dumps(sharegpt_data, ensure_ascii=False)
        queue = init_prompt_queue_from_string(json_str)

        item = queue.get()
        # image field with URL should be set as image_url
        assert item["image_url"] == "http://example.com/test_image.jpg"
        assert item.get("image_base64", "") == ""

    def test_parse_with_prompt_priority(self):
        """Test prompt field takes priority over conversations field."""
        sharegpt_data = [
            {
                "id": "test_005",
                "prompt": "直接的prompt字段",
                "conversations": [{"from": "human", "value": "这个不应该被使用"}],
            }
        ]

        json_str = json.dumps(sharegpt_data, ensure_ascii=False)
        queue = init_prompt_queue_from_string(json_str)

        item = queue.get()
        # prompt field should take priority
        assert item["prompt"] == "直接的prompt字段"

    def test_load_json_array_from_file(self):
        """Test loading JSON array format from file."""
        sharegpt_data = [
            {
                "id": "file_001",
                "conversations": [{"from": "human", "value": "文件测试"}],
            }
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

    def test_load_jsonl_from_file(self):
        """Test loading JSONL format from file still works."""
        jsonl_content = '{"id": "jsonl_file_001", "prompt": "JSONL文件测试"}\n{"id": "jsonl_file_002", "prompt": "第二行"}'

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

    def test_parse_empty_prompt_skip(self):
        """Test that entries without valid prompt are skipped."""
        sharegpt_data = [
            {"id": "test_006", "conversations": []},  # Empty conversations
            {
                "id": "test_007",
                "conversations": [{"from": "gpt", "value": "只有GPT回复，没有human"}],
            },
            {
                "id": "test_008",
                "conversations": [{"from": "human", "value": "有效的prompt"}],
            },
        ]

        json_str = json.dumps(sharegpt_data, ensure_ascii=False)
        queue = init_prompt_queue_from_string(json_str)

        # Only the last one should be in queue
        assert queue.qsize() == 1
        item = queue.get()
        assert item["id"] == "test_008"
        assert item["prompt"] == "有效的prompt"

    def test_parse_user_as_human(self):
        """Test that 'user' is treated the same as 'human' in conversations."""
        sharegpt_data = [
            {
                "id": "test_009",
                "conversations": [{"from": "user", "value": "使用user代替human"}],
            }
        ]

        json_str = json.dumps(sharegpt_data, ensure_ascii=False)
        queue = init_prompt_queue_from_string(json_str)

        item = queue.get()
        assert item["prompt"] == "使用user代替human"

    def test_parse_messages_field(self):
        """Test parsing OpenAI messages format."""
        openai_data = [
            {
                "id": "test_010",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "从messages提取的prompt"},
                ],
            }
        ]

        json_str = json.dumps(openai_data, ensure_ascii=False)
        queue = init_prompt_queue_from_string(json_str)

        assert queue.qsize() == 1
        item = queue.get()
        assert item["prompt"] == "从messages提取的prompt"

    def test_prompt_priority_order(self):
        """Test prompt extraction priority: prompt > conversations > messages."""
        # Priority 1: prompt field takes precedence
        data1 = [
            {
                "id": "test_011",
                "prompt": "最高优先级prompt",
                "conversations": [{"from": "human", "value": "不应使用"}],
                "messages": [{"role": "user", "content": "也不应使用"}],
            }
        ]
        queue1 = init_prompt_queue_from_string(json.dumps(data1, ensure_ascii=False))
        item1 = queue1.get()
        assert item1["prompt"] == "最高优先级prompt"

        # Priority 2: conversations when no prompt
        data2 = [
            {
                "id": "test_012",
                "conversations": [{"from": "human", "value": "conversations优先级"}],
                "messages": [{"role": "user", "content": "不应使用"}],
            }
        ]
        queue2 = init_prompt_queue_from_string(json.dumps(data2, ensure_ascii=False))
        item2 = queue2.get()
        assert item2["prompt"] == "conversations优先级"

        # Priority 3: messages when no prompt or conversations
        data3 = [
            {
                "id": "test_013",
                "messages": [{"role": "user", "content": "messages优先级"}],
            }
        ]
        queue3 = init_prompt_queue_from_string(json.dumps(data3, ensure_ascii=False))
        item3 = queue3.get()
        assert item3["prompt"] == "messages优先级"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
