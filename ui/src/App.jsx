import React, { useEffect, useState } from "react";
import Waterfall from "./Waterfall.jsx";
import Matrix from "./Matrix.jsx";
import VerdictCard from "./VerdictCard.jsx";

const DEFAULT_TRACE = "f809ade2ecee6aba1c2669047f8a59ce";

export default function App() {
  const [traceId, setTraceId] = useState(DEFAULT_TRACE);
  const [input, setInput] = useState(DEFAULT_TRACE);
  const [incident, setIncident] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch(`/api/incident/${traceId}`)
      .then((r) => {
        if (!r.ok) throw new Error(`API ${r.status}`);
        return r.json();
      })
      .then(setIncident)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [traceId]);

  return (
    <div className="app">
      <header>
        <h1>
          Agent Flight Recorder <span className="sub">incident diff</span>
        </h1>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setTraceId(input.trim());
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            size={36}
            spellCheck={false}
          />
          <button type="submit">Load</button>
        </form>
      </header>

      {loading && (
        <div className="waterfalls" aria-label="loading">
          <div className="waterfall skeleton-panel">
            <div className="skeleton skeleton-title" />
            {[...Array(6)].map((_, i) => (
              <div className="skeleton skeleton-row" key={i} />
            ))}
          </div>
          <div className="waterfall skeleton-panel">
            <div className="skeleton skeleton-title" />
            {[...Array(6)].map((_, i) => (
              <div className="skeleton skeleton-row" key={i} />
            ))}
          </div>
        </div>
      )}
      {error && (
        <div className="empty-state error-state">
          <p className="empty-title">Couldn't load this incident</p>
          <p className="empty-hint">{error} — is the API running on port 8000?</p>
        </div>
      )}

      {incident && (
        <>
          <section className="waterfalls">
            <Waterfall
              title={`original — FAIL (${incident.original.trace_id.slice(0, 8)}…)`}
              spans={incident.original.spans}
              divergence={incident.divergence}
              failSide
            />
            {incident.fix ? (
              <Waterfall
                title={`${incident.fix.config_id} fix applied — PASS (${incident.fix.trace_id.slice(0, 8)}…)`}
                spans={incident.fix.spans}
                divergence={incident.divergence}
              />
            ) : (
              <div className="waterfall empty-state">
                <p className="empty-title">No validated fix yet</p>
                <p className="empty-hint">
                  Run the replay engine with the fix config to give this incident
                  its passing counterpart: python -m replay.engine --trace-id …
                  --config cf-5
                </p>
              </div>
            )}
          </section>

          <section className="bottom">
            <Matrix matrix={incident.matrix} />
            <VerdictCard traceId={traceId} />
          </section>
        </>
      )}
    </div>
  );
}
