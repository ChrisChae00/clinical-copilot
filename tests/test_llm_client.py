import pytest
from llm.client import _normalize_messages, _parse_json_object


class TestParseJsonObject:
    def test_raw_json(self):
        assert _parse_json_object('{"a": 1}') == {"a": 1}

    def test_fenced_json(self):
        assert _parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}

    def test_bare_fence(self):
        assert _parse_json_object('```\n{"a": 1}\n```') == {"a": 1}

    def test_rejects_non_object(self):
        with pytest.raises(RuntimeError):
            _parse_json_object("[1, 2, 3]")

    def test_rejects_malformed_json(self):
        with pytest.raises(RuntimeError):
            _parse_json_object("{not json}")

    def test_rejects_malformed_fence(self):
        with pytest.raises(RuntimeError):
            _parse_json_object('```json\n{"a": 1}')

    def test_rejects_nested_fence(self):
        with pytest.raises(RuntimeError):
            _parse_json_object('```json\n```json\n{"a": 1}\n```\n```')

    def test_error_omits_content(self):
        # Error messages must not leak parsed content (can carry clinical data).
        with pytest.raises(RuntimeError) as exc_info:
            _parse_json_object("not json at all, definitely not")
        assert "not json at all" not in str(exc_info.value)


class TestNormalizeMessages:
    def test_valid_user_message(self):
        result = _normalize_messages([{"role": "user", "content": "hi"}])
        assert result == [{"role": "user", "content": "hi"}]

    def test_rejects_empty_list(self):
        with pytest.raises(ValueError):
            _normalize_messages([])

    def test_rejects_unsupported_role(self):
        with pytest.raises(ValueError):
            _normalize_messages([{"role": "bogus", "content": "hi"}])

    def test_rejects_non_string_content(self):
        with pytest.raises(ValueError):
            _normalize_messages([{"role": "user", "content": 123}])

    def test_tool_call_requires_assistant_role(self):
        with pytest.raises(ValueError):
            _normalize_messages(
                [{"role": "user", "content": "hi", "tool_calls": [{}]}]
            )

    def test_tool_message_requires_tool_name(self):
        with pytest.raises(ValueError):
            _normalize_messages([{"role": "tool", "content": "result"}])

    def test_valid_tool_message(self):
        result = _normalize_messages(
            [
                {
                    "role": "tool",
                    "content": "result",
                    "tool_name": "autofill",
                    "tool_call_id": "abc123",
                }
            ]
        )
        assert result[0]["tool_name"] == "autofill"
        assert result[0]["tool_call_id"] == "abc123"

    def test_images_only_valid_for_user(self):
        with pytest.raises(ValueError):
            _normalize_messages(
                [{"role": "assistant", "content": "hi", "images": ["b64"]}]
            )
