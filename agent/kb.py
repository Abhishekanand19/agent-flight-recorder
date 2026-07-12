"""Tiny in-memory knowledge base for the support agent.

Entry kb-001 is deliberately STALE: it points refunds at refund_api_v1,
which has been decommissioned. This is what makes the demo failure for
order #123 deterministic (see agent/tools.py: issue_refund).
"""

ENTRIES = [
    {
        "id": "kb-001",
        "title": "Refund policy",
        "body": (
            "Refunds for delivered orders must be issued through refund_api_v1 "
            "using the order id. No approval token is required. "
            "Last reviewed: 2025-11-02."
        ),
    },
    {
        "id": "kb-002",
        "title": "Shipping policy",
        "body": (
            "Standard shipping takes 3-5 business days. Expedited shipping is "
            "available at checkout for a flat fee."
        ),
    },
    {
        "id": "kb-003",
        "title": "Warranty claims",
        "body": (
            "Hardware products carry a 12-month warranty. Warranty claims are "
            "handled by the warranty team, not by support agents."
        ),
    },
]


def search(query: str) -> list[dict]:
    """Return entries whose title or body shares a word with the query."""
    words = {w.lower().strip("?.,!") for w in query.split()}
    hits = []
    for entry in ENTRIES:
        text = (entry["title"] + " " + entry["body"]).lower()
        if any(w and w in text for w in words):
            hits.append(entry)
    return hits
