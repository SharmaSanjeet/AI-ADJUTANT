# The agents

Adjutant's analytical work is done by **eight deterministic agents**. This page
is the per-agent deep dive: what each one does, what triggers it, what it
reads, what it writes into the event log, which UI tab shows its output, and —
most importantly — what it structurally cannot do.

> One-line summary: **agents propose, humans decide, and every agent output is
> an auditable event.**

## What "agent" means here

An Adjutant agent is not an LLM loop with tools. It is a **pure, deterministic
function over the fact base**: same facts in, same output out, replayable from
the event log at any time. That is a deliberate design choice — in an incident
you need advice you can audit, not advice you have to trust.

Shared invariants, enforced in code:

1. **Deterministic code, not model calls.** No agent calls an LLM. The only
   model slot in the entire platform is the quarantine extractor's schema-strict
   fallback — and it lives *before* the fact base, outside every agent.
2. **Read facts, write events.** Agents read only current facts recorded in the
   store, and their only write is an appended, hash-chained event with an
   `agent:<role>` source. You can trace exactly which agent did what in the
   timeline and audit log.
3. **No send path, no credentials.** No agent holds credentials, network
   access, or messaging capability. There is nothing for a prompt injection to
   steal or a runaway agent to send.
4. **Agents cannot act.** Consequential actions — brief approval, clock
   confirmation, dispatch acknowledgement, containment approval, handoff
   acknowledgement, kill-switch changes — **reject** actors with
   `agent:`/`system:`/`bot:`/`model:` prefixes by design.
5. **Every agent output ends at a human gate.** The table below is the map.

## At a glance

| Agent | Role | Emits (event) | UI tab | Next human gate |
|---|---|---|---|---|
| `agent:containment-advisor` | Tiered containment action proposals with cited evidence | `proposal.created` | Proposals · Containment | Approve (HMAC-signed, single-use) |
| `agent:scribe` | Draft audience briefs — one fully-cited claim per fact | `brief.drafted` | Briefs | Approve, then send |
| `agent:fact-checker` | Provenance gate on every brief draft | `brief.checked` | Briefs | FAILED blocks approval; NEEDS_REVIEW needs explicit acknowledgment |
| `agent:clock-advisor` | Regulatory deadline candidates with computation traces | `clock.candidate_recorded` | Clocks | Legal confirmation with attestation |
| `agent:dispatch` | Owner resolution + ack SLA escalation | `dispatch.resolved`, `dispatch.escalated` | Dispatch | Human acknowledgement |
| `agent:bia` | Asset → service → business impact mapping | `impact.mapped` | BCP | — (advisory input to BCP tab) |
| `agent:readiness` | DR plane + integration health assessment | `readiness.assessed` | BCP | — (advisory input to BCP tab) |
| `agent:handoff` | Shift handoff assembled from verified counts | `handoff.drafted` | Handoff | Receiving human acknowledges |

Every agent output path terminates in a human decision — approval, send,
confirmation, acknowledgement — or is purely advisory. None reaches the
outside world by itself.

## agent:containment-advisor

**What it does.** Turns assessment facts into tiered containment action
proposals (`T0`–`T3`), each with a fixed action from the catalog, parameters,
a target asset, and `justification_refs` pointing at the evidence that
motivated it.

- **Trigger** — `POST /incidents/{id}/proposals`; the seeded demo incident
  ships three proposals drafted by this agent.
- **Reads** — the action catalog (`GET /incidents/{id}/actions`), current
  assessment facts (impact, asset criticality, trust state).
- **Emits** — `proposal.created` with `proposed_by=agent:containment-advisor`.

**Guardrails.** A proposal is inert. Before anything happens it must pass the
policy gate — unknown actions denied, tier rules enforced, the never-automate
list, citation and freshness checks, untrusted-data escalation, out-of-hours
escalation — and then receive a **human approval** that is HMAC-signed,
single-use, expiring, and bound to the exact action hash. Execution is dry-run
only in this build, and the executor accepts only signed approved objects.

## agent:scribe

**What it does.** Drafts briefs per audience (IC, exec, legal, comms, …) from
the fact delta since the last brief to that audience. One claim per eligible
fact, with templated claim text — **no free-form prose is generated**, because
prose is where unsupported claims hide.

Eligibility is strict: the fact must be `trusted`, have evidence, be current
(not superseded/retracted/disputed-without-flag), and match the audience's
attribute prefixes.

- **Trigger** — `POST /incidents/{id}/briefs`.
- **Reads** — current facts filtered by audience scope; the timestamp of the
  previous brief to the same audience.
- **Emits** — `brief.drafted`.

**Guardrails.** If there are no new supported facts, the scribe refuses
(HTTP 409 "no new supported facts to brief") rather than padding. Long values
and long claims are dropped, not truncated into ambiguity. The draft goes
straight to the fact-checker — the scribe never sees a send path.

## agent:fact-checker

**What it does.** A deterministic provenance gate that runs at **draft time**,
can be re-run on demand, and **re-runs at approval and send** so a brief can
never slide through on a stale check. It re-reads the cited facts fresh from
the store and validates every claim:

| Check | Code |
|---|---|
| Claim cites no facts | `provenance_missing` |
| Cited fact doesn't exist | `fact_not_found` |
| Cited fact superseded/retracted | `fact_not_current` |
| Cited fact is untrusted | `trust_untrusted` |
| Cited fact has no evidence | `evidence_missing` |
| Evidence ref not attached to cited facts | `evidence_unknown` |
| Identifier/UUID in text not in cited facts | `identifier_unsupported` |
| Date in text not in cited facts' timestamps | `timestamp_unsupported` |
| Number in text not in cited facts | `number_unsupported` |
| Cites a disputed fact without flagging it | `disputed_not_flagged` |
| Judgment claim present | `judgment_requires_review` |

Verdicts: **PASS**, **NEEDS_REVIEW** (judgment or flagged issues — a human must
explicitly acknowledge review), **FAILED** (unsupported claim — approval is
refused outright).

- **Trigger** — automatically inside `POST /incidents/{id}/briefs`; on demand
  via `POST /incidents/{id}/briefs/{brief_id}/check`; re-run inside approve and
  send.
- **Reads** — the draft brief plus the cited facts, freshly loaded.
- **Emits** — `brief.checked`.

**Guardrails.** "No model judgment is trusted here" is the docstring. A FAILED
check cannot be overridden — approval raises HTTP 409. The send step re-checks
as well, so facts that went stale between approval and send are caught.

## agent:clock-advisor

**What it does.** Proposes regulatory clock candidates — trigger fact, due
date, and a full computation trace (business-day math, holidays) — from a rule
catalog (e.g. CERT-In's 6-hour reporting rule in the seed).

- **Trigger** — `POST /incidents/{id}/clocks` with a rule id and a trigger
  fact id (or explicit trigger time). A trigger fact must be current and
  trusted, or the request is refused.
- **Reads** — the clock rule catalog; the trigger fact's `valid_at`.
- **Emits** — `clock.candidate_recorded`, always with
  `requires_legal_confirmation=True`.

**Guardrails.** A clock that has not been legally **confirmed by a human with
a written attestation** drives nothing — it sits in `candidate` status. If the
trigger fact is later superseded or retracted, confirmation is refused and a
recompute is required. The advisor computes; counsel decides.

## agent:dispatch

**What it does.** Resolves the accountable owner for each affected asset by
walking a fixed, confidence-ordered fallback chain, and drafts the assignment
with an acknowledgement SLA scaled by incident severity. It also re-evaluates
pending assignments and records SLA breaches with escalation targets.

The fallback chain, in order:

1. CMDB asset owner
2. Service catalog: asset → service → service owner → service on-call
3. HR directory manager
4. Last known assignee
5. Service team lead

Every step is recorded — used, rejected (why), or missing — so the resolution
is fully explainable. Ties in confidence resolve to **ambiguous** and withhold
the owner; a chain with no candidates routes acknowledgements to the **incident
commander** (`unknown_owner`) rather than guessing.

- **Trigger** — `POST /incidents/{id}/dispatch/resolve` (per asset);
  `POST /incidents/{id}/dispatch/evaluate` re-checks pending acks.
- **Reads** — ownership/on-call facts, incident severity (SLA minutes).
- **Emits** — `dispatch.resolved` (steps + candidates + assignment),
  `dispatch.escalated` (advisory, names the escalation target).

**Guardrails.** Acknowledgement is human-only, with SLA-met computed from the
record. Escalation is a written recommendation in the event log — the agent
cannot page, message, or notify anyone.

## agent:bia

**What it does.** Maps affected assets to the services they carry and to
business impact, using recorded criticality/RTO/RPO facts — the material the
BCP tab renders.

- **Trigger** — `POST /incidents/{id}/impact`.
- **Reads** — asset facts, service mappings, criticality and RTO/RPO facts.
- **Emits** — `impact.mapped`.

**Guardrails.** Missing data becomes an explicit **gap**, never an inference.
If nobody recorded what service an asset carries, the BIA says so instead of
guessing a target.

## agent:readiness

**What it does.** Assesses disaster-recovery planes and integration health
from recorded checks and health facts — which planes can take a failover,
which integrations are currently verified.

- **Trigger** — `POST /incidents/{id}/readiness`.
- **Reads** — DR plane facts, integration health facts.
- **Emits** — `readiness.assessed`.

**Guardrails.** Plane status is derived only from recorded checks. An
integration that hasn't been verified reads as **unknown**, never "healthy".
The latest assessment feeds the BCP tab and the handoff brief.

## agent:handoff

**What it does.** Assembles the end-of-shift handoff from **verified counts
queried from the store** — open approvals, open acknowledgements, evidence
gaps, pending clocks, latest readiness, check results — plus a summary and
title. The incoming commander gets state, not narration.

- **Trigger** — `POST /incidents/{id}/handoff`.
- **Reads** — everything: incident, facts, briefs, proposals, clocks,
  dispatch records, impact mappings, latest readiness.
- **Emits** — `handoff.drafted`.

**Guardrails.** Display-only: the handoff cannot send anything, to anyone. The
receiving human acknowledges it for the record (`handoff.acknowledged`), which
is the one human gate on this path.

## The automation layer is not an agent

The Phase 5 autonomy engine (shadow → suggest → approve per action type,
circuit breakers, rate limits, kill switch, scorecards) is a **guard wrapper**
around the advisory → approval → execution chain — and it obeys the same rule.
Auto-suggestions are advisory only; only a human can approve an action or raise
an autonomy level (promotion requires both scorecard thresholds *and* a config
flag that defaults off); demotions are deterministic. The kill switch stops
every approval and execution path instantly and independently of the app.

## Where the code lives

| Component | File |
|---|---|
| Scribe (claim building) + fact-checker | `src/adjutant/comms.py` |
| Clock computation | `src/adjutant/clocks.py` |
| Dispatch resolution, SLA, escalation, BIA, readiness, handoff | `src/adjutant/dispatch.py` |
| Action catalog, policy gate, approvals, executor | `src/adjutant/containment.py` |
| Quarantine extractor (the only LLM slot — outside the agents) | `src/adjutant/extractors.py` |
| Store functions that invoke agents and append their events | `src/adjutant/store.py` |
| Demo incident's pre-drafted agent outputs | `src/adjutant/seed.py` |

See [architecture.md](architecture.md) for the trust skeleton underneath all
of this — event store, facts, policy gate, approvals — and
[production-guide.md](production-guide.md) for what changes when these become
model-assisted in a real deployment (spoiler: the gate structure stays, the
agents' determinism contract is revisited explicitly, per slot).
