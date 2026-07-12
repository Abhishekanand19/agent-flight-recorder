"""The demo failure must be deterministic: stale KB entry (kb-001) sends the
agent to refund_api_v1, which issue_refund always rejects."""

import pytest

from agent import kb
from agent.tools import do_check_order, do_issue_refund, do_search_kb


def test_kb_returns_stale_refund_policy():
    hits = kb.search("refund order")
    assert any(e["id"] == "kb-001" for e in hits)
    stale = next(e for e in hits if e["id"] == "kb-001")
    assert "refund_api_v1" in stale["body"]


def test_order_123_exists_and_is_delivered():
    assert '"delivered"' in do_check_order("#123")


def test_refund_via_stale_method_always_fails():
    with pytest.raises(ValueError, match="decommissioned"):
        do_issue_refund("123", "refund_api_v1")


def test_refund_via_current_method_succeeds():
    assert "Refund of $89.00 issued" in do_issue_refund("123", "refund_api_v2")
