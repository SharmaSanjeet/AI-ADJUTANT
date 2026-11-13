# Adjutant — Build Plan

**Product:** Adjutant, by Sanjeet Sharma
**Working/repo name:** AI-IRCP
**What it is:** the Incident Commander's chief of staff — an event-sourced coordination layer for stakeholder reporting, cross-domain dispatch, containment analysis, and BCP/DR notification. The AI proposes; humans decide.

---

## Non-negotiables (day 1, expensive to retrofit)

- Append-only event store is the single source of truth; reports and briefs are projections.
- Every fact carries source, valid time, recorded time, confidence tuple, fact status, and supersedes link.
- Hash-chained, append-only audit log; independently verifiable.
- Deterministic orchestrator: workflow and state transitions are code. LLMs only fill bounded slots.
- LLM proposes → policy decides (Allow / Deny / Escalate) → executor acts.
- Only the executor holds write credentials, and only JIT, short-lived, action-scoped ones.
- Provenance gate: no claim in any report without an evidence reference.
- Untrusted input quarantine: typed extraction before any planning agent sees the data.
- Dry-run mode on everything with side effects.
- Synthetic incident data only.

## Stack

| Layer | Choice |
|---|---|
| Backend | Python + FastAPI + Pydantic |
| State | Postgres (bitemporal event table + projections) |
| Workflow | Postgres-backed deterministic state machine (Temporal later if needed) |
| Policy | OPA/Rego sidecar |
| LLM | Thin `ModelPort`; Azure OpenAI/Foundry adapter + mock adapter |
| Integrations | Ports/adapters; mock adapters first |
| Auth/approval | Passkey + signed approval objects (mock keys in dev), passkey-ready interface |
| Frontend | React + TypeScript, Tailwind + shadcn/ui, dark-first operations theme |
| Local run | Docker Compose: app + Postgres + OPA |

## Principles of the build

- Vertical slice first; no microservices until something must scale independently.
- Mock adapters first; no external account required to run the app.
- Every deferred decision gets an ADR + config schema + feature flag.
- Config profiles: `local/mock` (default), `single-tenant`, `out-of-band`.
- Orchestration config is declarative and versioned, but the engine and transitions are code — no LLM-authored workflows, no arbitrary code in config.
- Config that changes approval, policy, or tiers is high-privilege: signed, versioned, audited.

## Phases

### Phase 0 — Foundations ✅
Repo skeleton, Docker Compose (app + Postgres + OPA), bitemporal event store, hash-chained audit, core schemas (`Fact`, `Evidence`, `ActionProposal`, `Approval`), `ModelPort` with mock adapter, synthetic ransomware incident seed.
**Exit:** append/replay tests green, audit chain verifies, API docs live, seeded incident loads on startup.

### Phase 1 — Scribe ✅
Signal ingest → quarantine extractor (deterministic allowlisted parsers + schema-strict, tool-less LLM extractor) → typed facts with `trust` markers → timeline and decision-log projections. Thin UI at `/ui`: incident rail, event timeline with provenance/confidence/trust chips, fact ledger, decision log, advisory proposals, and quarantined signals.
**Exit (met):** 18 tests green including the prompt-injection corpus; seeded incident renders end-to-end; disputed and untrusted-derived states visible in UI; audit chain verified.

### Phase 2 — Comms + clocks ✅
Audience-tailored briefs are built deterministically from trusted, current, evidenced facts (one cited claim per fact, audience prefix filters, deltas since the last brief for that audience). A deterministic fact-checker gate re-runs at approval and at send; human-only approval expires after 30 minutes; delivery is mock-only (`mock://`). Regulatory clocks are proposed as candidates by a pure engine — calendar, business-day, holiday, and timezone rules with a full computation trace — and bind only after a legal/DPO attestation that re-validates the trigger fact. UI: briefs and clocks tabs with claims, gate issues, approval/send actions, countdowns, traces, and confirmation forms.
**Exit (met):** 32 tests green, including unsupported identifiers/counts, superseded citations, judgment acknowledgements, disputed flags, business-day/holiday math, and legal-confirmation guards; no code path sends externally; audit chain verifies across 14 seed events.

### Phase 3 — Dispatch + BCP ✅
Asset → owner → on-call resolution with a fixed fallback chain (CMDB → service catalog → on-call roster → last assignee → team lead), per-source confidence, and a recorded step trace; `unknown_owner` is a first-class resolution and assignment that escalates to the incident commander. Acknowledgements are human-only, carry severity-based SLAs (sev1 15m → sev4 120m), and are escalated by a deterministic evaluator. BIA maps assets to services with RTO/RPO from typed facts and reports gaps instead of guessing; readiness assesses DR planes (identity, backup, EDR, ITSM, network) and a per-integration degraded-mode matrix where unknown evidence fails safe to manual. The shift handoff is assembled from projections with verified counts, including open approvals, open acknowledgements, evidence gaps, and pending clocks; it is display-only. UI: dispatch board, BCP tab, and handoff tab.
**Exit (met):** 42 tests green including fallback ordering, untrusted/disputed rejection, unknown-owner routing to the IC, SLA escalation (including IC-owned → deputy), BIA gaps, readiness fail-safe, and handoff counts; degraded modes exercised in the seed (cmdb/backup degraded, identity degraded, network unknown); audit chain verifies across 36 seed events.

### Phase 4 — Containment advisor ✅
Action catalog (`action-catalog@1`) with preconditions, blast radius, rollback, evidence-preservation steps, and write scope per action; a deterministic policy gate (`policy-engine@1`) deciding Allow / Deny / Escalate from the catalog and cited evidence — unknown actions and tier mismatches deny, never-automate actions, bad citations, untrusted or disputed evidence, and out-of-hours business-hours-only actions escalate; approvals are HMAC-signed with a mock key (`mock-hmac-sha256-v1`, passkey-ready interface), expire after 15 minutes, bind to an action hash over the exact proposal content, carry a unique nonce, and are single-use (a partial unique index blocks replay at the database level); the executor is dry-run only — it simulates evidence preservation first, then the action, records a rollback path, and obtains a scope descriptor from a mock JIT credential broker; `dry_run=false` is always refused, and refusals are recorded events. Never-automate actions (`wipe_host`, `disable_backup_jobs`, `pay_ransom`) always escalate and can never be approved or executed inside Adjutant. UI: containment tab with action details, policy reasons, signed-approval state with countdown, and dry-run execution.
**Exit (met):** 56 tests green including forgery (tampered payload and wrong key fail verification), replay (second execution refused and DB-blocked), expiry, action-hash mismatch, authority (role matrix + human-only approvers), never-automate escalation (approve/exec both fail closed), live-execution refusal, and the full evaluate → approve → dry-run chain with a verified audit chain across 39 seed events.

### Phase 5 — Limited automation ✅
Per-action autonomy scorecards over a rolling 30-day window (`autonomy-engine@1`, `autonomy-thresholds@1`) with shadow → suggest → approve levels: promotion requires scorecard thresholds (≥10 proposals, ≥80% allow rate, ≥5 simulated dry-runs, no breaker trips, no demotion triggers) **and** a config flag that defaults to off; demotion is deterministic and needs no flag (denies or breaker trips → shadow, refusals or expired approvals → one level down). Per-action circuit breakers trip after repeated consecutive execution refusals and reset only by a human; rate limits cap simulated dry-runs per action per rolling hour; an independent kill switch blocks every approval and execution across all incidents instantly, with its own audited event and env-var override. The `out-of-band` config profile refuses in-band approvals and vice versa; approval-request bundles are HMAC-signed with a 30-minute TTL and a recorded nonce, verified fail-closed; never-automate actions have no in-system approval path of any kind. UI: Automation tab with posture pills, kill-switch control, per-action guards, and scorecards. Tabletop suite exercises five scenarios end to end.
**Exit (met):** 72 tests green including threshold-gated promotion (refused with flag off), deterministic demotion (deny → shadow, breaker trip → shadow), kill-switch drill (approvals and executions refused, release restores), breaker trip and human-only reset, rate-limit refusal, OOB drill (in-band refused in OOB profile, OOB refused in in-band profile, expired bundle and wrong signature rejected), approval-request guards, and the five tabletop scenarios with the audit chain verifying after each.

## Decision log

| Date | Decision | Rationale |
| --- | --- | --- |
| 2026-11-12 | Brief text is templated from facts, never model-written | The gate can only verify what it can parse; deterministic claims make "unsupported claims cannot pass" provable. |
| 2026-11-12 | Gate re-runs at approval and again at send | Facts can be superseded or retracted between drafting and sending; a stale check would let bad claims through. |
| 2026-11-12 | Approvals are human-only and expire after 30 minutes | Enforces "no external communication without human approval"; actor prefixes `agent:`, `system:`, `bot:`, `model:` are rejected. |
| 2026-11-12 | Delivery is mock-only with `mock://` destinations | No external channel exists to misconfigure; Phase 3+ can add a real adapter behind the same approved-action contract. |
| 2026-11-12 | Judgments are allowed but require explicit acknowledgement | Keeps analytic value in briefs without letting opinion masquerade as fact. |
| 2026-11-12 | Timestamps and dates are stripped before count checks | ISO strings were being parsed as numeric claims; false positives in the gate erode trust in it. |
| 2026-11-12 | Clock engine is pure and stores a numbered trace | Every deadline is reproducible and auditable; legal confirms the deadline, the engine only proposes. |
| 2026-11-12 | Clock confirmation re-validates the trigger fact | A deadline anchored to a retracted or untrusted fact must not silently stand. |
| 2026-11-12 | `append_fact` must persist `trust` from the request | A test caught untrusted facts being stored as trusted; projection must round-trip every provenance field. |
| 2026-11-12 | Owner resolution uses a fixed, confidence-ranked fallback chain | Dispatch must be deterministic and explainable; a model choosing owners would make escalation unauditable. Every source tried, skipped, or rejected is recorded as a step. |
| 2026-11-12 | `unknown_owner` is a first-class resolution, not an empty value | Missing ownership is a real operational finding. It routes acknowledgements to the IC and appears as an evidence gap in the handoff. |
| 2026-11-12 | Acknowledgement SLAs escalate deterministically, never auto-close | A missed ack is a signal for a human to act on; auto-closing would hide a coordination failure. Escalation is an event, so it is replayable. |
| 2026-11-12 | BIA gaps are reported, never inferred | Inventing RTO/RPO from criticality would create false confidence in recovery plans. Missing service/RTO/RPO facts surface as explicit gaps. |
| 2026-11-12 | Unknown or untrusted readiness evidence fails safe to `manual` | Assuming an integration is available is the dangerous default; manual mode forces a human to bridge the gap. |
| 2026-11-12 | Shift handoff is display-only with counts verified from projections | A handoff that could send would create another external-communication path. Counts are computed, not typed, so the handoff cannot drift from the ledger. |
| 2026-11-13 | The policy gate is deterministic code, not the OPA sidecar | Every decision must be reproducible from the same inputs and auditable in the event log; the sidecar stays as a default-escalate placeholder for a future externalised-policy phase. |
| 2026-11-13 | Approvals bind to an action hash over the exact proposal content | An approval must not survive a change of params, target, or tier; the hash is recomputed at execution and any mismatch refuses. |
| 2026-11-13 | Approvals are single-use: one simulated execution consumes them | Replay is the classic approval attack; a partial unique index makes double execution impossible even under a race, and the pre-check returns a recorded refusal. |
| 2026-11-13 | Refused executions never consume an approval | A refusal (e.g. live mode, or a transient gate failure) must not burn a valid approval; only a simulated execution spends it. Refusals are still recorded events. |
| 2026-11-13 | Never-automate actions cannot be approved or executed in-system | Escalate means "a human decides outside this system". If the API allowed approving them, the never-automate list would be advisory only. |
| 2026-11-13 | The executor refuses `dry_run=false` unconditionally | No real adapter exists; the refusal is recorded so an attempt to go live is visible in the audit trail, not silently ignored. |
| 2026-11-13 | The JIT broker issues scope descriptors, never credentials | Adjutant must not become a credential store; a real executor would exchange the scope for a short-lived credential outside the control plane. |
| 2026-11-13 | Disputed, superseded, or untrusted citations escalate instead of allowing | Actions must be justified by current, trusted evidence; the demo's disputed identity fact intentionally cannot justify isolation. |
| 2026-11-13 | Containment records expose `approval_spent` computed from the ledger, not inferred from the latest execution | A refusal after a simulated run would otherwise make a spent approval look active in the UI; display state must be derived from the same facts as enforcement, so the card cannot drift from what the gate will enforce. |
| 2026-11-13 | Autonomy promotion requires both scorecard thresholds and a config flag that defaults to off | Trust in an action type is earned from evidence, not granted by configuration alone — and neither alone is enough. Fail-safe default: no flag, no promotion, regardless of how good the scorecard looks. |
| 2026-11-13 | Demotion is deterministic and never gated by configuration | If the evidence shows an action type misbehaving, nothing should stand between the system and stepping it back; demotion is a safety response, not a privilege. |
| 2026-11-13 | The kill switch is its own control plane with env-var override, not just a DB row | A stuck database or a compromised app must not trap the switch; the operator needs a path that works even when the application cannot. Engage and release are separate audited events with human + reason required for both. |
| 2026-11-13 | Kill-switch and autonomy-level events record against a nil incident | They are global, not incident-scoped; attaching them to one incident would make the timeline lie about their scope. Breaker trips, which do belong to an incident, land in that incident's timeline. |
| 2026-11-13 | Breakers and rate limits are per action type, not per proposal | A malfunctioning action type (bad catalog entry, flaky integration) fails in bulk; a per-proposal limit would just slow the failure down. Tripping on consecutive refusals with a human-only reset makes recovery a decision, not an accident. |
| 2026-11-13 | The out-of-band profile refuses in-band approvals, and in-band profiles refuse OOB approvals | The approval channel is a security boundary; silently accepting both would let a compromised in-band path sign off on actions that were supposed to be decided outside the system. |
| 2026-11-13 | OOB bundle verification is fail-closed on every dimension | Decision currency, bundle expiry, action-hash match, attestation signature — any single miss refuses. An out-of-band approval is only as strong as its weakest check. |
| 2026-11-13 | Never-automate actions cannot create approval requests at all | Phase 4 blocked approve/execute; Phase 5 closes the last gap — an OOB bundle is still an in-system artifact, so even that path is refused. "A human decides outside this system" means outside, completely. |
| 2026-11-13 | The policy gate's asset check matches any domain prefix (`asset/`, `identity/`, `network/`, `backup/`), not just `asset/` | The tabletop suite caught proposals targeting identity and network assets escalating despite perfectly good citations; the gate should judge evidence quality, not attribute spelling. |

## Deferred behind config (not forgotten)

- Out-of-band topology alternatives (independent control plane shipped in Phase 5; same-tenant degraded mode deferred)
- Jurisdiction/regulator clock rules and legal sign-off
- Privilege/retention model and legal hold
- Auto-containment enablement
- Model provider and data residency
- Real identity/approval provider and signing keys

Each deferred item must be revisited at every phase gate, not "later".

## Local run

```bash
docker compose up
# UI:       http://localhost:8010/ui
# API:      http://localhost:8010
# API docs: http://localhost:8010/docs
# Seeded incident loads automatically
```
