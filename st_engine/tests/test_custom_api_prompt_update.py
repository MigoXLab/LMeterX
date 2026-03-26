"""
Test custom API prompt update functionality
"""

import json
import unittest
from unittest.mock import Mock

# Import core components without locust dependencies
from engine.core import ConfigManager, GlobalConfig


class TestCustomApiPromptUpdate(unittest.TestCase):
    """Test custom API prompt update functionality"""

    def setUp(self):
        """Set up test environment"""
        # Create global configuration instance
        self.global_config = GlobalConfig()
        self.global_config.task_id = "test_task"
        self.global_config.api_path = "/custom/api"
        self.global_config.request_payload = json.dumps(
            {"model": "test-model", "input": "original_prompt", "temperature": 0.7}
        )
        self.global_config.field_mapping = json.dumps(
            {
                "prompt": "input",
                "content": "output.text",
                "stream_prefix": "data:",
                "stop_flag": "[DONE]",
            }
        )

        # Create mock request handler
        self.request_handler = Mock()
        self.task_logger = Mock()

    def test_field_mapping_parsing(self):
        """Test field mapping parsing functionality"""
        field_mapping = ConfigManager.parse_field_mapping(
            self.global_config.field_mapping
        )

        # Verify field mapping is parsed correctly
        self.assertEqual(field_mapping.prompt, "input")
        self.assertEqual(field_mapping.content, "output.text")
        self.assertEqual(field_mapping.stream_prefix, "data:")
        self.assertEqual(field_mapping.stop_flag, "[DONE]")

    def test_empty_request_payload_handling(self):
        """Test handling of empty request_payload"""
        from engine.request_processor import PayloadBuilder

        # Test with empty request_payload
        config_with_empty_payload = GlobalConfig()
        config_with_empty_payload.task_id = "test_task"
        config_with_empty_payload.api_path = "/custom/api"
        config_with_empty_payload.request_payload = ""  # Empty payload
        config_with_empty_payload.model_name = "test-model"
        config_with_empty_payload.stream_mode = True

        handler = PayloadBuilder(config_with_empty_payload, self.task_logger)
        result, user_prompt = handler.prepare_request_kwargs(None)

        # Should generate default payload and not return None
        self.assertIsNotNone(result)
        self.assertIn("json", result)

        payload = result["json"]
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(payload["stream"], True)
        self.assertIn("messages", payload)
        self.assertEqual(len(payload["messages"]), 1)
        self.assertEqual(payload["messages"][0]["role"], "user")
        self.assertEqual(payload["messages"][0]["content"], "Hi")

    def test_none_request_payload_handling(self):
        """Test handling of None request_payload"""
        from request_processor import PayloadBuilder

        # Test with None request_payload
        config_with_none_payload = GlobalConfig()
        config_with_none_payload.task_id = "test_task"
        config_with_none_payload.api_path = "/custom/api"
        config_with_none_payload.request_payload = None  # None payload
        config_with_none_payload.model_name = "another-model"
        config_with_none_payload.stream_mode = False

        handler = PayloadBuilder(config_with_none_payload, self.task_logger)
        result, user_prompt = handler.prepare_request_kwargs(None)

        # Should generate default payload and not return None
        self.assertIsNotNone(result)
        self.assertIn("json", result)

        payload = result["json"]
        self.assertEqual(payload["model"], "another-model")
        self.assertEqual(payload["stream"], False)
        self.assertIn("messages", payload)

    def test_field_mapping_with_nested_field(self):
        """Test field mapping with nested field configuration"""
        # Set nested field mapping
        nested_field_mapping = json.dumps({"prompt": "messages.0.content"})
        field_mapping = ConfigManager.parse_field_mapping(nested_field_mapping)

        # Verify nested field mapping is parsed correctly
        self.assertEqual(field_mapping.prompt, "messages.0.content")

    def test_field_mapping_without_configuration(self):
        """Test field mapping parsing without configuration"""
        # Test empty field mapping
        field_mapping = ConfigManager.parse_field_mapping("")

        # Verify default values are used
        self.assertEqual(field_mapping.prompt, "")
        self.assertEqual(field_mapping.stream_prefix, "data:")
        self.assertEqual(field_mapping.data_format, "json")
        self.assertEqual(field_mapping.stop_flag, "[DONE]")

    def test_headers_parsing(self):
        """Test headers parsing functionality"""
        headers_json = '{"Authorization": "Bearer token123", "Custom-Header": "value"}'
        headers = ConfigManager.parse_headers(headers_json, self.task_logger)

        # Verify headers are parsed correctly
        self.assertEqual(headers["Authorization"], "Bearer token123")
        self.assertEqual(headers["Custom-Header"], "value")

    def _set_field_value(self, data, path, value):
        """Helper method to set field value in nested dictionary using dot-separated path."""
        if not path or not isinstance(data, dict):
            return

        try:
            keys = path.split(".")
            current = data

            # Navigate to the parent of the target field
            for key in keys[:-1]:
                if key.isdigit():
                    if isinstance(current, list):
                        current = current[int(key)]
                    else:
                        return
                elif isinstance(current, list) and current:
                    if isinstance(current[0], dict):
                        current = current[0].setdefault(key, {})
                    else:
                        return
                elif isinstance(current, dict):
                    current = current.setdefault(key, {})
                else:
                    return

            # Set the final field value
            final_key = keys[-1]
            if final_key.isdigit() and isinstance(current, list):
                current[int(final_key)] = value
            elif isinstance(current, dict):
                current[final_key] = value
        except (IndexError, ValueError, KeyError):
            pass

    def test_set_field_value_simple_field(self):
        """Test setting simple field value"""
        data = {"field1": "value1", "field2": "value2"}
        self._set_field_value(data, "field1", "new_value")
        self.assertEqual(data["field1"], "new_value")

    def test_set_field_value_nested_field(self):
        """Test setting nested field value"""
        data = {"level1": {"level2": {"target": "old_value"}}}
        self._set_field_value(data, "level1.level2.target", "new_value")
        self.assertEqual(data["level1"]["level2"]["target"], "new_value")

    def test_set_field_value_array_index(self):
        """Test setting array index field value"""
        data = {"messages": [{"content": "old_content"}, {"content": "other_content"}]}
        self._set_field_value(data, "messages.0.content", "new_content")
        self.assertEqual(data["messages"][0]["content"], "new_content")
        # Verify other elements are not modified
        self.assertEqual(data["messages"][1]["content"], "other_content")

    def test_cookies_parsing(self):
        """Test cookies parsing functionality"""
        cookies_json = '{"session_id": "abc123", "auth_token": "xyz789"}'
        cookies = ConfigManager.parse_cookies(cookies_json, self.task_logger)

        # Verify cookies are parsed correctly
        self.assertEqual(cookies["session_id"], "abc123")
        self.assertEqual(cookies["auth_token"], "xyz789")


if __name__ == "__main__":
    unittest.main()
