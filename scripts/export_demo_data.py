"""Capture real Flight Recorder data into demo_data/ snapshots.

Runs the live API endpoint functions against the local SigNoz/ClickHouse and
saves their exact JSON responses. Demo Mode (DEMO_MODE=1) then serves these
snapshots verbatim, so the deployed backend shows real captured incidents,
replays, investigations, dashboards, logs and knowledge base without needing
SigNoz online.

Usage (with the local stack up, DEMO_MODE unset): python -m scripts.export_demo_data
"""

import json
from pathlib import Path

from api import main as api

OUT = Path(__file__).resolve().parent.parent / "demo_data"
OUT.mkdir(exist_ok=True)


def dump(name: str, obj) -> None:
    (OUT / name).write_text(json.dumps(obj, indent=1, default=str))
    print(f"  wrote {name}")


def main() -> None:
    incidents = api.list_incidents()
    dump("incidents.json", incidents)
    dump("stats.json", api.get_stats())
    dump("failing-tools.json", api.failing_tools())
    dump("replay-cost.json", api.replay_cost())
    dump("knowledge-base.json", api.get_knowledge_base())

    details = 0
    for inc in incidents["incidents"]:
        tid = inc["trace_id"]
        try:
            dump(f"incident-{tid}.json", api.get_incident(tid))
            details += 1
        except Exception as exc:  # noqa: BLE001 - best effort snapshot
            print(f"  skip incident {tid}: {exc}")
        try:
            dump(f"verdict-{tid}.json", api.get_investigation(tid))
        except Exception:
            pass  # no cached verdict for this incident

    manifest = {
        "incidents": [i["trace_id"] for i in incidents["incidents"]],
        "primary": next((i["trace_id"] for i in incidents["incidents"]
                         if i.get("fix_validated") and i.get("root_cause")), None),
        "detail_count": details,
    }
    dump("manifest.json", manifest)
    print(f"exported {details} incident details; primary = {manifest['primary']}")


if __name__ == "__main__":
    main()
