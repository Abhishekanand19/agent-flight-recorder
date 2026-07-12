import React, { useEffect, useState } from "react";

export default function VerdictCard({ traceId }) {
  const [verdict, setVerdict] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

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
      {!verdict && (
        <button className="investigate" onClick={investigate} disabled={busy}>
          {busy ? "investigating… (one Gemini call)" : "Investigate"}
        </button>
      )}
      {error && <p className="status error">{error}</p>}
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
