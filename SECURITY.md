# Security policy

## What this project is

Adjutant is a **synthetic-data demonstration** of an incident-coordination platform with an enforced trust model. It contains no real credentials, no real customer data, no live attack tooling, and no working external-communication path. All integrations are mocked; the executor refuses real actions.

## Security guarantees

The design enforces the following, each covered by tests (see [docs/architecture.md](docs/architecture.md)):

1. **Append-only audit trail** — events are hash-chained; updates and deletes are rejected by database triggers; `/audit/verify` detects tampering.
2. **Quarantined ingestion** — attacker-controlled input enters only as inert, untrusted facts through an allowlisted extractor; the LLM slot is tool-less, schema-strict, and network-isolated by contract.
3. **Provenance gate** — no claim or action without evidence references; untrusted, disputed, retracted, or superseded facts cannot justify an action.
4. **Human-only consequential actions** — approvals, acknowledgements, clock confirmations, sends, and executions reject `agent:`/`system:`/`bot:`/`model:` actors.
5. **Signed, expiring, single-use approvals** — bound to an exact action hash; replay is blocked at the database level; refusals never consume approvals.
6. **Dry-run-only execution** — real mode is refused unconditionally; the credential broker issues scope descriptors, never credentials.
7. **Never-automate list** — `wipe_host`, `disable_backup_jobs`, `pay_ransom` have no in-system approval path of any kind.
8. **Independent kill switch** — refuses every approval and execution across all incidents; env-var override survives application-level failure; human + reason required to engage and release.
9. **Fail-safe autonomy** — promotion requires scorecard thresholds *and* an opt-in config flag (default off); demotion is deterministic and ungated.

## Dev-only warnings (do not run this as-is in production)

- `MOCK_SIGNING_KEY` / `MOCK_OOB_SIGNING_KEY` defaults are **mock values printed with a do-not-use warning**. Real deployments must use KMS/HSM-backed keys — see [docs/production-guide.md](docs/production-guide.md), step 2.
- Docker Compose uses development Postgres credentials (`adjutant:adjutant`). Replace them per environment and never expose the stack publicly.
- The API currently has **no authentication layer**. Identity (SSO + passkeys) is production-guide step 1 and must land before any real data or real authority flows through the system.

## Reporting a vulnerability

This repository is a demonstration, but if you find a vulnerability in the trust model or its enforcement:

1. **Do not open a public issue** for anything that weakens the guarantees above.
2. Contact the maintainer directly: [Sanjeet Sharma on LinkedIn](https://www.linkedin.com/in/sanjeet-sharma-cissp-17b68570/).
3. Include reproduction steps and which guarantee is affected.

## Threat-model notes

The interesting attack surfaces, and how they are handled today:

| Surface | Handling |
|---|---|
| Prompt injection via signals | Quarantine: allowlisted deterministic extraction; LLM slot tool-less and schema-strict; output always untrusted |
| Approval forgery | HMAC over the exact action content + nonce + expiry; tampered payloads fail verification (tested) |
| Approval replay | Single-use, DB-level partial unique index; refused replays are recorded events (tested) |
| Privilege escalation via roles | Role matrix on the policy decision; role changes require a human approver of matching role |
| Destructive actions | Never-automate list has no in-system approval path; tier-3 requires IC and business-hours gate |
| Runaway automation | Per-action breakers, rate limits, deterministic demotion, independent kill switch |
| Audit tampering | Hash chain + trigger-guarded append-only + scheduled verification (production guide, step 7) |
