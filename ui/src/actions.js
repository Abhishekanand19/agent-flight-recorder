// Engineer Action Center helpers. Everything is assembled from the incident
// and verdict data the page already holds — no new data models.

const SIGNOZ = "http://localhost:8080";

function timelineSteps(incident) {
  return [
    { label: "Original failure captured", done: true },
    { label: "Replayed under counterfactual configs", done: incident.matrix.length > 0 },
    { label: "Investigated — root cause identified", done: incident.investigation?.investigated },
    { label: "Fix found", done: incident.matrix.some((m) => m.fix_applied) },
    { label: "Validated", done: Boolean(incident.fix) },
  ];
}

export function buildMarkdown(incident, verdict) {
  const tid = incident.original.trace_id;
  const bd = incident.confidence_breakdown;
  const matrix = incident.matrix;
  const failed = matrix.filter((m) => !m.success).length;
  const passed = matrix.filter((m) => m.success).length;
  const L = [];

  L.push(`# Incident Report — ${tid.slice(0, 8)}…`, "");
  L.push(`- **Trace ID:** \`${tid}\``);
  L.push(`- **Generated:** ${new Date().toISOString()}`);
  L.push(`- **Confidence:** ${verdict.confidence_pct}%${bd ? ` (backed by ${bd.signals_met}/${bd.signals_total} signals)` : ""}`);
  L.push(`- **SigNoz trace:** ${SIGNOZ}/trace/${tid}`, "");

  L.push("## Summary");
  L.push(`Counterfactual replay reproduced the failure in ${failed}/${matrix.length} configs; ${passed} passed with the structural fix. Root cause below.`, "");

  L.push("## Root Cause");
  L.push(verdict.root_cause, "");

  L.push("## Validated Fix");
  L.push(verdict.suggested_fix, "");

  if (verdict.supporting_evidence?.length) {
    L.push("## Supporting Evidence");
    verdict.supporting_evidence.forEach((e) => L.push(`- ${e}`));
    L.push("");
  }

  if (bd) {
    L.push("## Confidence Breakdown");
    bd.signals.forEach((s) => L.push(`- ${s.met ? "[x]" : "[ ]"} **${s.label}** — ${s.detail}`));
    L.push("");
  }

  L.push("## Replay Results");
  L.push("| config | model | temp | fix | result | reason |");
  L.push("| --- | --- | --- | --- | --- | --- |");
  matrix.forEach((m) =>
    L.push(
      `| ${m.config_id} | ${m.model} | ${Number(m.temperature).toFixed(1)} | ${m.fix_applied ? "yes" : "no"} | ${m.success ? "PASS" : "FAIL"} | ${m.reason || ""} |`
    )
  );
  L.push("");

  if (incident.impact) {
    const d = incident.impact.deltas;
    L.push("## Delta Impact (validated fix vs original)");
    L.push(`- Latency: ${Math.round(d.avg_latency_ms)} ms`);
    L.push(`- Tokens: ${d.tokens}`);
    L.push(`- Execution time: ${Math.round(d.exec_ms)} ms`);
    L.push(`- Estimated cost: $${d.cost_usd.toFixed(4)}`, "");
  }

  L.push("## Investigation Timeline");
  timelineSteps(incident).forEach((s, i) => L.push(`${i + 1}. ${s.done ? "[x]" : "[ ]"} ${s.label}`));

  if (verdict.similar) {
    L.push("", "## Related History");
    L.push(`Similar to incident \`${verdict.similar.incident_id}\` (${verdict.similar.match_pct}% match) — previous fix: ${verdict.similar.suggested_fix}`);
  }
  return L.join("\n");
}

export function buildIssue(incident, verdict) {
  const tid = incident.original.trace_id;
  const matrix = incident.matrix;
  const failed = matrix.filter((m) => !m.success).length;
  const passed = matrix.filter((m) => m.success).length;
  const short = verdict.root_cause.length > 70 ? verdict.root_cause.slice(0, 70) + "…" : verdict.root_cause;

  const body = [
    `**Trace ID:** \`${tid}\``,
    `**SigNoz trace:** ${SIGNOZ}/trace/${tid}`,
    `**Confidence:** ${verdict.confidence_pct}%`,
    "",
    "## Root cause",
    verdict.root_cause,
    "",
    "## Suggested / validated fix",
    verdict.suggested_fix,
    "",
    "## Supporting evidence",
    ...(verdict.supporting_evidence || []).map((e) => `- ${e}`),
    "",
    "## Replay summary",
    `${failed}/${matrix.length} counterfactual configs reproduced the failure; ${passed} passed with the structural fix applied.`,
    ...matrix.map(
      (m) => `- \`${m.config_id}\` ${m.model} @ ${Number(m.temperature).toFixed(1)}${m.fix_applied ? " (fix)" : ""}: **${m.success ? "PASS" : "FAIL"}**`
    ),
    "",
    "_Filed from the Agent Flight Recorder Engineer Action Center._",
  ].join("\n");

  return { title: `[Agent Incident] ${short}`, body };
}

export function githubIssueUrl(repo, { title, body }) {
  return `https://github.com/${repo}/issues/new?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`;
}

export function downloadMarkdown(filename, text) {
  const blob = new Blob([text], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// Minimal markdown -> HTML for the print/PDF window (handles only the subset
// buildMarkdown emits: headings, bullets, tables, bold, inline code).
function mdToHtml(md) {
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const inline = (s) =>
    esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  const out = [];
  let inList = false, inTable = false;
  const closeList = () => inList && (out.push("</ul>"), (inList = false));
  const closeTable = () => inTable && (out.push("</table>"), (inTable = false));
  for (const line of md.split("\n")) {
    if (line.startsWith("## ")) { closeList(); closeTable(); out.push(`<h2>${inline(line.slice(3))}</h2>`); }
    else if (line.startsWith("# ")) { closeList(); closeTable(); out.push(`<h1>${inline(line.slice(2))}</h1>`); }
    else if (line.startsWith("- ") || /^\d+\. /.test(line)) {
      closeTable();
      if (!inList) { out.push("<ul>"); inList = true; }
      out.push(`<li>${inline(line.replace(/^(- |\d+\. )/, ""))}</li>`);
    } else if (line.startsWith("|")) {
      closeList();
      const cells = line.split("|").slice(1, -1).map((c) => c.trim());
      if (cells.every((c) => /^-+$/.test(c))) continue;
      if (!inTable) { out.push("<table>"); inTable = true; }
      out.push("<tr>" + cells.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>");
    } else { closeList(); closeTable(); if (line.trim()) out.push(`<p>${inline(line)}</p>`); }
  }
  closeList(); closeTable();
  return out.join("\n");
}

export function printReport(incident, verdict) {
  const html = mdToHtml(buildMarkdown(incident, verdict));
  const w = window.open("", "_blank");
  if (!w) return;
  w.document.write(
    `<html><head><title>Incident Report ${incident.original.trace_id.slice(0, 8)}</title>` +
      "<style>body{font-family:system-ui,Segoe UI,sans-serif;max-width:820px;margin:36px auto;padding:0 24px;line-height:1.5;color:#111;}" +
      "h1{font-size:22px;} h2{font-size:16px;margin-top:22px;border-bottom:1px solid #ddd;padding-bottom:4px;}" +
      "code{background:#f3f3f3;padding:1px 5px;border-radius:3px;font-size:90%;}" +
      "table{border-collapse:collapse;width:100%;font-size:13px;} td{border:1px solid #ccc;padding:4px 8px;}" +
      "ul{padding-left:20px;}</style></head><body>" + html + "</body></html>"
  );
  w.document.close();
  w.focus();
  setTimeout(() => w.print(), 350);
}
