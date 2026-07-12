"""Investigator pure functions: safe JSON parsing and the structured diff."""

from investigator.investigate import (
    FALLBACK_VERDICT,
    find_divergence,
    latest_run_per_config,
    parse_verdict,
)


def test_parse_clean_json():
    verdict = parse_verdict(
        '{"root_cause": "stale KB", "confidence_pct": 95, '
        '"suggested_fix": "update kb-001", "supporting_evidence": ["e1"]}'
    )
    assert verdict["root_cause"] == "stale KB"
    assert verdict["confidence_pct"] == 95
    assert verdict["supporting_evidence"] == ["e1"]


def test_parse_fenced_json_with_preamble():
    text = 'Here is my analysis:\n```json\n{"root_cause": "x", "confidence_pct": "88", ' \
           '"suggested_fix": "y", "supporting_evidence": "single"}\n```'
    verdict = parse_verdict(text)
    assert verdict["confidence_pct"] == 88
    assert verdict["supporting_evidence"] == ["single"]


def test_parse_garbage_falls_back():
    assert parse_verdict("I cannot answer that.") == FALLBACK_VERDICT
    assert parse_verdict('{"root_cause": "x"}') == FALLBACK_VERDICT


def test_parse_clamps_confidence():
    verdict = parse_verdict(
        '{"root_cause": "x", "confidence_pct": 250, "suggested_fix": "y", '
        '"supporting_evidence": []}'
    )
    assert verdict["confidence_pct"] == 100


def test_latest_run_per_config_keeps_newest():
    runs = [
        {"config_id": "cf-1", "trace_id": "old"},
        {"config_id": "cf-1", "trace_id": "new"},
        {"config_id": "cf-5", "trace_id": "only"},
    ]
    kept = latest_run_per_config(runs)
    assert [r["trace_id"] for r in kept] == ["new", "only"]


def test_find_divergence_spots_refund_method():
    shared = {"tool": "search_kb", "input": "refund policy", "error": None}
    check = {"tool": "check_order", "input": "123", "error": None}
    configs = [
        {
            "config_id": "cf-1",
            "success": False,
            "tool_sequence": [shared, check, {"tool": "issue_refund", "input": '{"method": "refund_api_v1"}', "error": "decommissioned"}],
        },
        {
            "config_id": "cf-5",
            "success": True,
            "tool_sequence": [shared, check, {"tool": "issue_refund", "input": '{"method": "refund_api_v2"}', "error": None}],
        },
    ]
    divergence = find_divergence(configs)
    assert divergence["position"] == 2
    assert divergence["tool"] == "issue_refund"
    assert "refund_api_v2" in divergence["successful_config_did"]["input"]
    assert "refund_api_v1" in divergence["failing_config_did"]["input"]


def test_find_divergence_none_without_success():
    configs = [{"config_id": "cf-1", "success": False, "tool_sequence": []}]
    assert find_divergence(configs) is None
