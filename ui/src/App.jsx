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

      {loading && <p className="status">loading incident…</p>}
      {error && <p className="status error">{error}</p>}

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
              <p className="status">no successful fix-applied replay found</p>
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
