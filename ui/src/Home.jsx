import React, { useEffect, useState } from "react";

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

export default function Home({ onOpen }) {
  const [stats, setStats] = useState(null);
  const [incidents, setIncidents] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([
      fetch("/api/stats").then((r) => r.json()),
      fetch("/api/incidents").then((r) => r.json()),
    ])
      .then(([s, i]) => {
        setStats(s);
        setIncidents(i.incidents);
      })
      .catch((e) => setError(String(e)));
  }, []);

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
      <section className="status-card panel">
        <div className="status-head">
          <span className="monitor-dot" />
          <span className="status-title">Flight Recorder Status</span>
          <span className="status-state">Monitoring</span>
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
