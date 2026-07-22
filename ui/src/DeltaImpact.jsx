import React from "react";

// Every metric here is "lower is better", so a negative delta is an
// improvement. Deltas come from the API as fix - original.
function sign(d) {
  return d < 0 ? "−" : d > 0 ? "+" : "";
}
function deltaMs(d) {
  const a = Math.abs(d);
  return sign(d) + (a >= 1000 ? `${(a / 1000).toFixed(1)} s` : `${Math.round(a)} ms`);
}
function deltaTokens(d) {
  return sign(d) + Math.abs(Math.round(d)).toLocaleString() + " tok";
}
function deltaCost(d) {
  return sign(d) + "$" + Math.abs(d).toFixed(4);
}

export default function DeltaImpact({ impact }) {
  if (!impact) return null;
  const { deltas, pct } = impact;
  const items = [
    { label: "Latency reduction", d: deltas.avg_latency_ms, p: pct.avg_latency_ms, fmt: deltaMs },
    { label: "Token savings", d: deltas.tokens, p: pct.tokens, fmt: deltaTokens },
    { label: "Execution time", d: deltas.exec_ms, p: pct.exec_ms, fmt: deltaMs },
    { label: "Est. cost savings", d: deltas.cost_usd, p: pct.cost_usd, fmt: deltaCost },
  ];
  return (
    <section className="panel delta-impact">
      <h2>Delta impact · validated fix vs original failure</h2>
      <div className="delta-cells">
        {items.map((it) => {
          const cls = it.d < 0 ? "good" : it.d > 0 ? "bad" : "flat";
          return (
            <div className={`delta-cell ${cls}`} key={it.label}>
              <div className="delta-value">{it.fmt(it.d)}</div>
              <div className="delta-label">{it.label}</div>
              {it.p != null && (
                <div className="delta-pct">
                  {it.p > 0 ? "+" : ""}
                  {it.p}%
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
