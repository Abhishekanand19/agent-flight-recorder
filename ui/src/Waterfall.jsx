import React from "react";

function kind(span) {
  if (span.name.startsWith("tool.")) return "tool";
  if (span.name.startsWith("llm.")) return "llm";
  return "root";
}

// The divergence marks the Nth tool call (position) where fail and fix
// runs differ; highlight that tool span in this waterfall.
function divergentSpanId(spans, divergence) {
  if (!divergence) return null;
  const toolSpans = spans.filter((s) => kind(s) === "tool");
  const target = toolSpans[divergence.position];
  return target && target.name === `tool.${divergence.tool}` ? target.span_id : null;
}

export default function Waterfall({ title, spans, divergence, failSide }) {
  const total = Math.max(...spans.map((s) => s.start_ms + s.duration_ms), 1);
  const divergent = divergentSpanId(spans, divergence);

  return (
    <div className={`waterfall ${failSide ? "fail" : "pass"}`}>
      <h2>{title}</h2>
      {spans.map((s) => {
        const left = (s.start_ms / total) * 100;
        const width = Math.max((s.duration_ms / total) * 100, 0.8);
        const isDivergent = s.span_id === divergent;
        return (
          <div
            className={`row ${isDivergent ? "divergent" : ""}`}
            key={s.span_id}
            title={s.error_message || s.tool_input || s.llm_model || s.name}
          >
            <span className="label">
              {s.name}
              {s.error && <em className="badge badge-err">ERR</em>}
              {isDivergent && <em className="badge badge-diverge">DIVERGES</em>}
            </span>
            <span className="track">
              <span
                className={`bar ${kind(s)} ${s.error ? "error" : ""}`}
                style={{ left: `${left}%`, width: `${width}%` }}
              />
            </span>
            <span className="dur">
              {s.duration_ms >= 1 ? `${s.duration_ms.toFixed(0)} ms` : "<1 ms"}
            </span>
          </div>
        );
      })}
    </div>
  );
}
