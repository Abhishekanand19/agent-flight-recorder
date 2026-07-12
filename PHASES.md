# Phase Plan — Agent Flight Recorder

Each phase: enter plan mode first, build, run it, invoke verifier agent,
show me PASS/FAIL, commit+push only on PASS, then STOP.
Original failing trace id: f809ade2ecee6aba1c2669047f8a59ce

## Phase 2.5 — Restore demo contrast (do FIRST if not done)
Add replay config cf-5 that applies the structural fix (corrected
non-stale KB entry refund_api_v2, OR a forced check_order verification
step before refund). Re-run ONLY cf-5 (quota). It must emit
replay.success=true, replay.of linkage, replay.fix_applied=true.
Definition of Done: success matrix shows 4 FAIL + cf-5 PASS. Verifier
PASS. Commit `feat: add fix-applied replay config for demo contrast`.

## Phase 3 — Crash Investigator (investigator/investigate.py)
- CLI arg --trace-id <original>
- Pull original failing trace + linked replay traces (replay.of) from SigNoz
- Compute structured diff: which span/tool differs between fail configs and
  the cf-5 fix config; which config succeeded
- ONE Gemini call, returns ONLY valid JSON (no fences):
  { root_cause, confidence_pct, suggested_fix, supporting_evidence }
- Parse safely, print a clean verdict card (English, not raw JSON/span IDs)
- META-OBSERVABILITY: the Investigator is itself OTel-instrumented under
  service.name=crash-investigator, spans carry investigation.of,
  investigation.confidence, llm.model, llm.tokens
Definition of Done: verdict card correct (points at stale KB / missing
verification, matches real failure) + crash-investigator spans visible in
SigNoz. Verifier PASS. Commit `feat: add crash investigator with meta-observability`.

## Phase 4 — Diff UI (/ui, React + Vite)
- Two trace waterfalls side by side: original fail vs cf-5 fix
- First divergent span highlighted red
- Success matrix panel (all configs → PASS/FAIL)
- Verdict card from Phase 3 rendered as a clean card
- One "Investigate" button that triggers/reads the investigation
- No backend auth needed; read trace data via a small FastAPI endpoint
  that queries ClickHouse (reuse the replay engine's access pattern)
Definition of Done: npm run dev renders all 4 elements with real data from
trace f809ade2... Verifier confirms UI reads live data. Commit
`feat: add diff UI with waterfalls, matrix, verdict card`.

## Phase 5 — Dashboards, alert, README (submission polish)
- SigNoz dashboard: token cost per step, agent failure rate, replay
  success matrix as a panel, investigator confidence over time
- Alert rule: agent failure rate spike → (demo) links to replay
- README: problem statement, 3-pillar architecture diagram, the
  flight-recorder pitch line, setup steps, demo GIF placeholder,
  "Roadmap" section (incident memory, prompt-version diffing, auto-PR) —
  clearly labeled future work, not built
- Architecture diagram (mermaid in README is fine)
Definition of Done: dashboard loads, alert rule exists, README complete
with diagram. Verifier PASS. Commit `docs: add dashboards, alerts, README`.
