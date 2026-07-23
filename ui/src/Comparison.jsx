import React, { useState } from "react";

const TRADITIONAL = [
  "🚨 Alert",
  "🔍 Manual trace analysis",
  "❓ Guess root cause",
  "🚀 Deploy fix",
  "🤞 Hope it works",
];
const FLIGHT_RECORDER = [
  "🚨 Alert",
  "⚙️ Replay",
  "🤖 AI investigation",
  "🎯 Root cause",
  "✅ Validated fix",
  "🛠️ Engineer action",
];

const DIMENSIONS = [
  { label: "Time to root cause", trad: "15–30 min · manual", afr: (t) => `${t} · automated` },
  { label: "Manual effort", trad: "High — read traces by hand", afr: () => "None — fully hands-free" },
  { label: "Replay automation", trad: "Not possible", afr: () => "Automated counterfactuals" },
  { label: "Root cause analysis", trad: "Guesswork", afr: () => "AI + evidence scorecard" },
  { label: "Fix validation", trad: "Deploy and hope", afr: () => "Replay-validated before merge" },
  { label: "Engineer productivity", trad: "Low", afr: () => "High" },
];

function Chain({ steps, kind }) {
  return (
    <div className={`wf-chain ${kind}`}>
      {steps.map((s, i) => (
        <React.Fragment key={s}>
          {i > 0 && <span className="wf-arrow">→</span>}
          <span className="wf-step">{s}</span>
        </React.Fragment>
      ))}
    </div>
  );
}

export default function Comparison({ avgRootCauseSeconds }) {
  const [open, setOpen] = useState(false);
  const afterTime =
    avgRootCauseSeconds && avgRootCauseSeconds < 600 ? `~${Math.round(avgRootCauseSeconds)} sec` : "~90 sec";

  return (
    <section className="comparison panel">
      <button className="comparison-toggle" onClick={() => setOpen(!open)}>
        <span>⚡ Why Flight Recorder? — traditional debugging vs. automated investigation</span>
        <span className="comparison-caret">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="comparison-body">
          <div className="wf-grid">
            <div>
              <div className="wf-title bad">Traditional workflow</div>
              <Chain steps={TRADITIONAL} kind="bad" />
            </div>
            <div>
              <div className="wf-title good">Agent Flight Recorder</div>
              <Chain steps={FLIGHT_RECORDER} kind="good" />
            </div>
          </div>

          <table className="cmp-table">
            <thead>
              <tr>
                <th></th>
                <th className="bad">Traditional</th>
                <th className="good">Flight Recorder</th>
              </tr>
            </thead>
            <tbody>
              {DIMENSIONS.map((d) => (
                <tr key={d.label}>
                  <td className="cmp-dim">{d.label}</td>
                  <td className="cmp-bad">✕ {d.trad}</td>
                  <td className="cmp-good">✓ {d.afr(afterTime)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
