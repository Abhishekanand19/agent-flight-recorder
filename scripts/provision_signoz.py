"""Provision the Agent Flight Recorder dashboard and alert rule into SigNoz.

Reads SIGNOZ_API_KEY from .env (create one in the SigNoz UI: Settings ->
API Keys, Admin role). Idempotent: skips anything that already exists by
title/name. Stdlib only.

Usage: python -m scripts.provision_signoz
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

SIGNOZ = "http://localhost:8080"
REPO = Path(__file__).resolve().parent.parent


def request(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{SIGNOZ}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "SIGNOZ-API-KEY": os.environ["SIGNOZ_API_KEY"],
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read() or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail}") from None


def provision_dashboard() -> None:
    data = json.loads((REPO / "signoz" / "dashboards" / "flight-recorder.json").read_text())
    existing = request("GET", "/api/v1/dashboards").get("data") or []
    for dash in existing:
        title = (dash.get("data") or {}).get("title")
        if title == data["title"]:
            ident = dash.get("id") or dash.get("uuid")
            request("PUT", f"/api/v1/dashboards/{ident}", data)
            print(f"dashboard updated in place: '{title}' (id {ident})")
            print(f"  open: {SIGNOZ}/dashboard/{ident}")
            return
    created = request("POST", "/api/v1/dashboards", data)
    ident = (created.get("data") or {}).get("id") or (created.get("data") or {}).get("uuid")
    print(f"dashboard created: '{data['title']}' (id {ident})")
    print(f"  open: {SIGNOZ}/dashboard/{ident}")


def provision_channel() -> None:
    """SigNoz requires at least one notification channel before a rule can be
    created. For the demo this is a webhook pointing at the local API."""
    existing = request("GET", "/api/v1/channels").get("data") or []
    if any(c.get("name") == "flight-recorder-demo" for c in existing):
        print("channel already exists: 'flight-recorder-demo'")
        return
    payload = {
        "name": "flight-recorder-demo",
        "webhook_configs": [
            {"url": "http://host.docker.internal:8000/api/alert-hook", "send_resolved": True}
        ],
    }
    request("POST", "/api/v1/channels", payload)
    print("channel created: 'flight-recorder-demo' (webhook -> local API)")


def provision_alert() -> None:
    rule = json.loads((REPO / "signoz" / "alerts" / "agent-failure-rate.json").read_text())
    existing = request("GET", "/api/v1/rules").get("data") or {}
    rules = existing.get("rules") if isinstance(existing, dict) else existing
    for r in rules or []:
        if r.get("alert") == rule["alert"]:
            print(f"alert rule already exists: '{rule['alert']}' (id {r.get('id')})")
            return
    created = request("POST", "/api/v1/rules", rule)
    print(f"alert rule created: '{rule['alert']}' -> {json.dumps(created)[:200]}")


def main() -> None:
    load_dotenv(REPO / ".env")
    if not os.environ.get("SIGNOZ_API_KEY"):
        sys.exit("SIGNOZ_API_KEY missing from .env (SigNoz UI -> Settings -> API Keys)")
    provision_dashboard()
    provision_channel()
    provision_alert()


if __name__ == "__main__":
    main()
