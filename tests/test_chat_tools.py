from routes.chat import (
    _actions_from_tool_calls,
    _normalize_tool_arguments,
    _normalize_tool_calls,
)


def _raw_call(name, arguments):
    return {"function": {"name": name, "arguments": arguments}}


class TestNormalizeToolCalls:
    def test_valid_call(self):
        result = _normalize_tool_calls(
            [_raw_call("autofill", {"instructions": "fill in the visit date"})]
        )
        assert len(result) == 1
        assert result[0]["function"]["name"] == "autofill"
        assert result[0]["function"]["arguments"] == {
            "instructions": "fill in the visit date"
        }

    def test_drops_unsupported_tool_name(self):
        assert _normalize_tool_calls([_raw_call("delete_everything", {})]) == []

    def test_drops_call_missing_required_argument(self):
        # autofill requires "instructions"
        assert _normalize_tool_calls([_raw_call("autofill", {})]) == []

    def test_drops_call_with_malformed_json_string_arguments(self):
        assert _normalize_tool_calls([_raw_call("autofill", "{not json}")]) == []

    def test_accepts_arguments_as_json_string(self):
        result = _normalize_tool_calls(
            [_raw_call("autofill", '{"instructions": "fill it"}')]
        )
        assert len(result) == 1

    def test_strips_unexpected_arguments(self):
        result = _normalize_tool_calls(
            [_raw_call("referral", {"instructions": "cardiology", "bogus": "x"})]
        )
        assert "bogus" not in result[0]["function"]["arguments"]

    def test_ignores_non_list_input(self):
        assert _normalize_tool_calls(None) == []
        assert _normalize_tool_calls("not a list") == []

    def test_ignores_non_dict_entries(self):
        assert _normalize_tool_calls(["not a dict"]) == []

    def test_referral_has_no_required_arguments(self):
        result = _normalize_tool_calls([_raw_call("referral", {})])
        assert len(result) == 1


class TestNormalizeToolArguments:
    def test_dict_passthrough(self):
        assert _normalize_tool_arguments({"a": 1}, tool_name="autofill") == {"a": 1}

    def test_valid_json_string(self):
        assert _normalize_tool_arguments('{"a": 1}', tool_name="autofill") == {"a": 1}

    def test_malformed_json_string_returns_empty(self):
        assert _normalize_tool_arguments("{not json}", tool_name="autofill") == {}

    def test_non_object_json_returns_empty(self):
        assert _normalize_tool_arguments("[1, 2]", tool_name="autofill") == {}

    def test_unsupported_type_returns_empty(self):
        assert _normalize_tool_arguments(42, tool_name="autofill") == {}


class TestActionsFromToolCalls:
    def test_dedupes_repeated_tool_names(self):
        calls = [
            {"function": {"name": "autofill", "arguments": {}}},
            {"function": {"name": "autofill", "arguments": {}}},
        ]
        assert _actions_from_tool_calls(calls) == ["autofill"]

    def test_preserves_order_of_first_occurrence(self):
        calls = [
            {"function": {"name": "referral", "arguments": {}}},
            {"function": {"name": "autofill", "arguments": {}}},
        ]
        assert _actions_from_tool_calls(calls) == ["referral", "autofill"]
