"""Phase 4 containment advisor: action catalog, policy gate, approvals, executor.

Everything in this module is deterministic and advisory. The executor only
simulates; no adapter exists that can reach a real endpoint, and the JIT
credential broker returns scope descriptors only — never credential material.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, time, timedelta, timezone
from typing import Any
from uuid import uuid4

from .models import (
    ActionCatalogEntry,
    ActionProposal,
    Approval,
    ApprovalCreate,
    CredentialGrant,
    ExecutionStep,
    Fact,
    FactStatus,
    FactTrust,
    PolicyDecision,
)

CATALOG_VERSION = "action-catalog@1"
POLICY_VERSION = "policy-engine@1"
EXECUTOR_VERSION = "executor@1"
CREDENTIAL_BROKER = "mock-jit-broker@1"
SIGNER_KEY_ID = "mock-hmac-sha256-v1"
DEFAULT_SIGNING_KEY = "mock-signing-key-do-not-use-in-production"
APPROVAL_TTL_MINUTES = 15
CREDENTIAL_TTL_SECONDS = 300
BUSINESS_HOURS_START = time(8, 0)
BUSINESS_HOURS_END = time(18, 0)

ACTION_CATALOG: dict[str, ActionCatalogEntry] = {
    "revoke_active_sessions": ActionCatalogEntry(
        action_id="revoke_active_sessions",
        title="Revoke active sessions",
        description=(
            "Invalidate all active authentication sessions for the affected "
            "identity, forcing re-authentication on every device."
        ),
        tier=1,
        blast_radius=(
            "Single identity: the account owner is logged out everywhere; "
            "no data is changed."
        ),
        rollback=["Sessions re-establish on next login; no rollback needed."],
        evidence_preservation=[
            "Snapshot the current session list for the identity before revocation.",
            "Export recent authentication logs for the identity to the evidence store.",
        ],
        preconditions=[
            "Identity and exposure status are evidenced by trusted facts.",
            "IdP integration is operational.",
        ],
        write_scope="idp:sessions:revoke:{asset}",
    ),
    "disable_service_account": ActionCatalogEntry(
        action_id="disable_service_account",
        title="Disable service account",
        description=(
            "Disable the service account observed in the incident so it can "
            "no longer authenticate. Business-hours restricted because the "
            "account may back production batch jobs."
        ),
        tier=1,
        blast_radius=(
            "Single account: jobs and integrations using it will fail until "
            "it is re-enabled."
        ),
        rollback=["Re-enable the account from the directory admin console."],
        evidence_preservation=[
            "Capture the account's current group memberships and consent grants.",
            "Export the account's recent sign-in logs to the evidence store.",
        ],
        preconditions=[
            "Account exposure is evidenced by a trusted, current fact.",
            "Directory integration is operational.",
        ],
        write_scope="directory:accounts:disable:{asset}",
        business_hours_only=True,
    ),
    "isolate_endpoint": ActionCatalogEntry(
        action_id="isolate_endpoint",
        title="Isolate endpoint",
        description=(
            "Place the endpoint in EDR network isolation: all traffic is "
            "blocked except the EDR management channel."
        ),
        tier=2,
        blast_radius=(
            "Single host: remote users lose access and host-initiated "
            "services stop; forensic reachability is preserved."
        ),
        rollback=["Release the host from isolation in the EDR console."],
        evidence_preservation=[
            "Capture volatile memory triage data before isolation.",
            "Record the host's active connections snapshot to the evidence store.",
        ],
        preconditions=[
            "Endpoint behaviour is evidenced by a trusted fact.",
            "EDR integration is operational.",
        ],
        write_scope="edr:endpoints:isolate:{asset}",
    ),
    "block_domain": ActionCatalogEntry(
        action_id="block_domain",
        title="Block attacker domain",
        description=(
            "Block the attacker-controlled domain at the egress firewall for "
            "all users. Broader than a single host, so it stays in tier 2."
        ),
        tier=2,
        blast_radius=(
            "All users on the egress path lose access to the domain; "
            "legitimate traffic to it stops."
        ),
        rollback=["Remove the firewall rule; egress resumes within minutes."],
        evidence_preservation=[
            "Export DNS and proxy logs covering the domain for the last 7 days.",
            "Snapshot the firewall rule set before adding the block.",
        ],
        preconditions=[
            "The domain is evidenced by a trusted fact with a clear source.",
        ],
        write_scope="firewall:egress:block:{asset}",
    ),
    "wipe_host": ActionCatalogEntry(
        action_id="wipe_host",
        title="Wipe and reimage host",
        description=(
            "Securely erase and reimage the endpoint. Destructive and "
            "irreversible: on the never-automate list, so Adjutant will "
            "always escalate it to a human decision made outside this system."
        ),
        tier=3,
        blast_radius=(
            "Total data loss on the host unless forensic images are taken "
            "first."
        ),
        rollback=["None. A wipe cannot be undone."],
        evidence_preservation=[
            "Completed forensic disk image stored and hash-verified.",
            "Memory capture completed and hash-verified.",
        ],
        preconditions=[
            "Forensic preservation explicitly signed off by the IC.",
        ],
        write_scope="endpoint:management:wipe:{asset}",
        never_automate=True,
    ),
    "disable_backup_jobs": ActionCatalogEntry(
        action_id="disable_backup_jobs",
        title="Disable backup jobs",
        description=(
            "Pause backup schedules, e.g. to stop an attacker using backup "
            "agents for lateral movement. Destructive to recovery posture: "
            "never-automate."
        ),
        tier=3,
        blast_radius=(
            "Recovery point objectives are no longer met while jobs are "
            "disabled."
        ),
        rollback=["Re-enable schedules; run a verification job afterwards."],
        evidence_preservation=[
            "Export the current backup schedule and last run states.",
        ],
        preconditions=[
            "Backup integrity evidenced as still trusted.",
        ],
        write_scope="backup:schedules:disable:{asset}",
        never_automate=True,
    ),
    "pay_ransom": ActionCatalogEntry(
        action_id="pay_ransom",
        title="Pay ransom",
        description=(
            "Any payment or negotiation step. Prohibited: Adjutant never "
            "proposes, approves, or executes payments, and always escalates."
        ),
        tier=3,
        blast_radius=(
            "Legal, regulatory, and financial exposure; may violate "
            "sanctions law."
        ),
        rollback=["None. Payments are irreversible."],
        evidence_preservation=[
            "Preserve the ransom note and communication channel as evidence.",
        ],
        preconditions=[
            "Legal counsel engaged outside Adjutant.",
        ],
        write_scope="none",
        never_automate=True,
    ),
}


def get_action(action_id: str) -> ActionCatalogEntry | None:
    return ACTION_CATALOG.get(action_id)


def catalog() -> list[ActionCatalogEntry]:
    return [ACTION_CATALOG[key] for key in sorted(ACTION_CATALOG)]


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def action_hash(proposal: ActionProposal) -> str:
    """Bind an approval to the exact proposal it covers."""
    body = {
        "incident_id": str(proposal.incident_id),
        "proposal_id": str(proposal.id),
        "action_id": proposal.action_id,
        "target_asset": proposal.target_asset,
        "params": proposal.params,
        "tier": proposal.tier,
        "catalog_version": CATALOG_VERSION,
    }
    digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    return "sha256:" + digest


def is_business_hours(now: datetime) -> bool:
    local = now.astimezone(timezone.utc)
    if local.weekday() >= 5:
        return False
    return BUSINESS_HOURS_START <= local.time() < BUSINESS_HOURS_END


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def approval_core(approval: Approval) -> dict[str, Any]:
    return {
        "approval_id": str(approval.id),
        "incident_id": str(approval.incident_id),
        "proposal_id": str(approval.proposal_id),
        "action_id": approval.action_id,
        "approver": approval.approver,
        "approver_role": approval.approver_role,
        "decided_at": _iso(approval.decided_at),
        "expires_at": _iso(approval.expires_at),
        "nonce": approval.nonce,
        "action_hash": approval.action_hash,
    }


def sign_payload(payload: dict[str, Any], key: str) -> str:
    mac = hmac.new(
        key.encode("utf-8"),
        canonical_json(payload).encode("utf-8"),
        hashlib.sha256,
    )
    return "hmac-sha256:" + mac.hexdigest()


def verify_signature(payload: dict[str, Any], signature: str, key: str) -> bool:
    return hmac.compare_digest(sign_payload(payload, key), signature)


def sign_approval_record(
    proposal: ActionProposal,
    decision: PolicyDecision,
    data: ApprovalCreate,
    now: datetime,
    key: str,
) -> Approval:
    """Create a signed approval.

    The mock HMAC key stands in for a hardware-backed passkey/WebAuthn
    signature; the interface (key id, nonce, expiry, canonical payload) is
    what a real signing provider would satisfy.
    """
    approval = Approval(
        id=uuid4(),
        incident_id=proposal.incident_id,
        proposal_id=proposal.id,
        action_id=proposal.action_id,
        approver=data.approver,
        approver_role=data.approver_role,
        decision="approved",
        decided_at=now,
        expires_at=now + timedelta(minutes=APPROVAL_TTL_MINUTES),
        nonce=uuid4().hex,
        action_hash=decision.action_hash,
        signature="",
        key_id=SIGNER_KEY_ID,
        note=data.note,
    )
    approval.signature = sign_payload(approval_core(approval), key)
    return approval


def check_approval(
    approval: Approval,
    proposal: ActionProposal,
    decision: PolicyDecision | None,
    now: datetime,
    key: str,
) -> list[str]:
    """Return refusal reasons; an empty list means the approval is valid."""
    reasons: list[str] = []
    if decision is None:
        reasons.append("no policy decision exists for this proposal")
    elif decision.decision != "allow":
        reasons.append(
            f"policy decision is '{decision.decision}'; "
            "only 'allow' proposals can be executed"
        )
    elif approval.action_hash != decision.action_hash:
        reasons.append("approval action hash does not match the current decision")
    if approval.proposal_id != proposal.id:
        reasons.append("approval belongs to a different proposal")
    if approval.action_hash != action_hash(proposal):
        reasons.append("proposal changed after approval; action hash mismatch")
    if now > approval.expires_at:
        reasons.append(f"approval expired at {_iso(approval.expires_at)}")
    if not verify_signature(approval_core(approval), approval.signature, key):
        reasons.append("approval signature does not verify against the mock key")
    return reasons


def evaluate_policy(
    proposal: ActionProposal, facts: list[Fact], now: datetime
) -> PolicyDecision:
    """Deterministic Allow / Deny / Escalate over the action catalog.

    First failing rule wins. Every outcome records its reasons so the
    decision is auditable and reproducible from the same inputs.
    """
    entry = ACTION_CATALOG.get(proposal.action_id)
    digest = action_hash(proposal)

    def decision(
        outcome: str, reasons: list[str], allowed_roles: list[str]
    ) -> PolicyDecision:
        return PolicyDecision(
            id=uuid4(),
            incident_id=proposal.incident_id,
            proposal_id=proposal.id,
            decision=outcome,
            reasons=reasons,
            required_approvals=1,
            allowed_roles=allowed_roles,
            action_hash=digest,
            policy_version=POLICY_VERSION,
            evaluated_at=now,
            evaluator=POLICY_VERSION,
        )

    if entry is None:
        return decision(
            "deny",
            [f"action '{proposal.action_id}' is not in the action catalog"],
            [],
        )

    if proposal.tier != entry.tier:
        return decision(
            "deny",
            [
                f"proposal tier {proposal.tier} does not match catalog tier "
                f"{entry.tier} for '{entry.action_id}'"
            ],
            [],
        )

    if entry.never_automate:
        return decision(
            "escalate",
            [
                "action is on the never-automate list; it cannot be approved "
                "or executed inside Adjutant and requires a human decision "
                "made outside this system"
            ],
            [],
        )

    allowed_roles = ["security", "ic"] if entry.tier == 1 else ["ic"]

    if not proposal.justification_refs:
        return decision(
            "escalate",
            ["no cited facts justify this action"],
            allowed_roles,
        )

    by_id = {fact.id: fact for fact in facts}
    missing = [ref for ref in proposal.justification_refs if ref not in by_id]
    if missing:
        return decision(
            "escalate",
            [f"{len(missing)} cited fact(s) do not exist in this incident"],
            allowed_roles,
        )

    cited = [by_id[ref] for ref in proposal.justification_refs]
    stale = [
        fact
        for fact in cited
        if fact.status in (FactStatus.DISPUTED, FactStatus.RETRACTED, FactStatus.SUPERSEDED)
    ]
    if stale:
        return decision(
            "escalate",
            [
                f"{len(stale)} cited fact(s) are disputed, retracted, or "
                "superseded"
            ],
            allowed_roles,
        )

    untrusted = [fact for fact in cited if fact.trust == FactTrust.UNTRUSTED]
    if untrusted:
        return decision(
            "escalate",
            [
                f"{len(untrusted)} cited fact(s) derive from untrusted data "
                "and cannot justify an action"
            ],
            allowed_roles,
        )

    if entry.business_hours_only and not is_business_hours(now):
        return decision(
            "escalate",
            [
                "action is restricted to business hours "
                "(Mon-Fri 08:00-18:00 UTC); escalate for out-of-hours approval"
            ],
            allowed_roles,
        )

    target = proposal.target_asset
    if not any(
        attribute.split("/")[1:2] == [target] for attribute in
        (fact.attribute for fact in facts)
    ):
        return decision(
            "escalate",
            [
                f"no recorded facts reference target asset "
                f"'{proposal.target_asset}'"
            ],
            allowed_roles,
        )

    return decision(
        "allow",
        [
            f"catalog entry '{entry.action_id}' matched with "
            f"{len(cited)} current, trusted citation(s)"
        ],
        allowed_roles,
    )


def build_execution_plan(
    entry: ActionCatalogEntry, proposal: ActionProposal
) -> list[ExecutionStep]:
    """Simulated plan: evidence preservation first, then the action."""
    steps: list[ExecutionStep] = []
    for instruction in entry.evidence_preservation:
        steps.append(
            ExecutionStep(
                name="preserve-evidence",
                status="simulated",
                detail=instruction,
            )
        )
    steps.append(
        ExecutionStep(
            name=f"action:{entry.action_id}",
            status="simulated",
            detail=(
                f"Dry run of '{entry.title}' on {proposal.target_asset}. "
                f"{entry.description}"
            ),
        )
    )
    if entry.rollback:
        steps.append(
            ExecutionStep(
                name="rollback-path",
                status="simulated",
                detail=" | ".join(entry.rollback),
            )
        )
    return steps


def mint_credential(
    entry: ActionCatalogEntry, proposal: ActionProposal
) -> CredentialGrant:
    """Mock JIT broker: returns a scope descriptor, never a credential."""
    return CredentialGrant(
        scope=entry.write_scope,
        ttl_seconds=CREDENTIAL_TTL_SECONDS,
        purpose=f"{proposal.action_id}:{proposal.target_asset}",
        note=(
            "Mock grant: a scope descriptor only. Adjutant never stores or "
            "issues real credentials; a production executor would exchange "
            "this scope for a just-in-time credential."
        ),
    )
