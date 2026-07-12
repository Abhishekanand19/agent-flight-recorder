"""replay.success classification: correct order acted on, wrong refund avoided."""

from langchain_core.messages import AIMessage, HumanMessage

from replay.engine import classify_success


def _ai(tool_calls):
    return AIMessage(content="", tool_calls=tool_calls)


def test_refund_via_v2_on_correct_order_is_success():
    messages = [
        HumanMessage("Please refund order #123."),
        _ai([{"name": "check_order", "args": {"order_id": "123"}, "id": "1"}]),
        _ai([{"name": "issue_refund", "args": {"order_id": "123", "method": "refund_api_v2"}, "id": "2"}]),
    ]
    assert classify_success(messages) is True


def test_decommissioned_method_is_failure():
    messages = [
        _ai([{"name": "issue_refund", "args": {"order_id": "123", "method": "refund_api_v1"}, "id": "1"}]),
    ]
    assert classify_success(messages) is False


def test_wrong_order_is_failure():
    messages = [
        _ai([{"name": "check_order", "args": {"order_id": "456"}, "id": "1"}]),
    ]
    assert classify_success(messages) is False


def test_never_touching_the_order_is_failure():
    messages = [
        _ai([{"name": "search_kb", "args": {"query": "refund policy"}, "id": "1"}]),
    ]
    assert classify_success(messages) is False
