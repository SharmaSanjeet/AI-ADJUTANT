<div align="center">

# ADJUTANT

### The Incident Commander's chief of staff

**by Sanjeet Sharma** · CISSP · [LinkedIn](https://www.linkedin.com/in/sanjeet-sharma-cissp-17b68570/)

*Event-sourced incident coordination where the AI proposes and humans decide.*

![Python](https://img.shields.io/badge/python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-05966B?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Tests](https://img.shields.io/badge/tests-72%20passing-22C55E)
![License](https://img.shields.io/badge/license-MIT-8B5CF6)

</div>

---

## The problem this solves

Anyone who has commanded a serious incident knows the real fight isn't the attacker — it's coordination chaos:

- **Facts are scattered.** Evidence lives in EDR consoles, CMDB exports, email threads, and chat screenshots — with no way to know what's trusted, what's disputed, or what's current.
- **Nobody knows who owns the asset.** "Who's the owner of FIN-WS-0142?" turns into 20 minutes of asking around while the clock runs.
- **Status comms drift from reality.** Executive updates are hand-typed under pressure and quietly diverge from the evidence.
- **Containment is a gamble.** Isolating a payment server during month-end settlement, wiping a host before forensics — decisions made in seconds that cost millions.
- **Nobody can reconstruct the incident.** What did we know, when, from whom, and who decided what? After-action reviews run on memory.
- **AI assistants make it worse.** A helpful LLM with tools can hallucinate a fact, send a report, or "just isolate the host" — and nobody can prove afterwards why it happened.

## What Adjutant is

Adjutant is a **coordination layer for incident commanders** — a chief of staff that ingests signals, maintains a provable fact ledger, drafts audience briefs, resolves asset owners, proposes containment actions, tracks regulatory clocks, and assembles shift handoffs.

The design rule enforced in code at every step: **the AI proposes; humans decide.** Every agent in the system is deterministic and advisory. Approvals, acknowledgements, clock confirmations, sends, and executions are human-only — enforced by rejecting agent actors, signing approvals, and refusing anything with real side effects.

> **The trust skeleton is real; the integrations are deliberately mocked.** Adjutant ships with mock adapters (EDR, CMDB, IdP, comms) and a dry-run-only executor, so the entire safety model can be exercised without touching a real system. [Production integration](docs/production-guide.md) is a documented, deferred path.

## How it works

```mermaid
flowchart LR
    A[Signal<br/>EDR · CMDB · email] --> B[Quarantine<br/>allowlisted extraction]
    B --> C[Typed facts<br/>trust + provenance + status]
    C --> D[Fact ledger<br/>bitemporal · supersedeable]
    D --> E1[Briefs<br/>fact-checker gate]
    D --> E2[Regulatory clocks<br/>legal confirmation]
    D --> E3[Dispatch<br/>owner resolution + SLA]
    D --> E4[Containment advisor<br/>policy gate]
    D --> E5[BIA · readiness<br/>handoff]
    E1 --> F{Human gates}
    E2 --> F
    E3 --> F
    E4 --> F
    F --> G[Hash-chained<br/>audit log]
```

Every arrow lands in an **append-only, hash-chained event log**. Reports, briefs, and dashboards are projections — rebuild the events, get the same state.

### The containment gate chain

The most consequential path is containment, and it runs through four locks:

1. **Propose** — the containment advisor (deterministic) raises a tiered action with cited evidence. Advisory only.
2. **Policy gate** — deterministic Allow / Deny / Escalate over a versioned action catalog: unknown actions and tier mismatches deny; never-automate actions, disputed or untrusted citations, and out-of-hours windows escalate.
3. **Human approval** — HMAC-signed (passkey-ready interface), expires in 15 minutes, binds to an action hash, single-use at the database level.
4. **Dry-run executor** — simulates evidence preservation first, records a rollback path, and obtains a scope *descriptor* (never a credential) from a JIT broker. `dry_run=false` is refused unconditionally.

Never-automate actions (`wipe_host`, `disable_backup_jobs`, `pay_ransom`) escalate with **no in-system approval path of any kind** — the decision happens entirely outside Adjutant.

## Screenshots

<div align="center">
<table>
<tr>
<td width="50%"><img src="docs/images/01-facts-dashboard.png" alt="Fact ledger and event timeline"/><p align="center"><sub>Fact ledger — provenance, confidence, trust on every fact</sub></p></td>
<td width="50%"><img src="docs/images/02-containment-gate.png" alt="Containment policy gate"/><p align="center"><sub>Containment gate — catalog, policy reasons, signed approvals</sub></p></td>
</tr>
<tr>
<td width="50%"><img src="docs/images/05-dispatch-board.png" alt="Dispatch board"/><p align="center"><sub>Dispatch — owner resolution trace, human-only acks, SLA escalation</sub></p></td>
<td width="50%"><img src="docs/images/06-bia-readiness.png" alt="BIA and readiness"/><p align="center"><sub>BIA + DR readiness — gaps reported, never guessed</sub></p></td>
</tr>
</table>

<img src="docs/images/adjutant-tour.gif" alt="Adjutant product tour" width="820"/>

</div>

## Quickstart

```bash
docker compose up --build
```

| What | Where |
|---|---|
| Operations UI | http://localhost:8010/ui |
| API | http://localhost:8010 |
| Interactive API docs | http://localhost:8010/docs |
| Health | http://localhost:8010/health |

A **synthetic ransomware incident** (`FIN-WS-0142`) is seeded on first start — no real data, no external calls, nothing to configure. New here? [Walk the demo incident in the UI](docs/ui-guide.md) — the click-by-click tour.

## Usage guide

### The UI, tab by tab

| Tab | What you see | The human gate |
|---|---|---|
| **Facts** | The typed fact ledger — provenance, confidence tuple, trust, status, supersedes links | — |
| **Decisions** | The decision log — decisions are first-class facts with provenance | — |
| **Proposals** | Advisory action proposals with cited evidence | — |
| **Containment** | Catalog details, policy-gate reasons, signed approvals, dry-run execution | Approve + execute |
| **Signals** | Raw quarantined input — stored untrusted, never trusted by default | — |
| **Briefs** | Audience-tailored briefs with claims, gate issues, approval and send | Approve + send |
| **Clocks** | Regulatory deadlines with full computation traces | Legal/DPO confirm |
| **Dispatch** | Owner resolution traces, acknowledgements, SLA timers | Ack |
| **BCP** | BIA mappings (RTO/RPO with gaps) and DR readiness per plane | — |
| **Handoff** | Shift handoff with verified counts — display-only | Acknowledge |
| **Auto** | Automation posture: kill switch, circuit breakers, rate limits, autonomy scorecards | Engage/release, resets |

### API walkthrough

Explore the seeded incident:

```bash
curl http://localhost:8010/incidents
curl http://localhost:8010/incidents/<incident_id>/timeline
curl http://localhost:8010/incidents/<incident_id>/facts
curl http://localhost:8010/incidents/<incident_id>/signals
curl http://localhost:8010/incidents/<incident_id>/decisions
curl http://localhost:8010/incidents/<incident_id>/proposals
curl http://localhost:8010/incidents/<incident_id>/briefs
curl http://localhost:8010/incidents/<incident_id>/clocks
curl http://localhost:8010/incidents/<incident_id>/dispatch
curl http://localhost:8010/incidents/<incident_id>/impact
curl http://localhost:8010/incidents/<incident_id>/readiness
curl http://localhost:8010/incidents/<incident_id>/handoff
curl http://localhost:8010/incidents/<incident_id>/containment
curl http://localhost:8010/incidents/<incident_id>/actions
curl http://localhost:8010/automation/status
curl http://localhost:8010/automation/scorecards
curl http://localhost:8010/audit/verify
```

Ingest a signal (attacker-controlled content stays untrusted):

```bash
curl -X POST http://localhost:8010/incidents/<incident_id>/signals \
  -H 'Content-Type: application/json' \
  -d '{"kind":"edr","source":"edr:mock","content":"{\"host\":\"FIN-WS-0142\",\"action\":\"file_encrypt\"}"}'
```

Draft, gate, approve, and mock-send a brief:

```bash
BRIEF=$(curl -s -X POST http://localhost:8010/incidents/<incident_id>/briefs \
  -H 'Content-Type: application/json' \
  -d '{"audience":"exec"}' | python -c 'import json,sys; print(json.load(sys.stdin)["brief"]["id"])')

curl -X POST http://localhost:8010/incidents/<incident_id>/briefs/$BRIEF/check
curl -X POST http://localhost:8010/incidents/<incident_id>/briefs/$BRIEF/approve \
  -H 'Content-Type: application/json' \
  -d '{"approver":"priya.nair","approver_role":"ic","review_acknowledged":true}'
curl -X POST http://localhost:8010/incidents/<incident_id>/briefs/$BRIEF/send \
  -H 'Content-Type: application/json' \
  -d '{"requested_by":"priya.nair"}'
```

Resolve ownership, acknowledge, and evaluate SLAs:

```bash
curl -X POST http://localhost:8010/incidents/<incident_id>/dispatch/resolve \
  -H 'Content-Type: application/json' \
  -d '{"asset":"FIN-SRV-0007"}'
curl -X POST http://localhost:8010/incidents/<incident_id>/dispatch/<assignment_id>/ack \
  -H 'Content-Type: application/json' \
  -d '{"acked_by":"priya.raman"}'
curl -X POST http://localhost:8010/incidents/<incident_id>/dispatch/evaluate
```

Confirm a regulatory clock (legal/DPO attestation required):

```bash
curl -X POST http://localhost:8010/incidents/<incident_id>/clocks/<clock_id>/confirm \
  -H 'Content-Type: application/json' \
  -d '{"confirmed_by":"meera.rao","role":"legal","attestation":true}'
```

### Automation drills

Kill switch — blocks every approval and execution across all incidents instantly:

```bash
curl -X POST http://localhost:8010/automation/kill-switch \
  -H 'Content-Type: application/json' \
  -d '{"engaged":true,"actor":"priya.nair","reason":"containment drill"}'
# ... approvals and executions now refuse ...
curl -X POST http://localhost:8010/automation/kill-switch \
  -H 'Content-Type: application/json' \
  -d '{"engaged":false,"actor":"priya.nair","reason":"drill over"}'
```

Reset a circuit breaker (human-only; breakers trip after repeated execution refusals):

```bash
curl -X POST http://localhost:8010/automation/breakers/isolate_endpoint/reset \
  -H 'Content-Type: application/json' \
  -d '{"actor":"priya.nair","note":"drill reset"}'
```

Set an action's autonomy level (promotion is refused unless `AUTONOMY_PROMOTION_ENABLED=true`):

```bash
curl -X POST http://localhost:8010/automation/levels/isolate_endpoint \
  -H 'Content-Type: application/json' \
  -d '{"level":"suggest","actor":"priya.nair","reason":"scorecard thresholds met"}'
```

Out-of-band approval drill (requires `CONFIG_PROFILE=out-of-band` to accept the final approval):

```bash
curl -X POST http://localhost:8010/incidents/<incident_id>/proposals/<proposal_id>/approval-request
curl -X POST http://localhost:8010/automation/mock-oob-sign \
  -H 'Content-Type: application/json' \
  -d '{"bundle_id":"<bundle_id>"}'
curl -X POST http://localhost:8010/incidents/<incident_id>/proposals/<proposal_id>/approve-oob \
  -H 'Content-Type: application/json' \
  -d '{"bundle_id":"<bundle_id>","approver":"priya.nair","approver_role":"ic","attestation_signature":"<signature>"}'
```

## Security model

The guarantees that make the demo trustworthy — enforced in code, covered by 72 tests:

- **Append-only, hash-chained events.** Updates and deletes are rejected by database triggers; tampering breaks verification (`/audit/verify`).
- **Quarantined ingestion.** Raw, attacker-controlled input is stored untrusted; deterministic allowlisted extraction runs first; the LLM extractor (tool-less, schema-strict, no network) only sees residual text and only produces untrusted-derived facts.
- **Provenance on everything.** Every fact carries source, valid/recorded times, a confidence tuple, status, classification, trust marker, evidence references, and a supersedes link.
- **Deterministic agents.** All eight agents are pure code — same inputs, same outputs, replayable from the event log. Per-agent deep dive: [docs/agents.md](docs/agents.md).
- **Human-only consequential actions.** Approvals, acks, clock confirmations, sends, and executions reject `agent:`/`system:`/`bot:`/`model:` actors.
- **Signed, expiring, single-use approvals.** Bound to an exact action hash; replay blocked by a partial unique index; refusals never consume an approval.
- **Dry-run-only execution.** Real mode is refused unconditionally; evidence preservation is simulated first; the JIT broker issues scope descriptors, never credentials.
- **Never-automate list.** `wipe_host`, `disable_backup_jobs`, `pay_ransom` have no in-system approval path — in-band *or* out-of-band.
- **Independent kill switch.** Own event, own audit entry, env-var override; refuses every approval and execution instantly; human + reason required to engage *and* release.
- **Per-action autonomy with fail-safe defaults.** Shadow → suggest → approve levels; promotion needs scorecard thresholds **and** a config flag that defaults off; demotion is deterministic and never gated.
- **Earned trust upgrades only.** Untrusted facts become usable only when a trusted source explicitly supersedes them.

Full guarantee list per phase: [BUILD_PLAN.md](BUILD_PLAN.md) · Deep architecture: [docs/architecture.md](docs/architecture.md) · The agents: [docs/agents.md](docs/agents.md) · UI walkthrough: [docs/ui-guide.md](docs/ui-guide.md) · Security policy: [SECURITY.md](SECURITY.md)

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql://adjutant:adjutant@localhost:5432/adjutant` | Postgres connection (dev default) |
| `SEED_DEMO` | `true` | Seed the synthetic ransomware incident when the DB is empty |
| `APP_ENV` | `local` | Deployment environment label |
| `MODEL_PROVIDER` | `mock` | Extractor model port (`mock` until a real adapter is wired) |
| `CONFIG_PROFILE` | `local/mock` | `local/mock` · `single-tenant` · `out-of-band` — the OOB profile refuses in-band approvals |
| `OOB_TOPOLOGY` | `independent-control-plane` | Out-of-band approval topology |
| `KILL_SWITCH` | `false` | Environment-level kill-switch override (DB row is the primary control) |
| `RATE_LIMIT_PER_HOUR` | `5` | Max simulated executions per action per rolling hour |
| `BREAKER_THRESHOLD` | `3` | Consecutive execution refusals that trip a breaker |
| `AUTONOMY_PROMOTION_ENABLED` | `false` | Fail-safe default: no autonomy promotion without explicit opt-in |
| `MOCK_SIGNING_KEY` | dev-only value | **Mock approval-signing key — replace in production** |
| `MOCK_OOB_SIGNING_KEY` | dev-only value | **Mock OOB-signing key — replace in production** |

## Testing

```bash
docker compose run --rm app pytest -q
```

**72 tests**, including a prompt-injection corpus, forgery/replay/expiry approval attacks, SLA escalation, business-day/holiday clock math, kill-switch and breaker drills, out-of-band channel exclusivity, and five tabletop scenarios (ransomware, insider exfiltration, supply-chain IOC, DR-plane compromise, IdP compromise) — with the audit chain re-verified after every scenario. Tests run against an isolated `adjutant_test` database.

## Production integration guide

Adjutant is **demo-complete, production-deferred by design**. The path from here to a real deployment is documented step by step — identity, KMS-backed signing, real integrations behind the existing ports, the real executor, comms, the LLM adapter, platform hardening, and governance sign-offs:

**[docs/production-guide.md](docs/production-guide.md)**

## Architecture

Event store, bitemporal facts, the trust model, the gate chain, projections, the automation engine, and every design decision with its rationale:

**[docs/architecture.md](docs/architecture.md)** · **[BUILD_PLAN.md](BUILD_PLAN.md)** (phases + decision log)

## Roadmap

- **Phase 6 — Hardening** (deferred until a real deployment target): identity/passkeys, KMS signing, real integrations, real executor, real comms, LLM adapter, managed platform, governance.
- Same-tenant degraded out-of-band topology (independent control plane shipped).
- Additional regulatory clock jurisdictions beyond the CERT-In seed rule.

## Author

Built by **Sanjeet Sharma** (CISSP) — security leader, creator of AI-Forensics.

[![LinkedIn](https://img.shields.io/badge/LinkedIn-sanjeet--sharma--cissp-0A66C2?logo=linkedin&logoColor=white)](https://www.linkedin.com/in/sanjeet-sharma-cissp-17b68570/)

## License

[MIT](LICENSE)
