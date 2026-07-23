import React, { useState } from "react";
import { buildIssue, buildMarkdown, downloadMarkdown, githubIssueUrl, printReport } from "./actions.js";

// The repo incidents are filed against. Change to your fork if needed.
const REPO = "Abhishekanand19/agent-flight-recorder";

export default function ActionCenter({ incident, verdict }) {
  const [copied, setCopied] = useState(false);

  if (!verdict) {
    return (
      <section className="panel action-center">
        <h2>Actions</h2>
        <p className="empty-hint">
          Run the investigation to enable one-click report export and GitHub issue creation.
        </p>
      </section>
    );
  }

  const tid = incident.original.trace_id;
  const copyReport = () => {
    navigator.clipboard.writeText(buildMarkdown(incident, verdict)).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  const issueUrl = githubIssueUrl(REPO, buildIssue(incident, verdict));

  return (
    <section className="panel action-center">
      <h2>Actions</h2>
      <p className="action-intro">
        Everything below is pre-filled from this investigation — no copy-pasting required.
      </p>
      <div className="action-buttons">
        <button className="action-btn" onClick={() => downloadMarkdown(`incident-${tid.slice(0, 8)}.md`, buildMarkdown(incident, verdict))}>
          ⬇ Export report (.md)
        </button>
        <button className="action-btn" onClick={() => printReport(incident, verdict)}>
          🖨 Save as PDF
        </button>
        <button className="action-btn" onClick={copyReport}>
          {copied ? "✓ Copied" : "⧉ Copy report"}
        </button>
        <a className="action-btn primary" href={issueUrl} target="_blank" rel="noreferrer">
          ⎇ Create GitHub issue
        </a>
      </div>
    </section>
  );
}
