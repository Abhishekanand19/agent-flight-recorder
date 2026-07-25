"""Reset Demo Mode to a clean first-launch state.

Produces demo_data/catalog.json: an ordered set of a few REAL captured
incidents that start HIDDEN. Demo Mode reveals them one at a time as the user
clicks "Simulate Crash", so the Operations Center opens empty and the first
click generates the first incident. Keeps only the seed incident/verdict
detail files (for drill-in) and prunes the rest.

Usage: python -m scripts.reset_demo_data
"""

import json
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "demo_data"
N_SEEDS = 3

# Representative real-scale contribution of one refund incident (matches the
# actual agent behaviour: one failed issue_refund, KB searches, one check).
CONTRIBUTION = {
    "tools": {
        "issue_refund": {"failures": 1, "calls": 1},
        "search_kb": {"failures": 0, "calls": 2},
        "check_order": {"failures": 0, "calls": 1},
    },
    "replay": {
        "count": 2, "successes": 1, "tokens": 4724, "cost_usd": 0.0033,
        "avg_duration_ms": 3900.0, "avg_latency_ms": 340.0,
        "model": "llama-3.3-70b-versatile",
    },
}


def main() -> None:
    rows = json.loads((D / "incidents.json").read_text())["incidents"]
    seed_ids = [
        r["trace_id"] for r in rows
        if (D / f"verdict-{r['trace_id']}.json").exists()
        and r.get("fix_validated") and r.get("root_cause")
    ][:N_SEEDS]

    seeds = [{"trace_id": tid,
              "row": next(r for r in rows if r["trace_id"] == tid),
              "contribution": CONTRIBUTION}
             for tid in seed_ids]
    (D / "catalog.json").write_text(json.dumps({"seeds": seeds}, indent=1))

    keep = {"catalog.json"}
    keep |= {f"incident-{t}.json" for t in seed_ids}
    keep |= {f"verdict-{t}.json" for t in seed_ids}
    removed = 0
    for f in D.glob("*.json"):
        if f.name not in keep:
            f.unlink()
            removed += 1

    print(f"catalog seeds ({len(seed_ids)}): {seed_ids}")
    print(f"pruned {removed} snapshot files; kept {len(keep)} (catalog + {N_SEEDS} incident/verdict pairs)")


if __name__ == "__main__":
    main()
