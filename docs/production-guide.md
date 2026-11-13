# Production integration guide

Adjutant is **demo-complete, production-deferred by design**. Everything below documents the path from this repository to a real deployment. The architecture was built so that every mock sits behind a port or a config value — productionizing is substitution, not surgery.

> **Trigger rule:** start this work only when there is a real deployment target (a pilot with one real integration). Building it speculatively adds risk and no value.

---

## Guiding invariants (do not break these while productionizing)

1. The AI proposes; humans decide — every gate stays human-only.
2. Append-only, hash-chained event log remains the single source of truth.
3. Dry-run remains the default for anything with side effects.
4. Never-automate actions never gain an in-system approval path.
5. The kill switch must always be able to stop everything, independent of the app.
6. No secrets in code; all configuration via environment/secret store.

---

## Step 1 — Identity and authority (do this first)

**Today:** the API is unauthenticated; approvers are named actors validated by role and human-prefix rules only.

**Required:**

- Put an identity provider (Entra ID / Okta / Keycloak) in front of the API — OIDC tokens on every request; map groups to the existing role matrix (`ic`, `security`, `exec`, `legal`, `comms`).
- Replace name-based approvals with **passkeys/WebAuthn** — the approval object interface is already passkey-ready; the signature currently carried by the mock HMAC key moves to the passkey assertion.
- Enforce step-up authentication for tier-2/3 approvals (fresh user verification required at approval time).
- Bind the API session to the incident context so approval authority can't be replayed across incidents.

**Definition of done:** an approval cannot be created without a cryptographically verified human identity; a role from the IdP is the only source of approver authority.

## Step 2 — Signing keys

**Today:** `mock-signing-key-do-not-use-in-production` and the OOB equivalent, in config defaults.

**Required:**

- Move approval and OOB signing to **KMS/HSM-backed keys** (Azure Key Vault, AWS KMS) — sign via API, never export key material.
- Key rotation procedure with a documented re-verification path for approvals signed under a previous key id (the `key_id` field already exists on approvals).
- Separate keys per environment; production never shares keys with staging.
- The kill switch should also freeze signing if engaged (fail closed).

**Definition of done:** no signing key material exists in the application process; key ids rotate without breaking verification.

## Step 3 — Real integrations (read-only first)

**Today:** `edr:mock`, `cmdb:mock`, `idp:mock`, `backup:mock`, `status:mock`, `network:mock` adapters.

**Required (in order):**

1. **CMDB** (read-only) — asset ownership, criticality, service mapping. Lowest risk; immediately exercises dispatch and BIA with real data.
2. **Identity provider** (read-only) — account status, session data for identity-plane readiness.
3. **EDR telemetry** (read-only) — signal ingest posts to `POST /incidents/{id}/signals`; the quarantine pipeline already treats it as untrusted.
4. **Backup / DR status** (read-only) — readiness planes.

Rules for every adapter:

- Implement the existing port; the store never learns the adapter's name.
- Adapter-out data enters **only** through the signal/fact API with provenance — adapters are sources, not writers.
- Timeouts and error states become `integration/<name>/status` facts (the readiness engine already degrades on them).
- Never let an adapter write facts with `trusted` directly — trust upgrades go through supersede by a verified source.

**Definition of done:** a real CMDB owner resolves through the fallback chain into a real dispatch assignment with a real human ack.

## Step 4 — The real executor

**Today:** dry-run-only; `dry_run=false` refused unconditionally; JIT broker issues scope descriptors.

**Required:**

- Stand up a separate **executor service** — the only component holding write credentials. Adjutant emits signed, approved action objects; the executor verifies signature, hash, expiry, and nonce before acting.
- Credentials: JIT, short-lived (minutes), action-scoped, minted from a secret store at execution time — never stored, never cached.
- Keep the dry-run simulation as a mandatory pre-step in production mode (evidence preservation first, as today's step order already enforces).
- Rollout per tier: tier-1 actions first (revoke sessions), then tier-2 (isolate, block), tier-3 actions only after a full tabletop against real infrastructure.
- Every execution result — success, failure, timeout — becomes an event.
- The kill switch and breakers must gate the executor service too (it checks the same projection / a signed switch state, not just the API).

**Definition of done:** a real isolation executed on a real host, evidence preserved, rollback path recorded, audit chain verified, kill switch able to halt mid-flight actions.

## Step 5 — Real comms

**Today:** briefs send to `mock://briefs/<id>`; handoffs are display-only.

**Required:**

- One real adapter (email / Teams / Slack) implementing the send port.
- The gate re-runs at send (already implemented) — keep it, add the adapter behind it.
- External sends remain human-approved, per-audience, with the classification check (restricted briefs cannot route to external channels).
- Handoffs stay display-only unless a phase explicitly decides otherwise.

**Definition of done:** an exec brief delivered to a real channel, gated, approved, audited — and a provable refusal for a restricted brief aimed at an external channel.

## Step 6 — The LLM adapter

**Today:** `ModelPort` has a schema-strict mock; the deterministic extractor handles most input.

**Required:**

- Implement the Azure OpenAI/Foundry adapter behind `ModelPort` — bounded slots only: residual-text extraction. No tools, no network egress beyond the model endpoint, no incident context beyond the single signal being extracted.
- Keep `MODEL_PROVIDER=mock` as the default; enable the real adapter per environment.
- Log extraction provenance (model, prompt version) as event metadata; the extractor's output is still untrusted-derived until superseded.
- Data residency: the model endpoint region must match the deployment's data-residency decision (deferred governance item).

**Definition of done:** an LLM-extracted fact is indistinguishable in handling from a deterministic one — untrusted, provenance-stamped, evidence-linked.

## Step 7 — Platform

**Today:** Docker Compose (app + Postgres + OPA) on one host.

**Required:**

- **Managed PostgreSQL** with HA, PITR backups, and restore drills. The event store is the crown jewels — test restores, not just backups.
- **TLS** everywhere (ingress + service-to-service); run the app non-root, read-only filesystem, dropped capabilities.
- **Secrets** in a managed store; compose-file credentials replaced per environment.
- **Monitoring/alerting:** audit-chain verification on a schedule (broken chain pages someone), kill-switch state changes page the IC, breaker trips and rate-limit saturations alert, SLA misses roll up to a dashboard.
- **Log retention** aligned with the privilege/retention model (governance item below).
- Load-test the event log write path — incident spikes are the usage spike.

**Definition of done:** a fresh environment reaches healthy from secrets + manifests alone; a restore drill succeeds; a tampered event trips an alert.

## Step 8 — Governance sign-offs (before go-live, not after)

| Item | Owner | Notes |
|---|---|---|
| Regulatory clock jurisdictions | Legal/DPO | The engine has CERT-In (6h) as a seed rule; add jurisdictions with counsel, confirm computation traces |
| Privilege & retention model | Legal + Security | Who may see restricted facts, how long evidence and events are kept |
| Threat model & pen test | Security | Especially: approval path, OOB channel, quarantine boundary, executor handoff |
| Kill-switch runbook | IC + Security | Who engages, who releases, drill cadence (quarterly), out-of-band path when the app is down |
| Auto-containment enablement | IC | Explicitly deferred — decide if/when any tier-1 action may execute without a human keystroke, and record it in the decision log |
| OOB topology | Security | `independent-control-plane` shipped; `same-tenant-degraded` remains deferred — decide for the deployment |

**Definition of done:** every row signed off and recorded as a decision-log entry in BUILD_PLAN.md.

---

## Suggested cut

| Slice | Scope | Outcome |
|---|---|---|
| **6a — Pilot** | Steps 1, 2, 7 + CMDB read-only | Real humans approve real briefs on real identity with real keys, real CMDB dispatch |
| **6b — Signals** | Step 3 (EDR, IdP), step 6 | Real telemetry into the quarantine pipeline, real readiness |
| **6c — Action** | Step 4, step 5 | Real containment (tier-1 first), real comms |
| **6d — Governance** | Step 8 | Go-live sign-offs |

Each slice ends with the tabletop suite re-run against the new reality.

---

## What must never be defaulted

These remain explicit human decisions, recorded in the decision log:

- Approval crypto and authority (passkeys, key custody)
- Regulatory scope and jurisdiction clocks
- Privilege, classification, and retention rules
- Auto-containment enablement
- Model provider and data residency
- Out-of-band topology choice
