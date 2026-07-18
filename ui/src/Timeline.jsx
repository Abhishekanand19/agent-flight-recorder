import React from "react";

// Incident lifecycle: each step lights up from real data, no guesses.
export default function Timeline({ incident, verdict }) {
  const steps = [
    { label: "Original", done: true },
    { label: "Replayed", done: incident.matrix.length > 0 },
    { label: "Investigated", done: incident.investigation?.investigated ?? false },
    { label: "Fix found", done: Boolean(verdict?.suggested_fix || incident.matrix.some((m) => m.fix_applied)) },
    { label: "Validated", done: Boolean(incident.fix) },
  ];
  return (
    <div className="timeline panel">
      {steps.map((s, i) => (
        <React.Fragment key={s.label}>
          {i > 0 && <span className={`timeline-bar ${s.done ? "done" : ""}`} />}
          <span className={`timeline-step ${s.done ? "done" : ""}`}>
            <span className="timeline-dot">{s.done ? "✓" : ""}</span>
            {s.label}
          </span>
        </React.Fragment>
      ))}
    </div>
  );
}
