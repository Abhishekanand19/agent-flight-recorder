import React, { useEffect, useState } from "react";
import Home from "./Home.jsx";
import Timeline from "./Timeline.jsx";
import Waterfall from "./Waterfall.jsx";
import Matrix from "./Matrix.jsx";
import VerdictCard from "./VerdictCard.jsx";
import DeltaImpact from "./DeltaImpact.jsx";
import ActionCenter from "./ActionCenter.jsx";

export default function App() {
  const [traceId, setTraceId] = useState(null); // null = Operations Center
  const [input, setInput] = useState("");
  const [incident, setIncident] = useState(null);
  const [verdict, setVerdict] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!traceId) {
      setIncident(null);
      setVerdict(null);
      return;
    }
    setLoading(true);
    setError(null);
    setIncident(null);
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
        <h1 className="brand" onClick={() => setTraceId(null)}>
          Agent Flight Recorder{" "}
          <span className="sub">{traceId ? "incident diff" : "operations center"}</span>
        </h1>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (input.trim()) setTraceId(input.trim());
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            size={36}
            spellCheck={false}
            placeholder="open a trace id…"
          />
          <button type="submit">Load</button>
        </form>
      </header>

      {!traceId && <Home onOpen={(id) => setTraceId(id)} />}

      {traceId && (
        <>
          <button className="back-link" onClick={() => setTraceId(null)}>
            ← Operations Center
          </button>

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
              <Timeline incident={incident} verdict={verdict} />

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

              <DeltaImpact impact={incident.impact} />

              <section className="bottom">
                <Matrix matrix={incident.matrix} />
                <VerdictCard
                  traceId={traceId}
                  onVerdict={setVerdict}
                  breakdown={incident.confidence_breakdown}
                />
              </section>

              <ActionCenter incident={incident} verdict={verdict} />
            </>
          )}
        </>
      )}
    </div>
  );
}
