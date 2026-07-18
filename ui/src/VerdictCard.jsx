import React, { useEffect, useState } from "react";

export default function VerdictCard({ traceId, onVerdict }) {
  const [verdict, setVerdictState] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const setVerdict = (v) => {
    setVerdictState(v);
    if (onVerdict) onVerdict(v);
  };

  // Show a cached investigation instantly if one exists.
  useEffect(() => {
    setVerdict(null);
    setError(null);
    fetch(`/api/investigation/${traceId}`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setVerdict)
      .catch(() => {});
  }, [traceId]);

  const investigate = () => {
    setBusy(true);
    setError(null);
    fetch(`/api/investigate/${traceId}`, { method: "POST" })
      .then((r) => {
        if (!r.ok) throw new Error(`API ${r.status}`);
        return r.json();
      })
      .then(setVerdict)
      .catch((e) => setError(String(e)))
      .finally(() => setBusy(false));
  };

  return (
    <div className="panel verdict">
      <h2>Crash investigation</h2>
      {!verdict && !busy && (
        <div className="empty-state">
          <p className="empty-title">No investigation cached for this incident</p>
          <p className="empty-hint">
            One click runs the Crash Investigator: structured trace diff, a single
            Gemini call, and a root-cause verdict — itself fully traced in SigNoz.
          </p>
          <button className="investigate" onClick={investigate}>
            Investigate
          </button>
        </div>
      )}
      {busy && (
        <div className="empty-state">
          <span className="spinner" aria-label="investigating" />
          <p className="empty-hint">Investigating — diffing replays, one Gemini call…</p>
        </div>
      )}
      {error && (
        <div className="empty-state error-state">
          <p className="empty-title">Investigation failed</p>
          <p className="empty-hint">{error}</p>
        </div>
      )}
      {verdict && (
        <div className="card">
          <p className="root-cause">{verdict.root_cause}</p>
          <div className="confidence">
            <span className="conf-label">confidence</span>
            <span className="conf-track">
              <span
                className="conf-fill"
                style={{ width: `${verdict.confidence_pct}%` }}
              />
            </span>
            <span className="conf-pct">{verdict.confidence_pct}%</span>
          </div>
          <p>
            <strong>Suggested fix:</strong> {verdict.suggested_fix}
          </p>
          {verdict.supporting_evidence?.length > 0 && (
            <ul>
              {verdict.supporting_evidence.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
