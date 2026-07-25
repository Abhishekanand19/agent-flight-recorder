import React from "react";

const FIELDS = [
  ["customer", "Customer"],
  ["application", "Application"],
  ["service", "Service"],
  ["model", "Model"],
  ["tool", "Tool"],
  ["status", "Status"],
];

function derive(incident) {
  const models = [...new Set(incident.matrix.map((m) => m.model))].join(" · ");
  return {
    customer: "Customer request",
    application: "AI Customer Support",
    service: "support-agent",
    model: models,
    tool: incident.divergence ? `${incident.divergence.tool}()` : "—",
    status: incident.investigation?.investigated ? "Fix validated" : "Investigating",
  };
}

export default function IncidentContext({ incident }) {
  const ctx = incident.context || derive(incident);
  const stats = incident.replay_stats || {
    counterfactuals: incident.matrix.length,
    validated: incident.matrix.filter((m) => m.success).length,
    failed: incident.matrix.filter((m) => !m.success).length,
  };

  return (
    <>
      {incident.summary && (
        <section className="incident-summary panel">
          <span className="summary-badge">Incident summary</span>
          <p>{incident.summary}</p>
        </section>
      )}

      <section className="incident-context panel">
        <div className="ctx-grid">
          {FIELDS.map(([key, label]) =>
            ctx[key] ? (
              <div className="ctx-item" key={key}>
                <div className="ctx-label">{label}</div>
                <div className={`ctx-value ${key === "status" ? "ctx-status" : ""}`}>{ctx[key]}</div>
              </div>
            ) : null
          )}
        </div>

        <div className="replay-stats">
          <div className="rstat">
            <div className="rstat-num">{stats.counterfactuals}</div>
            <div className="rstat-label">Counterfactuals tested</div>
          </div>
          <div className="rstat good">
            <div className="rstat-num">{stats.validated}</div>
            <div className="rstat-label">Validated fix</div>
          </div>
          <div className="rstat bad">
            <div className="rstat-num">{stats.failed}</div>
            <div className="rstat-label">Failed replays</div>
          </div>
        </div>
      </section>
    </>
  );
}
