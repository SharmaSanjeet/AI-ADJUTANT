# Architecture

How Adjutant is built, why each piece exists, and where the trust boundaries are.

---

## Overview

Adjutant is a single FastAPI service backed by PostgreSQL, with a React UI, an OPA sidecar (placeholder for externalized policy), and mock integrations. Everything runs in Docker Compose for local use.

```
┌─────────────┐   signals    ┌──────────────────────────────┐
│ EDR/CMDB/IdP│─────────────▶│  Quarantine extractor        │
│ (mock now)  │              │  deterministic → LLM slot    │
└─────────────┘              └──────────────┬───────────────┘
                                            │ typed, untrusted facts
        ┌───────────────────────────────────▼────────────────────┐
        │                 Append-only event store                │
        │        hash-chained · bitemporal · trigger-guarded     │
        └───────────────────┬────────────────────────────────────┘
                            │ projections (replayable)
   ┌──────────┬──────────┬──┴───────┬───────────┬──────────────┐
   ▼          ▼          ▼          ▼           ▼              ▼
 Facts     Briefs     Clocks     Dispatch   Containment   Handoff
 ledger    +checker   engine     +SLA       policy gate   (display)
   │          │          │          │           │
   └──────────┴──────────┴──────────┴───────────┘
                        │
                 Human gates only:
        approve · ack · confirm · send · execute
```

- **Backend:** Python 3.11, FastAPI, Pydantic v2, psycopg3 (async pool)
- **State:** PostgreSQL 16 (event store + projections)
- **Frontend:** React 18, TypeScript, Vite, Tailwind — dark-first operations theme
- **LLM:** thin `ModelPort` with a schema-strict mock adapter (Azure adapter is a documented future slot)

---

## The event store

The single source of truth is the `events` table:

- **Append-only at the database level.** `BEFORE UPDATE OR DELETE` triggers reject any mutation — not an application convention, a schema guarantee.
- **Hash-chained.** Each event's hash covers the previous event's hash, the event metadata, and the payload. Tampering with any row breaks the chain and `/audit/verify` reports the first broken sequence.
- **Bitemporal.** Events carry `valid_at` (when the thing happened in the world) and `recorded_at` (when Adjutant learned it). Reconstructing "what did we know at time T" is a filter, not an investigation.
- **Global events use a nil incident.** Kill-switch engagements and autonomy-level changes record against the nil UUID (`000…0`) so they are auditable without polluting any incident timeline. Breaker trips, which do belong to an incident, land in that incident's timeline.

Everything else — the fact ledger, timelines, briefs, dispatch boards, handoffs — is a **projection** of events. `rebuild_facts` replays the log to prove it.

## The fact model

Facts are bitemporal rows with mandatory provenance:

| Field | Purpose |
|---|---|
| `attribute` | Namespaced path, e.g. `asset/FIN-WS-0142/behaviour`, `decision/containment/001` |
| `value` | Typed value from allowlisted extraction |
| `source` | Who asserted it (`edr:mock`, `human:priya.nair`, `agent:dispatch`, `extractor:deterministic-json`) |
| `valid_at` / `recorded_at` | Bitemporal pair |
| `confidence` | Tuple: source reliability, corroboration, extraction certainty |
| `status` | `asserted → corroborated / disputed / retracted / superseded` |
| `trust` | `trusted · untrusted · mixed` — untrusted-derived facts can never justify an action |
| `classification` | Public / internal / restricted |
| `evidence` | Content-hashed references (every claim traces to evidence) |
| `supersedes` | Explicit correction chain |

The lifecycle is **never destructive**: corrections supersede, disputes annotate, retractions retract. The history stays queryable.

## Quarantine ingestion

`POST /incidents/{id}/signals` is the only external input door. What happens to raw content:

1. **Dedupe** by content hash per incident.
2. **Deterministic extraction first** — JSON (or `key=value` tokens) filtered through a fixed allowlist of keys, bounded to 10 fields and 500 chars per value.
3. **LLM slot only as fallback** — the `ModelPort` extractor is tool-less, schema-strict (`extra="forbid"`, bounded lengths), and has no network or credential access. It sees residual text only when the deterministic parser found nothing.
4. **Every extracted field becomes an untrusted fact** with evidence pointing at the raw signal's content hash. Raw content is stored and visible on the Signals tab — permanently untrusted until a trusted source explicitly supersedes it.

This is the prompt-injection boundary: attacker-controlled text can enter the ledger only as inert, untrusted, clearly-labeled facts. The policy gate refuses actions justified by untrusted facts.

## The agents

Eight deterministic agents do the analytical work. They are code, not LLM loops — same inputs produce the same outputs, replayable from the event log.

| Agent | Does | Cannot do |
|---|---|---|
| `agent:containment-advisor` | Assessment facts, tiered action proposals with cited evidence | Approve, execute |
| `agent:scribe` | Draft briefs — claims templated from evidenced facts | Write prose, send |
| `agent:fact-checker` | Gate briefs at draft, approval, and send | Pass an unsupported claim |
| `agent:clock-advisor` | Propose regulatory deadlines with computation traces | Confirm a clock |
| `agent:dispatch` | Resolve owners via the fixed fallback chain | Acknowledge |
| `agent:bia` | Map assets → services, RTO/RPO; report gaps | Infer missing targets |
| `agent:readiness` | Assess DR planes and integrations | Assume availability |
| `agent:handoff` | Assemble the shift handoff with verified counts | Send anything |

Consequential actions reject `agent:`/`system:`/`bot:`/`model:` actors by design.

## The containment gate chain

**1. Action catalog** (`action-catalog@1`) — every action declares preconditions, blast radius, rollback steps, evidence-preservation steps, write scope, tier, business-hours restriction, and `never_automate`.

**2. Policy gate** (`policy-engine@1`) — deterministic; first failing rule wins, every outcome records its reasons:

```
unknown action            → deny
tier mismatch             → deny
never-automate            → escalate (no in-system path)
no citations / missing    → escalate
disputed/retracted/super. → escalate
untrusted citations       → escalate
out-of-hours (restricted) → escalate
no facts on target asset  → escalate
otherwise                 → allow (role matrix applies)
```

The asset check matches any domain prefix (`asset/`, `identity/`, `network/`, `backup/`) — the gate judges evidence quality, not attribute spelling.

**3. Approvals** — HMAC-signed (mock key, passkey-ready interface), expire in 15 minutes, bind to an action hash over the exact proposal content, carry a unique nonce, and are **single-use**: a partial unique index blocks replay at the database level even under a race. Refused executions never consume an approval; only a simulated run spends it.

**4. Executor** — dry-run only. It simulates evidence preservation first, then the action, records the rollback path, and obtains a scope *descriptor* from a mock JIT credential broker (Adjutant never becomes a credential store). `dry_run=false` is refused unconditionally and the refusal is recorded.

**Out-of-band channel.** With `CONFIG_PROFILE=out-of-band`, in-band approvals are refused; in-band profiles refuse OOB approvals. Approval-request bundles are HMAC-signed with a 30-minute TTL and a recorded nonce; verification is fail-closed on decision currency, expiry, action hash, and attestation signature. Never-automate actions cannot create approval requests at all.

## Briefs and clocks

- Brief claims are **generated deterministically** from trusted, current, evidenced facts — one cited claim per fact, audience prefix filters, deltas since the last brief for that audience. No model writes prose.
- The **fact-checker gate** verifies provenance, citation currency and trust, evidence references, identifiers, timestamps, and counts. It re-runs at approval and again at send — a fact superseded between draft and send blocks the send.
- Approvals are human-only and expire after 30 minutes. Delivery is mock-only (`mock://briefs/<id>`); no adapter can reach an external channel and there is no auto-send path.
- **Clocks** are proposed as candidates by a pure engine (calendar, business-day, holiday, timezone rules) that stores a numbered computation trace — every deadline is reproducible. Confirmation requires a human legal/DPO attestation that re-validates the trigger fact.

## Dispatch and BCP

- **Owner resolution** walks a fixed, confidence-ranked fallback chain (CMDB → service catalog → on-call roster → HR directory → last assignee → team lead). Every source tried, skipped, or rejected is recorded as a step. Untrusted, disputed, or blank values are rejected and the rejection is recorded.
- **`unknown_owner` is a first-class outcome** — it routes acknowledgements to the IC and appears as an evidence gap in the handoff, never a silent empty owner.
- **Acks are human-only and SLA-tracked** by severity (sev1 15m → sev4 120m). Missed SLAs escalate deterministically (IC-owned escalates to the deputy IC). Nothing auto-closes.
- **BIA mappings** use only typed service facts; missing service/RTO/RPO/criticality become explicit gaps, never inferred values.
- **Readiness** treats missing or untrusted evidence as `unknown` and fails safe to manual mode. Identity evidence that is disputed or asserts compromise degrades the identity plane.

## The automation engine

Phase 5 wraps every action type in earned-autonomy guardrails:

- **Scorecards** per action over a rolling 30-day window (`autonomy-engine@1`): proposals, allow rate, simulated dry-runs, refusals, denies, escalations, expired approvals, breaker trips.
- **Levels** shadow → suggest → approve. **Promotion** requires thresholds (≥10 proposals, ≥80% allow rate, ≥5 simulated dry-runs, no trips, no demotion triggers) **and** `AUTONOMY_PROMOTION_ENABLED=true` (default off). **Demotion** is deterministic and never gated: denies or breaker trips drop to shadow; refusals or expired approvals drop one level.
- **Circuit breakers** trip per action after `BREAKER_THRESHOLD` consecutive execution refusals; reset is human-only.
- **Rate limits** cap simulated dry-runs per action per rolling hour.
- **Kill switch** — independent control with its own event, audit entry, and env-var override. Engaged, it refuses every approval and execution across all incidents instantly; advisory evaluation keeps working. Both engage and release require a human and a reason.

## Configuration profiles

| Profile | Approval channel | Use |
|---|---|---|
| `local/mock` (default) | in-band | Development, demo |
| `single-tenant` | in-band | Single-organization deployment |
| `out-of-band` | out-of-band | Approvals decided on an independent control plane |

High-privilege config (approval channels, policy versions, tiers) is versioned and audited. Deferred decisions carry a config schema and a feature flag, and are revisited at every phase gate — see the decision log in [BUILD_PLAN.md](../BUILD_PLAN.md).

## Testing strategy

72 tests, all against an isolated `adjutant_test` database (truncated per test):

- **Phase 1:** event append/replay, hash-chain tampering, prompt-injection corpus, dedupe, provenance round-trip.
- **Phase 2:** gate attacks (unsupported claims, superseded citations, judgment acks), business-day/holiday math, legal-confirmation guards.
- **Phase 3:** fallback ordering, untrusted/disputed rejection, unknown-owner routing, SLA escalation including IC→deputy, BIA gaps, readiness fail-safe, handoff counts.
- **Phase 4:** approval forgery (tampered payload, wrong key), replay (API + DB), expiry, hash mismatch, role matrix, never-automate fail-closed, live-execution refusal.
- **Phase 5:** promotion gating, deterministic demotion, kill-switch drill, breaker trip/reset, rate-limit refusal, OOB channel exclusivity and fail-closed verification, and five tabletop scenarios with the audit chain verified after each.

## Source map

| Path | What lives there |
|---|---|
| `src/adjutant/store.py` | All persistence: events, facts, proposals, approvals, executions, briefs, clocks, dispatch, automation |
| `src/adjutant/containment.py` | Action catalog, policy gate, approvals, executor, JIT broker |
| `src/adjutant/autonomy.py` | Scorecards, promotion/demotion, OOB signing/verification |
| `src/adjutant/clocks.py` | Pure clock engine with computation traces |
| `src/adjutant/comms.py` | Brief generation, fact-checker gate |
| `src/adjutant/dispatch.py` | Owner resolution, SLA evaluation |
| `src/adjutant/extractors.py` | Quarantine boundary |
| `src/adjutant/schema.sql` | Tables, triggers (append-only), indexes |
| `src/adjutant/seed.py` | Synthetic ransomware incident |
| `web/src/` | React UI (11 tabs, live-polling) |
