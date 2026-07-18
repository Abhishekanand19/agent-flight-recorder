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

## Phase 6 — Demo Experience Polish (post-5 roadmap, do FIRST)
Make the product feel premium. UI pass in /ui (styles + small component
touches, NO logic changes): loading skeletons + Investigate spinner,
designed empty states, one consistent badge system (PASS/FAIL/ERR/
DIVERGES/fix), typography + color-token consistency, smooth transitions,
fix temp 0 -> 0.0 in Matrix. Docs: README gains a "Why Flight Recorder?"
section at the very top (what failed? -> why, what-if, what fixes it,
can the fix be verified); new DEMO.md with the 3-min script, pre-demo
checklist, GIF fallback, closing line ("Traditional observability ends
at the alert. Flight Recorder starts there."). Record docs/demo.gif
(UI flow + ~5s of SigNoz trace view + dashboard).
Definition of Done: no broken README images; GIF plays on GitHub; UI
polish visible; DEMO.md exists. Verifier PASS. Commit
`feat: demo experience polish` + push.

## Phase 7 — Flight Operations Center
Land on a command center, not a trace. Backend (api/main.py, read-only
over existing data): GET /api/incidents (distinct replay.of + latest
investigation spans + cached verdicts -> per-incident lifecycle status);
GET /api/stats (status card + tiles: traces/incidents today, replay
success rate, avg investigation.confidence, last-replay age, Avg Root
Cause Time from span timestamps, latest alert state via SigNoz rules
API — fallback to ClickHouse-only tiles if payload shape shifts).
Frontend: Home.jsx (large "Flight Recorder Status" card: Monitoring dot,
traces today, investigations, active incidents, last replay age; stat
tiles incl. "Avg Root Cause Time" with small (MTTRC) sub-label; incident
table with SigNoz trace deep-links); Timeline.jsx (horizontal lifecycle
Original -> Replayed -> Investigated -> Fix found -> Validated, lit from
real status, shown atop the incident detail view). App.jsx: two views
(home / incident detail), existing traceId state is the switch.
Definition of Done: UI opens on the Operations Center with >=2 real
incidents and live stats; clicking a row lands in the diff view;
verifier cross-checks /api/incidents against ClickHouse. Commit
`feat: flight operations center` + push.

## Phase 8 — Closed loop: alert -> auto-investigation
SigNoz webhook channel -> POST /api/webhook/alert -> background task:
find most recent errored support_request trace, idempotency check via
.cache (never re-investigate; protects Gemini quota), then replay
(existing pacing rules) + investigate() with
investigation.triggered_by=alert on the root span. Provision the webhook
channel + bind to the existing rule via scripts/provision_signoz.py.
scripts/failure_storm.py (5 sequential agent runs) trips the alert on
demand. Frontend: incident list auto-refreshes (15s), "auto-investigated
by alert" badge, live progress strip (Alert received -> Replaying ->
Investigating -> Root cause found) driven by GET
/api/investigations/active.
Definition of Done: failure storm -> alert fires -> incident appears in
the UI with verdict attached, zero human action; triggered_by=alert span
visible in SigNoz. Verifier PASS. Commit
`feat: alert-triggered auto-investigation` + push. THEN STOP.

## Parked (post-hackathon; do not build before judging)
- Phase 9 (optional, only if 8 is done + rehearsed with slack):
  replay --assert exit-code gate + illustrative CI workflow, honestly
  labeled as needing SigNoz + keys to run.
- Phase 10: second incident type / generalized success criteria —
  highest risk to the deterministic demo; first thing AFTER judging.
- Phase 11: OTel span links — invisible in demo; roadmap mention only.
