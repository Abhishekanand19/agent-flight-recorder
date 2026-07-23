"""Lightweight incident knowledge base — a local JSON store that learns from
completed investigations and surfaces similar past incidents.

No external database: one JSON file under .cache/. Every investigation is
recorded; when a new incident is investigated, the most similar prior
incident (by root-cause word overlap) is surfaced.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

KB_PATH = Path(__file__).resolve().parent.parent / ".cache" / "incident_kb.json"
SIMILARITY_THRESHOLD = 0.4

_STOPWORDS = {
    "the", "a", "an", "to", "for", "of", "and", "or", "was", "were", "is", "are",
    "it", "its", "in", "on", "with", "that", "this", "as", "by", "not", "no", "be",
    "been", "which", "using", "use", "used", "instead", "so", "same", "when", "then",
}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9_]+", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _similarity(a: str, b: str) -> float:
    """Jaccard overlap of significant words — simple, explainable, no deps."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _load() -> list[dict]:
    if not KB_PATH.exists():
        return []
    try:
        return json.loads(KB_PATH.read_text())
    except json.JSONDecodeError:
        return []


def _write(entries: list[dict]) -> None:
    KB_PATH.parent.mkdir(exist_ok=True)
    KB_PATH.write_text(json.dumps(entries, indent=1))


def find_similar(incident_id: str, root_cause: str) -> dict | None:
    """Best-matching prior incident (excluding this one) above the threshold."""
    best, best_score = None, 0.0
    for entry in _load():
        if entry["incident_id"] == incident_id:
            continue
        score = _similarity(root_cause, entry.get("root_cause", ""))
        if score > best_score:
            best, best_score = entry, score
    if best and best_score >= SIMILARITY_THRESHOLD:
        return {
            "incident_id": best["incident_id"],
            "match_pct": round(best_score * 100),
            "root_cause": best["root_cause"],
            "suggested_fix": best.get("suggested_fix", ""),
            "timestamp": best.get("timestamp"),
        }
    return None


def record(incident_id: str, verdict: dict, triggered_by: str = "manual") -> None:
    """Upsert a completed investigation into the knowledge base."""
    entries = [e for e in _load() if e["incident_id"] != incident_id]
    entries.append({
        "incident_id": incident_id,
        "root_cause": verdict.get("root_cause", ""),
        "supporting_evidence": verdict.get("supporting_evidence", []),
        "suggested_fix": verdict.get("suggested_fix", ""),
        "confidence_pct": verdict.get("confidence_pct", 0),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "triggered_by": triggered_by,
    })
    _write(entries)


def all_entries() -> list[dict]:
    return sorted(_load(), key=lambda e: e.get("timestamp", ""), reverse=True)


def backfill_from_cache() -> int:
    """Seed the KB from already-cached verdicts so history exists immediately."""
    count = 0
    for path in KB_PATH.parent.glob("verdict-*.json"):
        try:
            verdict = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        record(path.stem.replace("verdict-", ""), verdict, verdict.get("triggered_by", "manual"))
        count += 1
    return count
