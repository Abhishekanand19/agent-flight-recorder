import React, { useCallback, useEffect, useRef, useState } from "react";

function age(seconds) {
  if (seconds == null) return "—";
  if (seconds < 90) return `${Math.round(seconds)} s ago`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} min ago`;
  return `${(seconds / 3600).toFixed(1)} h ago`;
}

function duration(seconds) {
  if (seconds == null) return "—";
  if (seconds < 120) return `${Math.round(seconds)} sec`;
  if (seconds < 7200) return `${Math.round(seconds / 60)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

function Tile({ label, value, sub }) {
  return (
    <div className="tile">
      <div className="tile-value">{value}</div>
      <div className="tile-label">{label}</div>
      {sub && <div className="tile-sub">{sub}</div>}
    </div>
  );
}

function ReplayCost({ cost }) {
  if (!cost) return null;
  const money = (v) => `$${(v || 0).toFixed(v < 0.01 ? 6 : 4)}`;
  const ms = (v) => (v == null ? "—" : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${Math.round(v)} ms`);
  return (
    <section className="panel replay-cost" style={{ marginTop: 16 }}>
      <h2>Replay cost &amp; resources</h2>
      {cost.replay_count === 0 ? (
        <div className="empty-state">
          <p className="empty-title">No replay cost data yet</p>
          <p className="empty-hint">Run a replay (or click Simulate Crash) to populate cost metrics.</p>
        </div>
      ) : (
        <>
          <div className="cost-cells">
            <div className="cost-cell">
              <div className="cost-value">{money(cost.total_cost_usd)}</div>
              <div className="cost-label">total est. cost · {cost.replay_count} replays</div>
            </div>
            <div className="cost-cell">
              <div className="cost-value">{Math.round(cost.avg_tokens).toLocaleString()}</div>
              <div className="cost-label">avg tokens / replay</div>
            </div>
            <div className="cost-cell">
              <div className="cost-value">{ms(cost.avg_duration_ms)}</div>
              <div className="cost-label">avg execution time</div>
            </div>
            <div className="cost-cell">
              <div className="cost-value">{ms(cost.avg_latency_ms)}</div>
              <div className="cost-label">avg LLM latency</div>
            </div>
          </div>
          {cost.by_model.length > 0 && (
            <table className="cost-table">
              <thead>
                <tr><th>model</th><th>replays</th><th>tokens</th><th>avg exec</th><th>est. cost</th></tr>
              </thead>
              <tbody>
                {cost.by_model.map((m) => (
                  <tr key={m.model}>
                    <td className="mono">{m.model}</td>
                    <td>{m.replays}</td>
                    <td>{m.tokens.toLocaleString()}</td>
                    <td>{ms(m.avg_duration_ms)}</td>
                    <td>{money(m.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
  );
}

function FailingTools({ tools }) {
  const withFailures = (tools || []).filter((t) => t.failures > 0);
  const maxShare = Math.max(...withFailures.map((t) => t.share), 1e-9);
  return (
    <section className="panel" style={{ marginTop: 16 }}>
      <h2>Top failing tools</h2>
      {withFailures.length === 0 ? (
        <div className="empty-state">
          <p className="empty-title">No tool failures recorded</p>
          <p className="empty-hint">Tool failures appear here the moment an incident occurs.</p>
        </div>
      ) : (
        <div className="tool-bars">
          {withFailures.map((t) => (
            <div className="tool-row" key={t.tool}>
              <span className="tool-name mono">{t.tool}</span>
              <span className="tool-track">
                <span className="tool-bar" style={{ width: `${(t.share / maxShare) * 100}%` }} />
              </span>
              <span className="tool-metric">
                <strong>{t.failures}</strong> fail
                <span className="tool-rate">{Math.round(t.failure_rate * 100)}% of {t.calls} calls</span>
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

const PIPELINE_STAGES = [
  { key: "detected", icon: "🚨", label: "Crash detected" },
  { key: "replaying", icon: "⚙", label: "Replaying counterfactuals…" },
  { key: "investigating", icon: "🔍", label: "Investigating…" },
  { key: "done", icon: "✅", label: "Root cause found" },
];

function ProgressStrip({ active }) {
  if (!active || active.stage === "idle") return null;
  const reached =
    { generating: 0, replaying: 1, investigating: 2, done: 3, failed: 2 }[active.stage] ?? 0;
  return (
    <section className={`progress-strip panel ${active.stage === "done" ? "strip-done" : ""}`}>
      <span className="strip-title">
        Live investigation {active.trace_id ? `· ${active.trace_id.slice(0, 8)}…` : ""}
      </span>
      <div className="strip-stages">
        {PIPELINE_STAGES.map((s, i) => (
          <span key={s.key} className={`strip-stage ${i <= reached ? "lit" : ""} ${i === reached && active.stage !== "done" ? "current" : ""}`}>
            {s.icon} {s.label}
          </span>
        ))}
      </div>
      {active.stage === "failed" && <span className="strip-error">failed: {active.error}</span>}
    </section>
  );
}

export default function Home({ onOpen }) {
  const [stats, setStats] = useState(null);
  const [incidents, setIncidents] = useState(null);
  const [tools, setTools] = useState(null);
  const [cost, setCost] = useState(null);
  const [active, setActive] = useState(null);
  const [error, setError] = useState(null);
  const lastStage = useRef(null);

  const loadAll = useCallback(
    () =>
      Promise.all([
        fetch("/api/stats").then((r) => r.json()),
        fetch("/api/incidents").then((r) => r.json()),
        fetch("/api/failing-tools").then((r) => r.json()),
        fetch("/api/replay-cost").then((r) => r.json()),
      ])
        .then(([s, i, t, c]) => {
          setStats(s);
          setIncidents(i.incidents);
          setTools(t.tools);
          setCost(c);
          setError(null);
        })
        .catch((e) => setError(String(e))),
    []
  );

  useEffect(() => {
    loadAll();
    const slow = setInterval(loadAll, 15000); // incidents appear by themselves
    const fast = setInterval(
      () => fetch("/api/investigations/active").then((r) => r.json()).then(setActive).catch(() => {}),
      3000
    );
    return () => {
      clearInterval(slow);
      clearInterval(fast);
    };
  }, [loadAll]);

  // The instant the pipeline finishes, pull the new incident in — no refresh.
  useEffect(() => {
    const stage = active?.stage;
    if (stage && stage !== lastStage.current) {
      if (stage === "done" || stage === "failed") loadAll();
      lastStage.current = stage;
    }
  }, [active?.stage, loadAll]);

  const busy = ["generating", "replaying", "investigating"].includes(active?.stage);

  const simulateCrash = () => {
    fetch("/api/simulate-crash", { method: "POST" })
      .then((r) => r.json())
      .then(() =>
        fetch("/api/investigations/active").then((r) => r.json()).then(setActive)
      )
      .catch((e) => setError(String(e)));
  };

  if (error)
    return (
      <div className="empty-state error-state">
        <p className="empty-title">Operations Center unavailable</p>
        <p className="empty-hint">{error} — is the API running on port 8000?</p>
      </div>
    );

  if (!stats || !incidents)
    return (
      <div className="panel skeleton-panel" style={{ marginTop: 22 }}>
        <div className="skeleton skeleton-title" />
        {[...Array(5)].map((_, i) => (
          <div className="skeleton skeleton-row" key={i} />
        ))}
      </div>
    );

  const pct = (v) => (v == null ? "—" : `${Math.round(v * 100)}%`);

  return (
    <>
      <ProgressStrip active={active} />
      <section className="status-card panel">
        <div className="status-head">
          <span className="monitor-dot" />
          <span className="status-title">Flight Recorder Status</span>
          <span className="status-state">Monitoring</span>
          <button className="simulate-btn" onClick={simulateCrash} disabled={busy}>
            {busy ? "⚙ Running…" : "⚡ Simulate Crash"}
          </button>
        </div>
        <div className="status-facts">
          <span><strong>{stats.traces_today}</strong> traces today</span>
          <span><strong>{stats.investigations}</strong> investigations</span>
          <span><strong>{stats.active_incidents}</strong> active incident{stats.active_incidents === 1 ? "" : "s"}</span>
          <span>last replay <strong>{age(stats.last_replay_age_s)}</strong></span>
        </div>
      </section>

      <section className="tiles">
        <Tile label="Today's incidents" value={stats.incidents_today} />
        <Tile label="Open investigations" value={stats.open_investigations} />
        <Tile
          label="Latest alert"
          value={stats.alert ? stats.alert.state : "—"}
          sub={stats.alert ? stats.alert.name : "SigNoz API unavailable"}
        />
        <Tile label="Replay success rate" value={pct(stats.replay_success_rate)} sub={`${stats.replay_runs} replays`} />
        <Tile label="Avg investigation confidence" value={stats.avg_confidence == null ? "—" : `${Math.round(stats.avg_confidence)}%`} />
        <Tile label="Avg Root Cause Time" value={duration(stats.avg_root_cause_s)} sub="(MTTRC)" />
      </section>

      <ReplayCost cost={cost} />

      <FailingTools tools={tools} />

      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Incidents</h2>
        {incidents.length === 0 ? (
          <div className="empty-state">
            <p className="empty-title">No incidents recorded yet</p>
            <p className="empty-hint">Run the agent to record one: python -m agent.main</p>
          </div>
        ) : (
          <table className="incident-table">
            <thead>
              <tr>
                <th>incident</th>
                <th>request</th>
                <th>root cause</th>
                <th>replays</th>
                <th>status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {incidents.map((i) => (
                <tr key={i.trace_id} className="incident-row" onClick={() => onOpen(i.trace_id)}>
                  <td className="mono">{i.trace_id.slice(0, 8)}…</td>
                  <td>{i.request || "—"}</td>
                  <td className="cause-cell">{i.root_cause || (i.investigated ? "investigated" : "not investigated")}</td>
                  <td>{i.replay_count}</td>
                  <td>
                    {i.fix_validated ? (
                      <span className="badge badge-pass">FIX VALIDATED</span>
                    ) : i.investigated ? (
                      <span className="badge badge-fix">INVESTIGATED</span>
                    ) : (
                      <span className="badge badge-fail">OPEN</span>
                    )}
                    {i.auto && <span className="badge badge-auto">AUTO</span>}
                  </td>
                  <td>
                    <a
                      href={i.signoz_url}
                      target="_blank"
                      rel="noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="ext-link"
                    >
                      SigNoz ↗
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
