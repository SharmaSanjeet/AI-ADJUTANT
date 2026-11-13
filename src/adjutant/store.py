from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from .audit import GENESIS_HASH, compute_event_hash
from .autonomy import (
    AUTONOMY_VERSION,
    OOB_REQUEST_TTL_MINUTES,
    OOB_SIGNER_KEY_ID,
    THRESHOLDS_VERSION,
    approval_window_start,
    evaluate_autonomy,
    oob_bundle_payload,
    sign_oob_bundle,
    verify_oob_approval,
)
from .clocks import compute_clock, get_clock_rule
from .comms import AUDIENCE_LABELS, build_claims, evaluate_brief
from .config import get_settings
from .containment import (
    ACTION_CATALOG,
    EXECUTOR_VERSION,
    approval_core,
    build_execution_plan,
    check_approval,
    evaluate_policy,
    get_action,
    mint_credential,
    sign_approval_record,
    sign_payload,
)
from .dispatch import (
    assess_readiness as compute_readiness,
    build_assignment,
    build_handoff,
    escalation_for,
    map_impacts,
    resolve_owner,
)
from .errors import ConflictError, NotFoundError, PolicyViolation
from .extractors import extract_signal
from .models import (
    ActionCatalogEntry,
    ActionProposal,
    ActionProposalCreate,
    ActionWindowStats,
    Approval,
    ApprovalCreate,
    ApprovalRequest,
    AuditVerification,
    AutonomyLevel,
    AutonomyLevelRequest,
    AutomationStatus,
    BreakerResetRequest,
    BreakerState,
    BriefApproval,
    BriefApprovalCreate,
    BriefCheck,
    BriefCreate,
    BriefDraft,
    BriefRecord,
    BriefSend,
    BriefSendCreate,
    CheckStatus,
    Classification,
    ClockCandidate,
    ClockCandidateCreate,
    ClockConfirmation,
    ClockStatus,
    ContainmentRecord,
    DispatchAckCreate,
    DispatchAssignment,
    DispatchRecord,
    DispatchResolveCreate,
    DispatchStatus,
    EventEnvelope,
    Evidence,
    ExecutionRequest,
    ExecutionResult,
    Fact,
    FactCreate,
    FactStatus,
    FactStatusChange,
    FactTrust,
    HandoffAcknowledgment,
    HandoffBrief,
    ImpactMapping,
    Incident,
    IncidentCreate,
    KillSwitchRequest,
    KillSwitchState,
    OwnerResolution,
    OobApprovalCreate,
    OobSignResult,
    PolicyDecision,
    RateLimitState,
    ReadinessAssessment,
    Scorecard,
    Signal,
    SignalCreate,
    SignalIngestResult,
)
from .ports.model import ModelPort

CHAIN_LOCK_ID = 8_000_000_001
SEED_LOCK_ID = 8_000_000_002
KILL_SWITCH_KEY = "automation_kill_switch"
BREAKER_KEY_PREFIX = "automation_breaker:"
LEVEL_KEY_PREFIX = "autonomy_level:"
RATE_LIMIT_WINDOW_SECONDS = 3600
EPOCH_MIN = datetime.min.replace(tzinfo=timezone.utc)

FACT_COLUMNS = """
    id, incident_id, attribute, value, source, valid_at, recorded_at,
    confidence, status, supersedes, classification, trust, evidence
"""

BRIEF_COLUMNS = """
    id, incident_id, audience, title, claims, delta_since, fact_ids,
    generated_by, created_at, classification, status, check_status
"""

POLICY_DECISION_COLUMNS = """
    id, incident_id, proposal_id, decision, reasons, required_approvals,
    allowed_roles, action_hash, policy_version, evaluated_at, evaluator
"""

CONTAINMENT_APPROVAL_COLUMNS = """
    id, incident_id, proposal_id, action_id, approver, approver_role,
    decision, decided_at, expires_at, nonce, action_hash, signature, key_id,
    note
"""

EXECUTION_COLUMNS = """
    id, incident_id, proposal_id, approval_id, action_id, target_asset,
    status, dry_run, steps, reasons, credential, requested_by, started_at,
    finished_at, executor
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _last_hash(conn: AsyncConnection) -> str:
    cur = await conn.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1")
    row = await cur.fetchone()
    return row["hash"] if row else GENESIS_HASH


async def append_event(
    conn: AsyncConnection,
    *,
    incident_id: UUID,
    event_type: str,
    payload: dict[str, Any],
    source: str,
    valid_at: datetime | None = None,
    recorded_at: datetime | None = None,
    classification: str = "internal",
) -> EventEnvelope:
    """Append one event and update projections. Caller owns the transaction."""
    await conn.execute("SELECT pg_advisory_xact_lock(%s)", (CHAIN_LOCK_ID,))
    prev_hash = await _last_hash(conn)
    event_id = uuid4()
    recorded_at = recorded_at or utcnow()

    event_hash = compute_event_hash(
        prev_hash=prev_hash,
        event_id=event_id,
        incident_id=incident_id,
        event_type=event_type,
        payload=payload,
        source=source,
        recorded_at=recorded_at,
        valid_at=valid_at,
        classification=classification,
    )

    cur = await conn.execute(
        """
        INSERT INTO events (
            id, incident_id, event_type, payload, source,
            valid_at, recorded_at, classification, prev_hash, hash
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING seq
        """,
        (
            event_id,
            incident_id,
            event_type,
            Jsonb(payload),
            source,
            valid_at,
            recorded_at,
            classification,
            prev_hash,
            event_hash,
        ),
    )
    row = await cur.fetchone()
    await _apply_projection(conn, event_type, payload)

    return EventEnvelope(
        seq=row["seq"],
        id=event_id,
        incident_id=incident_id,
        event_type=event_type,
        payload=payload,
        source=source,
        valid_at=valid_at,
        recorded_at=recorded_at,
        classification=classification,
        prev_hash=prev_hash,
        hash=event_hash,
    )


async def _apply_projection(
    conn: AsyncConnection, event_type: str, payload: dict[str, Any]
) -> None:
    if event_type == "incident.created":
        await conn.execute(
            """
            INSERT INTO incidents (id, title, severity, status, declared_at, declared_by, summary)
            VALUES (%s, %s, %s, %s, %s::timestamptz, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                UUID(payload["id"]),
                payload["title"],
                payload["severity"],
                payload["status"],
                payload["declared_at"],
                payload["declared_by"],
                payload.get("summary"),
            ),
        )
    elif event_type == "signal.received":
        await conn.execute(
            """
            INSERT INTO signals (
                id, incident_id, kind, source, content_hash, content_excerpt,
                observed_at, recorded_at, trust
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::timestamptz, %s::timestamptz, %s)
            ON CONFLICT (incident_id, content_hash) DO NOTHING
            """,
            (
                UUID(payload["id"]),
                UUID(payload["incident_id"]),
                payload["kind"],
                payload["source"],
                payload["content_hash"],
                payload["content_excerpt"],
                payload["observed_at"],
                payload["recorded_at"],
                payload.get("trust", "untrusted"),
            ),
        )
    elif event_type == "fact.appended":
        await conn.execute(
            """
            INSERT INTO facts (
                id, incident_id, attribute, value, source, valid_at, recorded_at,
                confidence, status, supersedes, classification, trust, evidence
            ) VALUES (%s, %s, %s, %s, %s, %s::timestamptz, %s::timestamptz,
                      %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                UUID(payload["id"]),
                UUID(payload["incident_id"]),
                payload["attribute"],
                Jsonb(payload["value"]),
                payload["source"],
                payload["valid_at"],
                payload["recorded_at"],
                Jsonb(payload["confidence"]),
                payload["status"],
                UUID(payload["supersedes"]) if payload.get("supersedes") else None,
                payload["classification"],
                payload.get("trust", "trusted"),
                Jsonb(payload["evidence"]),
            ),
        )
        if payload.get("supersedes"):
            await conn.execute(
                """
                UPDATE facts SET status = 'superseded'
                WHERE id = %s AND incident_id = %s
                """,
                (UUID(payload["supersedes"]), UUID(payload["incident_id"])),
            )
    elif event_type == "fact.status_changed":
        cur = await conn.execute(
            """
            UPDATE facts SET status = %s
            WHERE id = %s AND incident_id = %s
            """,
            (
                payload["status"],
                UUID(payload["fact_id"]),
                UUID(payload["incident_id"]),
            ),
        )
        if cur.rowcount == 0:
            raise ValueError("fact not found")
    elif event_type == "proposal.created":
        await conn.execute(
            """
            INSERT INTO proposals (
                id, incident_id, action_id, params, target_asset, tier,
                justification_refs, proposed_by, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::timestamptz)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                UUID(payload["id"]),
                UUID(payload["incident_id"]),
                payload["action_id"],
                Jsonb(payload["params"]),
                payload["target_asset"],
                payload["tier"],
                Jsonb(payload["justification_refs"]),
                payload["proposed_by"],
                payload["created_at"],
            ),
        )
    elif event_type == "brief.drafted":
        await conn.execute(
            """
            INSERT INTO briefs (
                id, incident_id, audience, title, claims, delta_since,
                fact_ids, generated_by, created_at, classification, status
            ) VALUES (%s, %s, %s, %s, %s, %s::timestamptz, %s, %s,
                      %s::timestamptz, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                UUID(payload["id"]),
                UUID(payload["incident_id"]),
                payload["audience"],
                payload["title"],
                Jsonb(payload["claims"]),
                payload.get("delta_since"),
                Jsonb(payload["fact_ids"]),
                payload["generated_by"],
                payload["created_at"],
                payload["classification"],
                payload.get("status", "draft"),
            ),
        )
    elif event_type == "brief.checked":
        await conn.execute(
            """
            INSERT INTO brief_checks (
                id, brief_id, incident_id, status, issues, claims_checked,
                evidence, checked_at, checker
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::timestamptz, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                UUID(payload["id"]),
                UUID(payload["brief_id"]),
                UUID(payload["incident_id"]),
                payload["status"],
                Jsonb(payload["issues"]),
                payload["claims_checked"],
                Jsonb(payload["evidence"]),
                payload["checked_at"],
                payload["checker"],
            ),
        )
        await conn.execute(
            "UPDATE briefs SET check_status = %s WHERE id = %s",
            (payload["status"], UUID(payload["brief_id"])),
        )
    elif event_type == "brief.approved":
        await conn.execute(
            """
            INSERT INTO brief_approvals (
                id, brief_id, incident_id, approver, approver_role,
                approved_at, expires_at, check_id, acknowledgment
            ) VALUES (%s, %s, %s, %s, %s, %s::timestamptz, %s::timestamptz, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                UUID(payload["id"]),
                UUID(payload["brief_id"]),
                UUID(payload["incident_id"]),
                payload["approver"],
                payload["approver_role"],
                payload["approved_at"],
                payload["expires_at"],
                UUID(payload["check_id"]),
                payload.get("acknowledgment"),
            ),
        )
        await conn.execute(
            "UPDATE briefs SET status = 'approved' WHERE id = %s",
            (UUID(payload["brief_id"]),),
        )
    elif event_type == "brief.send_mocked":
        await conn.execute(
            """
            INSERT INTO brief_sends (
                id, brief_id, incident_id, channel, destination, sent_at,
                delivery_id, adapter, requested_by
            ) VALUES (%s, %s, %s, %s, %s, %s::timestamptz, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                UUID(payload["id"]),
                UUID(payload["brief_id"]),
                UUID(payload["incident_id"]),
                payload["channel"],
                payload["destination"],
                payload["sent_at"],
                payload["delivery_id"],
                payload["adapter"],
                payload["requested_by"],
            ),
        )
        await conn.execute(
            "UPDATE briefs SET status = 'sent_mock' WHERE id = %s",
            (UUID(payload["brief_id"]),),
        )
    elif event_type == "clock.candidate_recorded":
        await conn.execute(
            """
            INSERT INTO clocks (
                id, incident_id, regime, label, trigger_fact_id, trigger_at,
                due_at, status, requires_legal_confirmation, computation, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s::timestamptz, %s::timestamptz,
                      %s, %s, %s, %s::timestamptz)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                UUID(payload["id"]),
                UUID(payload["incident_id"]),
                payload["regime"],
                payload["label"],
                UUID(payload["trigger_fact_id"])
                if payload.get("trigger_fact_id")
                else None,
                payload["trigger_at"],
                payload["due_at"],
                payload.get("status", "candidate"),
                payload.get("requires_legal_confirmation", True),
                Jsonb(payload["computation"]),
                payload["created_at"],
            ),
        )
    elif event_type == "clock.confirmed":
        cur = await conn.execute(
            """
            UPDATE clocks
            SET status = 'confirmed', confirmed_by = %s,
                confirmed_role = %s, confirmed_at = %s::timestamptz
            WHERE id = %s AND incident_id = %s
            """,
            (
                payload["confirmed_by"],
                payload["role"],
                payload["confirmed_at"],
                UUID(payload["clock_id"]),
                UUID(payload["incident_id"]),
            ),
        )
        if cur.rowcount == 0:
            raise ValueError("clock not found")
    elif event_type == "dispatch.resolved":
        resolution = payload["resolution"]
        await conn.execute(
            """
            INSERT INTO dispatch_resolutions (
                id, incident_id, asset, status, owner, owner_source, contact,
                confidence, candidates, steps, resolved_at, resolver
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s::timestamptz, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                UUID(resolution["id"]),
                UUID(resolution["incident_id"]),
                resolution["asset"],
                resolution["status"],
                resolution.get("owner"),
                resolution.get("owner_source"),
                resolution.get("contact"),
                resolution["confidence"],
                Jsonb(resolution["candidates"]),
                Jsonb(resolution["steps"]),
                resolution["resolved_at"],
                resolution["resolver"],
            ),
        )
        assignment = payload.get("assignment")
        if assignment:
            await conn.execute(
                """
                INSERT INTO dispatch_assignments (
                    id, incident_id, resolution_id, asset, owner, contact,
                    role, channel, status, assigned_at, ack_due_at,
                    sla_minutes, ack_at, ack_by, sla_met, escalated_at,
                    escalated_to, note
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                          %s::timestamptz, %s::timestamptz, %s, %s, %s,
                          %s, %s::timestamptz, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    UUID(assignment["id"]),
                    UUID(assignment["incident_id"]),
                    UUID(assignment["resolution_id"]),
                    assignment["asset"],
                    assignment["owner"],
                    assignment["contact"],
                    assignment["role"],
                    assignment["channel"],
                    assignment["status"],
                    assignment["assigned_at"],
                    assignment["ack_due_at"],
                    assignment["sla_minutes"],
                    assignment.get("ack_at"),
                    assignment.get("ack_by"),
                    assignment.get("sla_met"),
                    assignment.get("escalated_at"),
                    assignment.get("escalated_to"),
                    assignment.get("note"),
                ),
            )
    elif event_type == "dispatch.acknowledged":
        cur = await conn.execute(
            """
            UPDATE dispatch_assignments
            SET status = 'acked', ack_at = %s::timestamptz, ack_by = %s,
                sla_met = %s, note = COALESCE(%s, note)
            WHERE id = %s AND incident_id = %s
            """,
            (
                payload["ack_at"],
                payload["acked_by"],
                payload["sla_met"],
                payload.get("note"),
                UUID(payload["assignment_id"]),
                UUID(payload["incident_id"]),
            ),
        )
        if cur.rowcount == 0:
            raise ValueError("dispatch assignment not found")
    elif event_type == "dispatch.escalated":
        cur = await conn.execute(
            """
            UPDATE dispatch_assignments
            SET status = 'escalated', escalated_at = %s::timestamptz,
                escalated_to = %s, note = COALESCE(%s, note)
            WHERE id = %s AND incident_id = %s
            """,
            (
                payload["escalated_at"],
                payload["escalated_to"],
                payload.get("note"),
                UUID(payload["assignment_id"]),
                UUID(payload["incident_id"]),
            ),
        )
        if cur.rowcount == 0:
            raise ValueError("dispatch assignment not found")
    elif event_type == "impact.mapped":
        for mapping in payload["mappings"]:
            await conn.execute(
                """
                INSERT INTO impact_mappings (
                    id, incident_id, asset, service, criticality, rto_minutes,
                    rpo_minutes, rto_deadline, status, gaps, evidence_refs,
                    mapped_at, engine
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::timestamptz, %s,
                          %s, %s, %s::timestamptz, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    UUID(mapping["id"]),
                    UUID(mapping["incident_id"]),
                    mapping["asset"],
                    mapping.get("service"),
                    mapping.get("criticality"),
                    mapping.get("rto_minutes"),
                    mapping.get("rpo_minutes"),
                    mapping.get("rto_deadline"),
                    mapping["status"],
                    Jsonb(mapping["gaps"]),
                    Jsonb(mapping["evidence_refs"]),
                    mapping["mapped_at"],
                    mapping["engine"],
                ),
            )
    elif event_type == "readiness.assessed":
        await conn.execute(
            """
            INSERT INTO readiness_assessments (
                id, incident_id, planes, integrations, checked_at, engine
            ) VALUES (%s, %s, %s, %s, %s::timestamptz, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                UUID(payload["id"]),
                UUID(payload["incident_id"]),
                Jsonb(payload["planes"]),
                Jsonb(payload["integrations"]),
                payload["checked_at"],
                payload["engine"],
            ),
        )
    elif event_type == "handoff.drafted":
        await conn.execute(
            """
            INSERT INTO handoffs (
                id, incident_id, title, summary, open_approvals, open_acks,
                evidence_gaps, pending_clocks, readiness, checks, generated_by,
                created_at, acknowledged_by, acknowledged_at, note
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s::timestamptz, %s, %s::timestamptz, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                UUID(payload["id"]),
                UUID(payload["incident_id"]),
                payload["title"],
                payload["summary"],
                Jsonb(payload["open_approvals"]),
                Jsonb(payload["open_acks"]),
                Jsonb(payload["evidence_gaps"]),
                Jsonb(payload["pending_clocks"]),
                Jsonb(payload["readiness"]),
                Jsonb(payload["checks"]),
                payload["generated_by"],
                payload["created_at"],
                payload.get("acknowledged_by"),
                payload.get("acknowledged_at"),
                payload.get("note"),
            ),
        )
    elif event_type == "handoff.acknowledged":
        cur = await conn.execute(
            """
            UPDATE handoffs
            SET acknowledged_by = %s, acknowledged_at = %s::timestamptz,
                note = %s
            WHERE id = %s AND incident_id = %s
            """,
            (
                payload["acknowledged_by"],
                payload["acknowledged_at"],
                payload.get("note"),
                UUID(payload["handoff_id"]),
                UUID(payload["incident_id"]),
            ),
        )
        if cur.rowcount == 0:
            raise ValueError("handoff not found")
    elif event_type == "policy.decided":
        await conn.execute(
            """
            INSERT INTO policy_decisions (
                id, incident_id, proposal_id, decision, reasons,
                required_approvals, allowed_roles, action_hash, policy_version,
                evaluated_at, evaluator
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::timestamptz, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                UUID(payload["id"]),
                UUID(payload["incident_id"]),
                UUID(payload["proposal_id"]),
                payload["decision"],
                Jsonb(payload["reasons"]),
                payload["required_approvals"],
                Jsonb(payload["allowed_roles"]),
                payload["action_hash"],
                payload["policy_version"],
                payload["evaluated_at"],
                payload["evaluator"],
            ),
        )
    elif event_type == "approval.signed":
        await conn.execute(
            """
            INSERT INTO containment_approvals (
                id, incident_id, proposal_id, action_id, approver,
                approver_role, decision, decided_at, expires_at, nonce,
                action_hash, signature, key_id, note
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::timestamptz,
                      %s::timestamptz, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                UUID(payload["id"]),
                UUID(payload["incident_id"]),
                UUID(payload["proposal_id"]),
                payload["action_id"],
                payload["approver"],
                payload["approver_role"],
                payload["decision"],
                payload["decided_at"],
                payload["expires_at"],
                payload["nonce"],
                payload["action_hash"],
                payload["signature"],
                payload["key_id"],
                payload.get("note"),
            ),
        )
    elif event_type in ("execution.simulated", "execution.refused"):
        await conn.execute(
            """
            INSERT INTO action_executions (
                id, incident_id, proposal_id, approval_id, action_id,
                target_asset, status, dry_run, steps, reasons, credential,
                requested_by, started_at, finished_at, executor
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s::timestamptz, %s::timestamptz, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                UUID(payload["id"]),
                UUID(payload["incident_id"]),
                UUID(payload["proposal_id"]),
                UUID(payload["approval_id"]) if payload.get("approval_id") else None,
                payload["action_id"],
                payload["target_asset"],
                payload["status"],
                payload["dry_run"],
                Jsonb(payload["steps"]),
                Jsonb(payload["reasons"]),
                Jsonb(payload["credential"]) if payload.get("credential") else None,
                payload["requested_by"],
                payload["started_at"],
                payload["finished_at"],
                payload["executor"],
            ),
        )
    elif event_type in (
        "automation.kill_switch_engaged",
        "automation.kill_switch_released",
    ):
        await conn.execute(
            """
            INSERT INTO system_state (key, value, updated_at)
            VALUES (%s, %s, %s::timestamptz)
            ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at
            """,
            (KILL_SWITCH_KEY, Jsonb(payload), payload["at"]),
        )
    elif event_type in (
        "automation.breaker_tripped",
        "automation.breaker_reset",
    ):
        await conn.execute(
            """
            INSERT INTO system_state (key, value, updated_at)
            VALUES (%s, %s, %s::timestamptz)
            ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at
            """,
            (
                f"{BREAKER_KEY_PREFIX}{payload['action_id']}",
                Jsonb(payload),
                payload["at"],
            ),
        )
    elif event_type == "automation.level_set":
        await conn.execute(
            """
            INSERT INTO system_state (key, value, updated_at)
            VALUES (%s, %s, %s::timestamptz)
            ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at
            """,
            (
                f"{LEVEL_KEY_PREFIX}{payload['action_id']}",
                Jsonb(
                    {
                        "action_id": payload["action_id"],
                        "level": payload["level"],
                        "set_by": payload["actor"],
                        "set_at": payload["at"],
                    }
                ),
                payload["at"],
            ),
        )
    elif event_type == "approval.requested":
        await conn.execute(
            """
            INSERT INTO approval_requests (
                id, incident_id, proposal_id, action_id, action_hash, nonce,
                bundle, topology, status, created_at, expires_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s::timestamptz, %s::timestamptz)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                UUID(payload["id"]),
                UUID(payload["incident_id"]),
                UUID(payload["proposal_id"]),
                payload["action_id"],
                payload["action_hash"],
                payload["nonce"],
                Jsonb(payload["bundle"]),
                payload["topology"],
                payload.get("status", "pending"),
                payload["created_at"],
                payload["expires_at"],
            ),
        )
    elif event_type == "approval.oob_signed":
        await conn.execute(
            """
            INSERT INTO containment_approvals (
                id, incident_id, proposal_id, action_id, approver,
                approver_role, decision, decided_at, expires_at, nonce,
                action_hash, signature, key_id, note
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::timestamptz,
                      %s::timestamptz, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                UUID(payload["id"]),
                UUID(payload["incident_id"]),
                UUID(payload["proposal_id"]),
                payload["action_id"],
                payload["approver"],
                payload["approver_role"],
                payload["decision"],
                payload["decided_at"],
                payload["expires_at"],
                payload["nonce"],
                payload["action_hash"],
                payload["signature"],
                payload["key_id"],
                payload.get("note"),
            ),
        )
        await conn.execute(
            """
            UPDATE approval_requests
            SET status = 'approved', resolved_at = %s::timestamptz,
                resolved_by = %s
            WHERE id = %s
            """,
            (
                payload["decided_at"],
                payload["approver"],
                UUID(payload["bundle_id"]),
            ),
        )


async def create_incident(pool: AsyncConnectionPool, data: IncidentCreate) -> Incident:
    incident = Incident(
        id=uuid4(),
        title=data.title,
        severity=data.severity,
        status="declared",
        declared_at=utcnow(),
        declared_by=data.declared_by,
        summary=data.summary,
    )
    async with pool.connection() as conn:
        async with conn.transaction():
            await append_event(
                conn,
                incident_id=incident.id,
                event_type="incident.created",
                payload=incident.model_dump(mode="json"),
                source=f"human:{data.declared_by}",
                valid_at=incident.declared_at,
                recorded_at=incident.declared_at,
                classification="internal",
            )
    return incident


async def append_fact(
    pool: AsyncConnectionPool, incident_id: UUID, data: FactCreate
) -> Fact:
    recorded_at = utcnow()
    fact = Fact(
        id=uuid4(),
        incident_id=incident_id,
        attribute=data.attribute,
        value=data.value,
        source=data.source,
        valid_at=data.valid_at or recorded_at,
        recorded_at=recorded_at,
        confidence=data.confidence,
        status=data.status,
        supersedes=data.supersedes,
        classification=data.classification,
        trust=data.trust,
        evidence=data.evidence,
    )
    async with pool.connection() as conn:
        async with conn.transaction():
            if data.supersedes is not None:
                cur = await conn.execute(
                    "SELECT incident_id FROM facts WHERE id = %s",
                    (data.supersedes,),
                )
                row = await cur.fetchone()
                if row is None or row["incident_id"] != incident_id:
                    raise ValueError("superseded fact not found in this incident")
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="fact.appended",
                payload=fact.model_dump(mode="json"),
                source=fact.source,
                valid_at=fact.valid_at,
                recorded_at=fact.recorded_at,
                classification=fact.classification.value,
            )
    return fact


async def change_fact_status(
    pool: AsyncConnectionPool,
    incident_id: UUID,
    fact_id: UUID,
    data: FactStatusChange,
) -> None:
    recorded_at = utcnow()
    payload = {
        "fact_id": str(fact_id),
        "incident_id": str(incident_id),
        "status": data.status.value,
        "reason": data.reason,
        "changed_by": data.changed_by,
        "changed_at": recorded_at.isoformat(),
    }
    async with pool.connection() as conn:
        async with conn.transaction():
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="fact.status_changed",
                payload=payload,
                source=f"human:{data.changed_by}",
                valid_at=recorded_at,
                recorded_at=recorded_at,
                classification="internal",
            )


async def create_proposal(
    pool: AsyncConnectionPool,
    incident_id: UUID,
    data: ActionProposalCreate,
) -> ActionProposal:
    proposal = ActionProposal(
        id=uuid4(),
        incident_id=incident_id,
        action_id=data.action_id,
        params=data.params,
        target_asset=data.target_asset,
        tier=data.tier,
        justification_refs=data.justification_refs,
        proposed_by=data.proposed_by,
        created_at=utcnow(),
    )
    async with pool.connection() as conn:
        async with conn.transaction():
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="proposal.created",
                payload=proposal.model_dump(mode="json"),
                source=proposal.proposed_by,
                valid_at=proposal.created_at,
                recorded_at=proposal.created_at,
                classification="internal",
            )
    return proposal


async def ingest_signal(
    pool: AsyncConnectionPool,
    incident_id: UUID,
    data: SignalCreate,
    model: ModelPort,
) -> SignalIngestResult:
    content_hash = "sha256:" + hashlib.sha256(
        data.content.encode("utf-8")
    ).hexdigest()

    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, incident_id, kind, source, content_hash, content_excerpt,
                   observed_at, recorded_at, trust
            FROM signals
            WHERE incident_id = %s AND content_hash = %s
            """,
            (incident_id, content_hash),
        )
        existing = await cur.fetchone()

    if existing:
        return SignalIngestResult(
            signal=Signal.model_validate(existing),
            extracted_facts=[],
            duplicate=True,
        )

    fields = await extract_signal(model, data.kind.value, data.content)
    recorded_at = utcnow()
    observed_at = data.observed_at or recorded_at
    excerpt = data.content[:280]
    signal = Signal(
        id=uuid4(),
        incident_id=incident_id,
        kind=data.kind,
        source=data.source,
        content_hash=content_hash,
        content_excerpt=excerpt,
        observed_at=observed_at,
        recorded_at=recorded_at,
    )
    evidence = Evidence(
        ref=f"signal:{content_hash}",
        kind="signal",
        content_hash=content_hash,
        excerpt=excerpt,
    )
    facts = [
        Fact(
            id=uuid4(),
            incident_id=incident_id,
            attribute=field.attribute,
            value=field.value,
            source=f"extractor:{field.extractor}",
            valid_at=observed_at,
            recorded_at=recorded_at,
            confidence=field.confidence,
            status=FactStatus.ASSERTED,
            classification=Classification.INTERNAL,
            trust=FactTrust.UNTRUSTED,
            evidence=[evidence],
        )
        for field in fields
    ]

    async with pool.connection() as conn:
        async with conn.transaction():
            payload = signal.model_dump(mode="json")
            payload["content"] = data.content
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="signal.received",
                payload=payload,
                source=f"ingest:{data.source}",
                valid_at=observed_at,
                recorded_at=recorded_at,
                classification="internal",
            )
            for fact in facts:
                await append_event(
                    conn,
                    incident_id=incident_id,
                    event_type="fact.appended",
                    payload=fact.model_dump(mode="json"),
                    source=fact.source,
                    valid_at=fact.valid_at,
                    recorded_at=fact.recorded_at,
                    classification=fact.classification.value,
                )

    return SignalIngestResult(signal=signal, extracted_facts=facts)


async def list_signals(
    pool: AsyncConnectionPool, incident_id: UUID
) -> list[Signal]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, incident_id, kind, source, content_hash, content_excerpt,
                   observed_at, recorded_at, trust
            FROM signals
            WHERE incident_id = %s
            ORDER BY recorded_at, id
            """,
            (incident_id,),
        )
        rows = await cur.fetchall()
    return [Signal.model_validate(row) for row in rows]


async def list_decisions(
    pool: AsyncConnectionPool, incident_id: UUID
) -> list[Fact]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, incident_id, attribute, value, source, valid_at, recorded_at,
                   confidence, status, supersedes, classification, trust, evidence
            FROM facts
            WHERE incident_id = %s AND attribute LIKE %s
            ORDER BY recorded_at, id
            """,
            (incident_id, "decision/%"),
        )
        rows = await cur.fetchall()
    return [Fact.model_validate(row) for row in rows]


async def list_incidents(pool: AsyncConnectionPool) -> list[Incident]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, title, severity, status, declared_at, declared_by, summary
            FROM incidents
            ORDER BY declared_at DESC, id
            """
        )
        rows = await cur.fetchall()
    return [Incident.model_validate(row) for row in rows]


async def get_incident(
    pool: AsyncConnectionPool, incident_id: UUID
) -> Incident | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, title, severity, status, declared_at, declared_by, summary
            FROM incidents
            WHERE id = %s
            """,
            (incident_id,),
        )
        row = await cur.fetchone()
    return Incident.model_validate(row) if row else None


async def list_facts(
    pool: AsyncConnectionPool,
    incident_id: UUID,
    include_history: bool = False,
) -> list[Fact]:
    query = """
        SELECT id, incident_id, attribute, value, source, valid_at, recorded_at,
               confidence, status, supersedes, classification, trust, evidence
        FROM facts
        WHERE incident_id = %s
    """
    if not include_history:
        query += " AND status <> 'superseded'"
    query += " ORDER BY recorded_at, id"

    async with pool.connection() as conn:
        cur = await conn.execute(query, (incident_id,))
        rows = await cur.fetchall()
    return [Fact.model_validate(row) for row in rows]


async def list_timeline(
    pool: AsyncConnectionPool, incident_id: UUID
) -> list[EventEnvelope]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT seq, id, incident_id, event_type, payload, source, valid_at,
                   recorded_at, classification, prev_hash, hash
            FROM events
            WHERE incident_id = %s
            ORDER BY seq
            """,
            (incident_id,),
        )
        rows = await cur.fetchall()
    return [EventEnvelope.model_validate(row) for row in rows]


async def list_proposals(
    pool: AsyncConnectionPool, incident_id: UUID
) -> list[ActionProposal]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, incident_id, action_id, params, target_asset, tier,
                   justification_refs, proposed_by, created_at
            FROM proposals
            WHERE incident_id = %s
            ORDER BY created_at, id
            """,
            (incident_id,),
        )
        rows = await cur.fetchall()
    return [ActionProposal.model_validate(row) for row in rows]


def _require_human(actor: str, action: str) -> None:
    normalized = actor.strip().lower()
    if not normalized:
        raise PolicyViolation(f"{action} requires a named human")
    if normalized.startswith(("agent:", "system:", "bot:", "model:")):
        raise PolicyViolation(f"{action} requires a human actor")


async def _system_state(
    conn: AsyncConnection, key: str
) -> dict[str, Any] | None:
    cur = await conn.execute(
        "SELECT value FROM system_state WHERE key = %s", (key,)
    )
    row = await cur.fetchone()
    return row["value"] if row else None


async def _effective_kill_switch(
    conn: AsyncConnection, settings: Any
) -> KillSwitchState:
    row = await _system_state(conn, KILL_SWITCH_KEY)
    state = KillSwitchState.model_validate(row) if row else KillSwitchState()
    if settings.kill_switch:
        return state.model_copy(
            update={
                "engaged": True,
                "source": "environment",
                "engaged_by": state.engaged_by,
                "engaged_at": state.engaged_at,
                "reason": state.reason,
            }
        )
    return state


def _kill_switch_reason(state: KillSwitchState) -> str:
    if state.source == "environment":
        base = (
            "kill switch engaged via environment (KILL_SWITCH); "
            "all automated actions are halted"
        )
    else:
        base = (
            f"kill switch engaged by {state.engaged_by}: {state.reason}; "
            "all automated actions are halted"
        )
    if get_settings().kill_switch and state.engaged_by:
        base += " (also engaged via environment)"
    return base


async def _simulated_count(
    conn: AsyncConnection, action_id: str, since: datetime
) -> int:
    cur = await conn.execute(
        """
        SELECT count(*) AS used FROM action_executions
        WHERE action_id = %s AND status = 'simulated' AND started_at > %s
        """,
        (action_id, since),
    )
    return (await cur.fetchone())["used"]


async def _maybe_trip_breaker(
    conn: AsyncConnection,
    incident_id: UUID,
    action_id: str,
    now: datetime,
) -> None:
    settings = get_settings()
    key = f"{BREAKER_KEY_PREFIX}{action_id}"
    breaker = await _system_state(conn, key)
    if breaker and breaker.get("tripped"):
        return
    reset_start = EPOCH_MIN
    if breaker and breaker.get("reset_at"):
        reset_start = datetime.fromisoformat(breaker["reset_at"])
    cur = await conn.execute(
        """
        SELECT status, started_at FROM action_executions
        WHERE action_id = %s AND started_at > %s
        ORDER BY started_at DESC, id DESC
        """,
        (action_id, reset_start),
    )
    consecutive = 0
    for row in await cur.fetchall():
        if row["status"] != "refused":
            break
        consecutive += 1
    if consecutive < settings.breaker_threshold:
        return
    state = {
        "action_id": action_id,
        "tripped": True,
        "tripped_at": now.isoformat(),
        "reason": (
            f"{consecutive} consecutive refused executions for "
            f"'{action_id}' (threshold {settings.breaker_threshold}); "
            "executions halted until a human resets the breaker"
        ),
        "consecutive_refusals": consecutive,
        "at": now.isoformat(),
    }
    await append_event(
        conn,
        incident_id=incident_id,
        event_type="automation.breaker_tripped",
        payload=state,
        source="executor@1",
        valid_at=now,
        recorded_at=now,
    )


async def _brief_record(
    conn: AsyncConnection, incident_id: UUID, brief_id: UUID
) -> BriefRecord:
    cur = await conn.execute(
        f"SELECT {BRIEF_COLUMNS} FROM briefs WHERE id = %s AND incident_id = %s",
        (brief_id, incident_id),
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("brief not found")
    brief = BriefDraft.model_validate(row)

    cur = await conn.execute(
        """
        SELECT id, brief_id, incident_id, status, issues, claims_checked,
               evidence, checked_at, checker
        FROM brief_checks
        WHERE brief_id = %s
        ORDER BY checked_at DESC, id DESC
        LIMIT 1
        """,
        (brief_id,),
    )
    check_row = await cur.fetchone()

    cur = await conn.execute(
        """
        SELECT id, brief_id, incident_id, approver, approver_role, approved_at,
               expires_at, check_id, acknowledgment
        FROM brief_approvals
        WHERE brief_id = %s
        ORDER BY approved_at DESC, id DESC
        LIMIT 1
        """,
        (brief_id,),
    )
    approval_row = await cur.fetchone()

    cur = await conn.execute(
        """
        SELECT id, brief_id, incident_id, channel, destination, sent_at,
               delivery_id, adapter, requested_by
        FROM brief_sends
        WHERE brief_id = %s
        ORDER BY sent_at DESC, id DESC
        LIMIT 1
        """,
        (brief_id,),
    )
    send_row = await cur.fetchone()

    return BriefRecord(
        brief=brief,
        check=BriefCheck.model_validate(check_row) if check_row else None,
        approval=BriefApproval.model_validate(approval_row)
        if approval_row
        else None,
        send=BriefSend.model_validate(send_row) if send_row else None,
    )


async def create_brief(
    pool: AsyncConnectionPool, incident_id: UUID, data: BriefCreate
) -> BriefRecord:
    now = utcnow()
    async with pool.connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                "SELECT title FROM incidents WHERE id = %s", (incident_id,)
            )
            incident_row = await cur.fetchone()
            if incident_row is None:
                raise NotFoundError("incident not found")

            cur = await conn.execute(
                f"""
                SELECT {FACT_COLUMNS} FROM facts
                WHERE incident_id = %s
                  AND status NOT IN ('superseded', 'retracted')
                ORDER BY recorded_at, id
                """,
                (incident_id,),
            )
            facts = [Fact.model_validate(row) for row in await cur.fetchall()]

            cur = await conn.execute(
                """
                SELECT created_at FROM briefs
                WHERE incident_id = %s AND audience = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (incident_id, data.audience.value),
            )
            previous = await cur.fetchone()
            delta_since = previous["created_at"] if previous else None

            delta = [
                fact
                for fact in facts
                if delta_since is None or fact.recorded_at > delta_since
            ]
            claims = build_claims(delta, data.audience)
            if not claims:
                raise ConflictError("no new supported facts to brief")

            fact_ids = sorted(
                {fact_id for claim in claims for fact_id in claim.fact_ids},
                key=str,
            )
            title = (
                f"{AUDIENCE_LABELS[data.audience]} brief — "
                f"{incident_row['title']}"
            )[:200]
            brief = BriefDraft(
                id=uuid4(),
                incident_id=incident_id,
                audience=data.audience,
                title=title,
                claims=claims,
                delta_since=delta_since,
                fact_ids=fact_ids,
                generated_by="agent:scribe",
                created_at=now,
            )

            await append_event(
                conn,
                incident_id=incident_id,
                event_type="brief.drafted",
                payload=brief.model_dump(mode="json"),
                source="agent:scribe",
                valid_at=now,
                recorded_at=now,
            )

            check = evaluate_brief(brief, {fact.id: fact for fact in facts})
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="brief.checked",
                payload=check.model_dump(mode="json"),
                source="agent:fact-checker",
                valid_at=check.checked_at,
                recorded_at=check.checked_at,
            )

            return await _brief_record(conn, incident_id, brief.id)


async def list_briefs(
    pool: AsyncConnectionPool, incident_id: UUID
) -> list[BriefRecord]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id FROM briefs
            WHERE incident_id = %s
            ORDER BY created_at, id
            """,
            (incident_id,),
        )
        rows = await cur.fetchall()
        return [
            await _brief_record(conn, incident_id, row["id"]) for row in rows
        ]


async def get_brief_record(
    pool: AsyncConnectionPool, incident_id: UUID, brief_id: UUID
) -> BriefRecord:
    async with pool.connection() as conn:
        return await _brief_record(conn, incident_id, brief_id)


async def check_brief_record(
    pool: AsyncConnectionPool, incident_id: UUID, brief_id: UUID
) -> BriefCheck:
    async with pool.connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                f"SELECT {BRIEF_COLUMNS} FROM briefs "
                "WHERE id = %s AND incident_id = %s",
                (brief_id, incident_id),
            )
            row = await cur.fetchone()
            if row is None:
                raise NotFoundError("brief not found")
            brief = BriefDraft.model_validate(row)

            cited_ids = {
                fact_id for claim in brief.claims for fact_id in claim.fact_ids
            }
            facts: dict[UUID, Fact] = {}
            if cited_ids:
                cur = await conn.execute(
                    f"""
                    SELECT {FACT_COLUMNS} FROM facts
                    WHERE incident_id = %s AND id = ANY(%s)
                    """,
                    (incident_id, list(cited_ids)),
                )
                for fact_row in await cur.fetchall():
                    fact = Fact.model_validate(fact_row)
                    facts[fact.id] = fact

            check = evaluate_brief(brief, facts)
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="brief.checked",
                payload=check.model_dump(mode="json"),
                source="agent:fact-checker",
                valid_at=check.checked_at,
                recorded_at=check.checked_at,
            )
            return check


async def approve_brief(
    pool: AsyncConnectionPool,
    incident_id: UUID,
    brief_id: UUID,
    data: BriefApprovalCreate,
) -> BriefRecord:
    _require_human(data.approver, "brief approval")

    check = await check_brief_record(pool, incident_id, brief_id)
    if check.status is CheckStatus.FAILED:
        raise ConflictError(
            "fact-checker gate failed; brief cannot be approved"
        )
    if check.status is CheckStatus.NEEDS_REVIEW and not data.review_acknowledged:
        raise PolicyViolation(
            "brief has judgment claims; approver must acknowledge review"
        )

    approved_at = utcnow()
    acknowledgment = data.note
    if check.status is CheckStatus.NEEDS_REVIEW and not acknowledgment:
        acknowledgment = "judgment claims reviewed by approver"

    async with pool.connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                "SELECT status FROM briefs WHERE id = %s AND incident_id = %s",
                (brief_id, incident_id),
            )
            row = await cur.fetchone()
            if row is None:
                raise NotFoundError("brief not found")
            if row["status"] in ("approved", "sent_mock"):
                raise ConflictError(f"brief is already {row['status']}")

            approval = BriefApproval(
                id=uuid4(),
                brief_id=brief_id,
                incident_id=incident_id,
                approver=data.approver,
                approver_role=data.approver_role,
                approved_at=approved_at,
                expires_at=approved_at + timedelta(minutes=30),
                check_id=check.id,
                acknowledgment=acknowledgment,
            )
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="brief.approved",
                payload=approval.model_dump(mode="json"),
                source=f"human:{data.approver}",
                valid_at=approved_at,
                recorded_at=approved_at,
            )
            return await _brief_record(conn, incident_id, brief_id)


async def send_brief_mock(
    pool: AsyncConnectionPool,
    incident_id: UUID,
    brief_id: UUID,
    data: BriefSendCreate,
) -> BriefRecord:
    _require_human(data.requested_by, "brief send")

    check = await check_brief_record(pool, incident_id, brief_id)
    if check.status is CheckStatus.FAILED:
        raise ConflictError(
            "fact-checker gate failed; brief cannot be sent"
        )

    sent_at = utcnow()
    async with pool.connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                "SELECT status FROM briefs WHERE id = %s AND incident_id = %s",
                (brief_id, incident_id),
            )
            row = await cur.fetchone()
            if row is None:
                raise NotFoundError("brief not found")
            if row["status"] == "sent_mock":
                raise ConflictError("brief was already mock-sent")
            if row["status"] != "approved":
                raise ConflictError("brief has no human approval")

            cur = await conn.execute(
                """
                SELECT id, acknowledgment, expires_at FROM brief_approvals
                WHERE brief_id = %s
                ORDER BY approved_at DESC, id DESC
                LIMIT 1
                """,
                (brief_id,),
            )
            approval = await cur.fetchone()
            if approval is None:
                raise ConflictError("brief has no human approval")
            if approval["expires_at"] <= sent_at:
                raise ConflictError("approval expired; re-approval required")
            if (
                check.status is CheckStatus.NEEDS_REVIEW
                and not approval["acknowledgment"]
            ):
                raise PolicyViolation(
                    "judgment claims were not acknowledged at approval"
                )

            send = BriefSend(
                id=uuid4(),
                brief_id=brief_id,
                incident_id=incident_id,
                channel="mock",
                destination=f"mock://briefs/{brief_id}",
                sent_at=sent_at,
                delivery_id=f"mock-{uuid4().hex[:12]}",
                adapter="mock",
                requested_by=data.requested_by,
            )
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="brief.send_mocked",
                payload=send.model_dump(mode="json"),
                source=f"human:{data.requested_by}",
                valid_at=sent_at,
                recorded_at=sent_at,
            )
            return await _brief_record(conn, incident_id, brief_id)


async def create_clock_candidate(
    pool: AsyncConnectionPool,
    incident_id: UUID,
    data: ClockCandidateCreate,
) -> ClockCandidate:
    try:
        rule = get_clock_rule(data.regime)
    except ValueError as exc:
        raise ConflictError(str(exc)) from exc

    now = utcnow()
    async with pool.connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                "SELECT 1 FROM incidents WHERE id = %s", (incident_id,)
            )
            if await cur.fetchone() is None:
                raise NotFoundError("incident not found")

            if data.trigger_fact_id is not None:
                cur = await conn.execute(
                    """
                    SELECT valid_at, status, trust FROM facts
                    WHERE id = %s AND incident_id = %s
                    """,
                    (data.trigger_fact_id, incident_id),
                )
                fact_row = await cur.fetchone()
                if fact_row is None:
                    raise NotFoundError("trigger fact not found")
                if fact_row["status"] in ("superseded", "retracted"):
                    raise ConflictError("trigger fact is no longer current")
                if fact_row["trust"] != "trusted":
                    raise ConflictError("trigger fact is untrusted")
                trigger_at = fact_row["valid_at"]
            elif data.trigger_at is not None:
                trigger_at = data.trigger_at
                if trigger_at.tzinfo is None:
                    trigger_at = trigger_at.replace(tzinfo=timezone.utc)
                else:
                    trigger_at = trigger_at.astimezone(timezone.utc)
            else:
                raise ConflictError("trigger_fact_id or trigger_at required")

            computation = compute_clock(
                rule,
                trigger_at,
                holidays=data.holidays,
                computed_at=now,
            )
            candidate = ClockCandidate(
                id=uuid4(),
                incident_id=incident_id,
                regime=rule.regime,
                label=rule.label,
                trigger_fact_id=data.trigger_fact_id,
                trigger_at=computation.trigger_at,
                due_at=computation.due_at,
                status=ClockStatus.CANDIDATE,
                requires_legal_confirmation=True,
                computation=computation,
                created_at=now,
            )
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="clock.candidate_recorded",
                payload=candidate.model_dump(mode="json"),
                source="agent:clock-advisor",
                valid_at=computation.trigger_at,
                recorded_at=now,
            )
            return candidate


async def list_clocks(
    pool: AsyncConnectionPool, incident_id: UUID
) -> list[ClockCandidate]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, incident_id, regime, label, trigger_fact_id, trigger_at,
                   due_at, status, requires_legal_confirmation, computation,
                   created_at, confirmed_by, confirmed_role, confirmed_at
            FROM clocks
            WHERE incident_id = %s
            ORDER BY due_at, id
            """,
            (incident_id,),
        )
        rows = await cur.fetchall()
    return [ClockCandidate.model_validate(row) for row in rows]


async def confirm_clock(
    pool: AsyncConnectionPool,
    incident_id: UUID,
    clock_id: UUID,
    data: ClockConfirmation,
) -> ClockCandidate:
    _require_human(data.confirmed_by, "clock confirmation")
    if not data.attestation:
        raise PolicyViolation("legal attestation is required")

    confirmed_at = utcnow()
    async with pool.connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                """
                SELECT id, status, trigger_fact_id FROM clocks
                WHERE id = %s AND incident_id = %s
                """,
                (clock_id, incident_id),
            )
            row = await cur.fetchone()
            if row is None:
                raise NotFoundError("clock not found")
            if row["status"] != "candidate":
                raise ConflictError(f"clock is already {row['status']}")

            if row["trigger_fact_id"] is not None:
                cur = await conn.execute(
                    "SELECT status, trust FROM facts WHERE id = %s AND incident_id = %s",
                    (row["trigger_fact_id"], incident_id),
                )
                trigger = await cur.fetchone()
                if trigger is None or trigger["status"] in (
                    "superseded",
                    "retracted",
                ):
                    raise ConflictError(
                        "trigger fact is no longer current; recompute required"
                    )
                if trigger["trust"] != "trusted":
                    raise ConflictError("trigger fact is untrusted")

            await append_event(
                conn,
                incident_id=incident_id,
                event_type="clock.confirmed",
                payload={
                    "clock_id": str(clock_id),
                    "incident_id": str(incident_id),
                    "confirmed_by": data.confirmed_by,
                    "role": data.role,
                    "attestation": data.attestation,
                    "note": data.note,
                    "confirmed_at": confirmed_at.isoformat(),
                },
                source=f"human:{data.confirmed_by}",
                valid_at=confirmed_at,
                recorded_at=confirmed_at,
            )

            cur = await conn.execute(
                """
                SELECT id, incident_id, regime, label, trigger_fact_id, trigger_at,
                       due_at, status, requires_legal_confirmation, computation,
                       created_at, confirmed_by, confirmed_role, confirmed_at
                FROM clocks
                WHERE id = %s AND incident_id = %s
                """,
                (clock_id, incident_id),
            )
            updated = await cur.fetchone()
    return ClockCandidate.model_validate(updated)


async def _incident_for(conn: AsyncConnection, incident_id: UUID) -> Incident:
    cur = await conn.execute(
        """
        SELECT id, title, severity, status, declared_at, declared_by, summary
        FROM incidents WHERE id = %s
        """,
        (incident_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("incident not found")
    return Incident.model_validate(row)


async def _facts_for(conn: AsyncConnection, incident_id: UUID) -> list[Fact]:
    cur = await conn.execute(
        f"SELECT {FACT_COLUMNS} FROM facts WHERE incident_id = %s "
        "ORDER BY recorded_at, id",
        (incident_id,),
    )
    return [Fact.model_validate(row) for row in await cur.fetchall()]


async def _briefs_for(
    conn: AsyncConnection, incident_id: UUID
) -> list[BriefRecord]:
    cur = await conn.execute(
        "SELECT id FROM briefs WHERE incident_id = %s ORDER BY created_at, id",
        (incident_id,),
    )
    return [
        await _brief_record(conn, incident_id, row["id"])
        for row in await cur.fetchall()
    ]


async def _proposals_for(
    conn: AsyncConnection, incident_id: UUID
) -> list[ActionProposal]:
    cur = await conn.execute(
        """
        SELECT id, incident_id, action_id, params, target_asset, tier,
               justification_refs, proposed_by, created_at
        FROM proposals WHERE incident_id = %s ORDER BY created_at, id
        """,
        (incident_id,),
    )
    return [ActionProposal.model_validate(row) for row in await cur.fetchall()]


async def _clocks_for(
    conn: AsyncConnection, incident_id: UUID
) -> list[ClockCandidate]:
    cur = await conn.execute(
        """
        SELECT id, incident_id, regime, label, trigger_fact_id, trigger_at,
               due_at, status, requires_legal_confirmation, computation,
               created_at, confirmed_by, confirmed_role, confirmed_at
        FROM clocks WHERE incident_id = %s ORDER BY created_at, id
        """,
        (incident_id,),
    )
    return [ClockCandidate.model_validate(row) for row in await cur.fetchall()]


async def _dispatch_record(
    conn: AsyncConnection, incident_id: UUID, resolution_id: UUID
) -> DispatchRecord:
    cur = await conn.execute(
        """
        SELECT id, incident_id, asset, status, owner, owner_source, contact,
               confidence, candidates, steps, resolved_at, resolver
        FROM dispatch_resolutions
        WHERE id = %s AND incident_id = %s
        """,
        (resolution_id, incident_id),
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("dispatch resolution not found")
    resolution = OwnerResolution.model_validate(row)

    cur = await conn.execute(
        """
        SELECT id, incident_id, resolution_id, asset, owner, contact, role,
               channel, status, assigned_at, ack_due_at, sla_minutes, ack_at,
               ack_by, sla_met, escalated_at, escalated_to, note
        FROM dispatch_assignments
        WHERE resolution_id = %s
        ORDER BY assigned_at DESC, id DESC
        LIMIT 1
        """,
        (resolution_id,),
    )
    assignment_row = await cur.fetchone()
    return DispatchRecord(
        resolution=resolution,
        assignment=(
            DispatchAssignment.model_validate(assignment_row)
            if assignment_row
            else None
        ),
    )


async def _dispatch_records_for(
    conn: AsyncConnection, incident_id: UUID
) -> list[DispatchRecord]:
    cur = await conn.execute(
        """
        SELECT id FROM dispatch_resolutions
        WHERE incident_id = %s ORDER BY resolved_at, id
        """,
        (incident_id,),
    )
    return [
        await _dispatch_record(conn, incident_id, row["id"])
        for row in await cur.fetchall()
    ]


async def _impact_records_for(
    conn: AsyncConnection, incident_id: UUID
) -> list[ImpactMapping]:
    cur = await conn.execute(
        """
        SELECT DISTINCT ON (asset)
               id, incident_id, asset, service, criticality, rto_minutes,
               rpo_minutes, rto_deadline, status, gaps, evidence_refs,
               mapped_at, engine
        FROM impact_mappings
        WHERE incident_id = %s
        ORDER BY asset, mapped_at DESC, id DESC
        """,
        (incident_id,),
    )
    return [ImpactMapping.model_validate(row) for row in await cur.fetchall()]


async def _readiness_for(
    conn: AsyncConnection, incident_id: UUID
) -> ReadinessAssessment | None:
    cur = await conn.execute(
        """
        SELECT id, incident_id, planes, integrations, checked_at, engine
        FROM readiness_assessments
        WHERE incident_id = %s
        ORDER BY checked_at DESC, id DESC
        LIMIT 1
        """,
        (incident_id,),
    )
    row = await cur.fetchone()
    return ReadinessAssessment.model_validate(row) if row else None


async def list_dispatch(
    pool: AsyncConnectionPool, incident_id: UUID
) -> list[DispatchRecord]:
    async with pool.connection() as conn:
        return await _dispatch_records_for(conn, incident_id)


async def resolve_dispatch(
    pool: AsyncConnectionPool,
    incident_id: UUID,
    data: DispatchResolveCreate,
) -> DispatchRecord:
    now = utcnow()
    asset = data.asset.strip()
    async with pool.connection() as conn:
        async with conn.transaction():
            incident = await _incident_for(conn, incident_id)
            facts = await _facts_for(conn, incident_id)
            resolution = resolve_owner(asset, facts, incident, now)
            assignment = build_assignment(resolution, incident, now)
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="dispatch.resolved",
                payload={
                    "resolution": resolution.model_dump(mode="json"),
                    "assignment": (
                        assignment.model_dump(mode="json") if assignment else None
                    ),
                },
                source="agent:dispatch",
                valid_at=now,
                recorded_at=now,
            )
            return await _dispatch_record(conn, incident_id, resolution.id)


async def ack_dispatch(
    pool: AsyncConnectionPool,
    incident_id: UUID,
    assignment_id: UUID,
    data: DispatchAckCreate,
) -> DispatchRecord:
    _require_human(data.acked_by, "dispatch acknowledgement")
    now = utcnow()
    async with pool.connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                """
                SELECT status, resolution_id, ack_due_at
                FROM dispatch_assignments
                WHERE id = %s AND incident_id = %s
                """,
                (assignment_id, incident_id),
            )
            row = await cur.fetchone()
            if row is None:
                raise NotFoundError("dispatch assignment not found")
            if row["status"] == "acked":
                raise ConflictError("assignment is already acknowledged")
            sla_met = now <= row["ack_due_at"]
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="dispatch.acknowledged",
                payload={
                    "assignment_id": str(assignment_id),
                    "incident_id": str(incident_id),
                    "acked_by": data.acked_by,
                    "ack_at": now.isoformat(),
                    "sla_met": sla_met,
                    "note": data.note,
                },
                source=f"human:{data.acked_by}",
                valid_at=now,
                recorded_at=now,
            )
            return await _dispatch_record(
                conn, incident_id, row["resolution_id"]
            )


async def evaluate_dispatch(
    pool: AsyncConnectionPool,
    incident_id: UUID,
    now: datetime | None = None,
) -> list[DispatchRecord]:
    now = now or utcnow()
    async with pool.connection() as conn:
        async with conn.transaction():
            incident = await _incident_for(conn, incident_id)
            cur = await conn.execute(
                """
                SELECT id, incident_id, resolution_id, asset, owner, contact,
                       role, channel, status, assigned_at, ack_due_at,
                       sla_minutes, ack_at, ack_by, sla_met, escalated_at,
                       escalated_to, note
                FROM dispatch_assignments
                WHERE incident_id = %s AND status = 'pending'
                ORDER BY ack_due_at, id
                """,
                (incident_id,),
            )
            assignments = [
                DispatchAssignment.model_validate(row)
                for row in await cur.fetchall()
            ]
            for assignment in assignments:
                target = escalation_for(assignment, incident, now)
                if target is None:
                    continue
                await append_event(
                    conn,
                    incident_id=incident_id,
                    event_type="dispatch.escalated",
                    payload={
                        "assignment_id": str(assignment.id),
                        "incident_id": str(incident_id),
                        "escalated_at": now.isoformat(),
                        "escalated_to": target,
                        "note": (
                            f"Acknowledgement SLA of {assignment.sla_minutes} "
                            "minutes elapsed without a human ack."
                        ),
                    },
                    source="agent:dispatch",
                    valid_at=now,
                    recorded_at=now,
                )
            return await _dispatch_records_for(conn, incident_id)


async def map_impact(
    pool: AsyncConnectionPool, incident_id: UUID
) -> list[ImpactMapping]:
    now = utcnow()
    async with pool.connection() as conn:
        async with conn.transaction():
            incident = await _incident_for(conn, incident_id)
            facts = await _facts_for(conn, incident_id)
            mappings = map_impacts(incident, facts, now)
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="impact.mapped",
                payload={
                    "incident_id": str(incident_id),
                    "mappings": [m.model_dump(mode="json") for m in mappings],
                    "mapped_at": now.isoformat(),
                },
                source="agent:bia",
                valid_at=now,
                recorded_at=now,
            )
            return mappings


async def list_impacts(
    pool: AsyncConnectionPool, incident_id: UUID
) -> list[ImpactMapping]:
    async with pool.connection() as conn:
        return await _impact_records_for(conn, incident_id)


async def assess_readiness(
    pool: AsyncConnectionPool, incident_id: UUID
) -> ReadinessAssessment:
    now = utcnow()
    async with pool.connection() as conn:
        async with conn.transaction():
            incident = await _incident_for(conn, incident_id)
            facts = await _facts_for(conn, incident_id)
            assessment = compute_readiness(incident, facts, now)
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="readiness.assessed",
                payload=assessment.model_dump(mode="json"),
                source="agent:readiness",
                valid_at=now,
                recorded_at=now,
            )
            return assessment


async def latest_readiness(
    pool: AsyncConnectionPool, incident_id: UUID
) -> ReadinessAssessment | None:
    async with pool.connection() as conn:
        return await _readiness_for(conn, incident_id)


async def _handoff_row(
    conn: AsyncConnection, incident_id: UUID, handoff_id: UUID
) -> HandoffBrief:
    cur = await conn.execute(
        """
        SELECT id, incident_id, title, summary, open_approvals, open_acks,
               evidence_gaps, pending_clocks, readiness, checks, generated_by,
               created_at, acknowledged_by, acknowledged_at, note
        FROM handoffs
        WHERE id = %s AND incident_id = %s
        """,
        (handoff_id, incident_id),
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("handoff not found")
    return HandoffBrief.model_validate(row)


async def create_handoff(
    pool: AsyncConnectionPool, incident_id: UUID
) -> HandoffBrief:
    now = utcnow()
    async with pool.connection() as conn:
        async with conn.transaction():
            incident = await _incident_for(conn, incident_id)
            facts = await _facts_for(conn, incident_id)
            briefs = await _briefs_for(conn, incident_id)
            proposals = await _proposals_for(conn, incident_id)
            clocks = await _clocks_for(conn, incident_id)
            dispatches = await _dispatch_records_for(conn, incident_id)
            impacts = await _impact_records_for(conn, incident_id)
            readiness = await _readiness_for(conn, incident_id)
            handoff = build_handoff(
                incident,
                facts,
                briefs,
                proposals,
                clocks,
                dispatches,
                impacts,
                readiness,
                now,
            )
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="handoff.drafted",
                payload=handoff.model_dump(mode="json"),
                source="agent:handoff",
                valid_at=now,
                recorded_at=now,
            )
            return handoff


async def latest_handoff(
    pool: AsyncConnectionPool, incident_id: UUID
) -> HandoffBrief | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id FROM handoffs
            WHERE incident_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (incident_id,),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        return await _handoff_row(conn, incident_id, row["id"])


async def acknowledge_handoff(
    pool: AsyncConnectionPool,
    incident_id: UUID,
    handoff_id: UUID,
    data: HandoffAcknowledgment,
) -> HandoffBrief:
    _require_human(data.acknowledged_by, "handoff acknowledgement")
    now = utcnow()
    async with pool.connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                "SELECT acknowledged_at FROM handoffs "
                "WHERE id = %s AND incident_id = %s",
                (handoff_id, incident_id),
            )
            row = await cur.fetchone()
            if row is None:
                raise NotFoundError("handoff not found")
            if row["acknowledged_at"] is not None:
                raise ConflictError("handoff is already acknowledged")
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="handoff.acknowledged",
                payload={
                    "handoff_id": str(handoff_id),
                    "incident_id": str(incident_id),
                    "acknowledged_by": data.acknowledged_by,
                    "acknowledged_at": now.isoformat(),
                    "note": data.note,
                },
                source=f"human:{data.acknowledged_by}",
                valid_at=now,
                recorded_at=now,
            )
            return await _handoff_row(conn, incident_id, handoff_id)


async def _proposal_for(
    conn: AsyncConnection, incident_id: UUID, proposal_id: UUID
) -> ActionProposal:
    cur = await conn.execute(
        """
        SELECT id, incident_id, action_id, params, target_asset, tier,
               justification_refs, proposed_by, created_at
        FROM proposals WHERE id = %s AND incident_id = %s
        """,
        (proposal_id, incident_id),
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("proposal not found")
    return ActionProposal.model_validate(row)


async def _latest_decision(
    conn: AsyncConnection, proposal_id: UUID
) -> PolicyDecision | None:
    cur = await conn.execute(
        f"""
        SELECT {POLICY_DECISION_COLUMNS} FROM policy_decisions
        WHERE proposal_id = %s
        ORDER BY evaluated_at DESC, id DESC
        LIMIT 1
        """,
        (proposal_id,),
    )
    row = await cur.fetchone()
    return PolicyDecision.model_validate(row) if row else None


async def _latest_approval(
    conn: AsyncConnection, proposal_id: UUID
) -> Approval | None:
    cur = await conn.execute(
        f"""
        SELECT {CONTAINMENT_APPROVAL_COLUMNS} FROM containment_approvals
        WHERE proposal_id = %s
        ORDER BY decided_at DESC, id DESC
        LIMIT 1
        """,
        (proposal_id,),
    )
    row = await cur.fetchone()
    return Approval.model_validate(row) if row else None


async def _latest_execution(
    conn: AsyncConnection, proposal_id: UUID
) -> ExecutionResult | None:
    cur = await conn.execute(
        f"""
        SELECT {EXECUTION_COLUMNS} FROM action_executions
        WHERE proposal_id = %s
        ORDER BY started_at DESC, id DESC
        LIMIT 1
        """,
        (proposal_id,),
    )
    row = await cur.fetchone()
    return ExecutionResult.model_validate(row) if row else None


def get_action_catalog() -> list[ActionCatalogEntry]:
    from .containment import catalog

    return catalog()


async def evaluate_proposal(
    pool: AsyncConnectionPool, incident_id: UUID, proposal_id: UUID
) -> PolicyDecision:
    now = utcnow()
    async with pool.connection() as conn:
        async with conn.transaction():
            proposal = await _proposal_for(conn, incident_id, proposal_id)
            facts = await _facts_for(conn, incident_id)
            decision = evaluate_policy(proposal, facts, now)
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="policy.decided",
                payload=decision.model_dump(mode="json"),
                source=decision.evaluator,
                valid_at=now,
                recorded_at=now,
            )
    return decision


async def list_policy_decisions(
    pool: AsyncConnectionPool, incident_id: UUID
) -> list[PolicyDecision]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {POLICY_DECISION_COLUMNS} FROM policy_decisions
            WHERE incident_id = %s
            ORDER BY evaluated_at, id
            """,
            (incident_id,),
        )
        rows = await cur.fetchall()
    return [PolicyDecision.model_validate(row) for row in rows]


async def approve_proposal(
    pool: AsyncConnectionPool,
    incident_id: UUID,
    proposal_id: UUID,
    data: ApprovalCreate,
) -> Approval:
    _require_human(data.approver, "containment approval")
    now = utcnow()
    async with pool.connection() as conn:
        async with conn.transaction():
            kill_switch = await _effective_kill_switch(conn, get_settings())
            if kill_switch.engaged:
                raise PolicyViolation(_kill_switch_reason(kill_switch))
            settings = get_settings()
            if settings.approval_channel == "out-of-band":
                raise PolicyViolation(
                    "the configured approval channel is out-of-band; "
                    "in-band approvals are refused — use the out-of-band "
                    "approval flow"
                )
            proposal = await _proposal_for(conn, incident_id, proposal_id)
            decision = await _latest_decision(conn, proposal_id)
            if decision is None:
                raise PolicyViolation(
                    "run the policy gate before approving this proposal"
                )
            if decision.decision != "allow":
                raise PolicyViolation(
                    f"policy decision is '{decision.decision}'; only 'allow' "
                    "proposals can be approved"
                )
            if data.approver_role not in decision.allowed_roles:
                allowed = ", ".join(decision.allowed_roles)
                raise PolicyViolation(
                    f"role '{data.approver_role}' cannot approve this action "
                    f"(allowed: {allowed})"
                )
            cur = await conn.execute(
                """
                SELECT id FROM containment_approvals
                WHERE proposal_id = %s AND expires_at > %s
                """,
                (proposal_id, now),
            )
            if await cur.fetchone():
                raise ConflictError(
                    "an active approval already exists for this proposal"
                )
            key = get_settings().mock_signing_key
            approval = sign_approval_record(proposal, decision, data, now, key)
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="approval.signed",
                payload=approval.model_dump(mode="json"),
                source=f"human:{data.approver}",
                valid_at=now,
                recorded_at=now,
            )
    return approval


async def list_approvals(
    pool: AsyncConnectionPool, incident_id: UUID
) -> list[Approval]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {CONTAINMENT_APPROVAL_COLUMNS} FROM containment_approvals
            WHERE incident_id = %s
            ORDER BY decided_at, id
            """,
            (incident_id,),
        )
        rows = await cur.fetchall()
    return [Approval.model_validate(row) for row in rows]


async def execute_proposal(
    pool: AsyncConnectionPool,
    incident_id: UUID,
    proposal_id: UUID,
    data: ExecutionRequest,
) -> ExecutionResult:
    _require_human(data.requested_by, "containment execution")
    now = utcnow()
    async with pool.connection() as conn:
        async with conn.transaction():
            proposal = await _proposal_for(conn, incident_id, proposal_id)
            entry = get_action(proposal.action_id)
            decision = await _latest_decision(conn, proposal_id)
            approval = await _latest_approval(conn, proposal_id)
            settings = get_settings()

            async def refuse(
                reasons: list[str], *, counts_toward_breaker: bool = True
            ) -> ExecutionResult:
                result = ExecutionResult(
                    id=uuid4(),
                    incident_id=incident_id,
                    proposal_id=proposal_id,
                    approval_id=approval.id if approval else None,
                    action_id=proposal.action_id,
                    target_asset=proposal.target_asset,
                    status="refused",
                    dry_run=data.dry_run,
                    reasons=reasons,
                    requested_by=data.requested_by,
                    started_at=now,
                    finished_at=now,
                )
                await append_event(
                    conn,
                    incident_id=incident_id,
                    event_type="execution.refused",
                    payload=result.model_dump(mode="json"),
                    source=f"human:{data.requested_by}",
                    valid_at=now,
                    recorded_at=now,
                )
                if counts_toward_breaker:
                    await _maybe_trip_breaker(
                        conn, incident_id, proposal.action_id, now
                    )
                return result

            kill_switch = await _effective_kill_switch(conn, settings)
            if kill_switch.engaged:
                return await refuse(
                    [_kill_switch_reason(kill_switch)], counts_toward_breaker=False
                )
            breaker = await _system_state(
                conn, f"{BREAKER_KEY_PREFIX}{proposal.action_id}"
            )
            if breaker and breaker.get("tripped"):
                return await refuse(
                    [
                        "circuit breaker tripped for "
                        f"'{proposal.action_id}': {breaker.get('reason')}; "
                        "a human must reset it via POST "
                        f"/automation/breakers/{proposal.action_id}/reset"
                    ],
                    counts_toward_breaker=False,
                )
            rate_used = await _simulated_count(
                conn, proposal.action_id, now - timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)
            )
            if rate_used >= settings.rate_limit_per_hour:
                return await refuse(
                    [
                        f"rate limit exceeded: {rate_used} simulated executions "
                        f"for '{proposal.action_id}' in the last "
                        f"{RATE_LIMIT_WINDOW_SECONDS // 60} minutes "
                        f"(limit {settings.rate_limit_per_hour})"
                    ],
                    counts_toward_breaker=False,
                )
            if entry is None:
                return await refuse(
                    [f"action '{proposal.action_id}' is not in the catalog"]
                )
            if decision is None:
                return await refuse(
                    ["no policy decision exists; run the policy gate first"]
                )
            if decision.decision != "allow":
                return await refuse(
                    [
                        f"policy decision is '{decision.decision}'; only "
                        "'allow' proposals can be executed"
                    ]
                )
            if not data.dry_run:
                return await refuse(
                    [
                        "dry-run is mandatory: no real executor is configured "
                        "in Adjutant"
                    ]
                )
            if approval is None:
                return await refuse(
                    ["no signed approval exists for this proposal"]
                )
            cur = await conn.execute(
                """
                SELECT 1 FROM action_executions
                WHERE approval_id = %s AND status = 'simulated'
                """,
                (approval.id,),
            )
            if await cur.fetchone():
                return await refuse(
                    ["approval was already used; replay is blocked"]
                )
            if approval.key_id == OOB_SIGNER_KEY_ID:
                key = settings.mock_oob_signing_key
            else:
                key = settings.mock_signing_key
            reasons = check_approval(approval, proposal, decision, now, key)
            if reasons:
                return await refuse(reasons)

            result = ExecutionResult(
                id=uuid4(),
                incident_id=incident_id,
                proposal_id=proposal_id,
                approval_id=approval.id,
                action_id=proposal.action_id,
                target_asset=proposal.target_asset,
                status="simulated",
                dry_run=True,
                steps=build_execution_plan(entry, proposal),
                reasons=["dry-run simulation recorded; no system was contacted"],
                credential=mint_credential(entry, proposal),
                requested_by=data.requested_by,
                started_at=now,
                finished_at=now,
                executor=EXECUTOR_VERSION,
            )
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="execution.simulated",
                payload=result.model_dump(mode="json"),
                source=f"human:{data.requested_by}",
                valid_at=now,
                recorded_at=now,
            )
            return result


async def list_executions(
    pool: AsyncConnectionPool, incident_id: UUID
) -> list[ExecutionResult]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {EXECUTION_COLUMNS} FROM action_executions
            WHERE incident_id = %s
            ORDER BY started_at, id
            """,
            (incident_id,),
        )
        rows = await cur.fetchall()
    return [ExecutionResult.model_validate(row) for row in rows]


async def containment_records(
    pool: AsyncConnectionPool, incident_id: UUID
) -> list[ContainmentRecord]:
    async with pool.connection() as conn:
        proposals = await _proposals_for(conn, incident_id)
        records: list[ContainmentRecord] = []
        for proposal in proposals:
            approval = await _latest_approval(conn, proposal.id)
            approval_spent = False
            if approval is not None:
                cur = await conn.execute(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM action_executions
                        WHERE approval_id = %s AND status = 'simulated'
                    ) AS spent
                    """,
                    (approval.id,),
                )
                approval_spent = (await cur.fetchone())["spent"]
            records.append(
                ContainmentRecord(
                    proposal=proposal,
                    catalog=get_action(proposal.action_id),
                    decision=await _latest_decision(conn, proposal.id),
                    approval=approval,
                    execution=await _latest_execution(conn, proposal.id),
                    approval_spent=approval_spent,
                )
            )
    return records


async def engage_kill_switch(
    pool: AsyncConnectionPool, data: KillSwitchRequest
) -> KillSwitchState:
    _require_human(data.actor, "kill switch")
    if data.engaged and not data.reason.strip():
        raise PolicyViolation("engaging the kill switch requires a reason")
    now = utcnow()
    if data.engaged:
        state = KillSwitchState(
            engaged=True,
            engaged_by=data.actor,
            engaged_at=now,
            reason=data.reason,
            source="database",
        )
        event_type = "automation.kill_switch_engaged"
        at = state.engaged_at
    else:
        state = KillSwitchState(
            engaged=False,
            released_by=data.actor,
            released_at=now,
            source="database",
        )
        event_type = "automation.kill_switch_released"
        at = state.released_at
    payload = state.model_dump(mode="json")
    payload["at"] = at.isoformat()
    async with pool.connection() as conn:
        async with conn.transaction():
            await append_event(
                conn,
                incident_id=UUID(int=0),
                event_type=event_type,
                payload=payload,
                source=f"human:{data.actor}",
                valid_at=now,
                recorded_at=now,
            )
    return state


async def reset_breaker(
    pool: AsyncConnectionPool, action_id: str, data: BreakerResetRequest
) -> BreakerState:
    _require_human(data.actor, "circuit breaker reset")
    now = utcnow()
    state = BreakerState(
        action_id=action_id,
        tripped=False,
        consecutive_refusals=0,
        reset_at=now,
        reset_by=data.actor,
    )
    payload = {
        "action_id": action_id,
        "tripped": False,
        "consecutive_refusals": 0,
        "reset_at": now.isoformat(),
        "reset_by": data.actor,
        "note": data.note,
        "at": now.isoformat(),
    }
    async with pool.connection() as conn:
        async with conn.transaction():
            await append_event(
                conn,
                incident_id=UUID(int=0),
                event_type="automation.breaker_reset",
                payload=payload,
                source=f"human:{data.actor}",
                valid_at=now,
                recorded_at=now,
            )
    return state


async def set_autonomy_level(
    pool: AsyncConnectionPool, action_id: str, data: AutonomyLevelRequest
) -> dict[str, Any]:
    _require_human(data.actor, "autonomy level change")
    settings = get_settings()
    if not settings.enable_autonomy_promotion:
        raise PolicyViolation(
            "autonomy promotion is disabled by configuration; action types "
            "remain at shadow level"
        )
    if get_action(action_id) is None:
        raise NotFoundError(f"action '{action_id}' is not in the catalog")
    now = utcnow()
    payload = {
        "action_id": action_id,
        "level": data.level,
        "actor": data.actor,
        "reason": data.reason,
        "at": now.isoformat(),
    }
    async with pool.connection() as conn:
        async with conn.transaction():
            await append_event(
                conn,
                incident_id=UUID(int=0),
                event_type="automation.level_set",
                payload=payload,
                source=f"human:{data.actor}",
                valid_at=now,
                recorded_at=now,
            )
    return {
        "action_id": action_id,
        "level": data.level,
        "set_by": data.actor,
        "set_at": now.isoformat(),
    }


async def automation_status(pool: AsyncConnectionPool) -> AutomationStatus:
    settings = get_settings()
    now = utcnow()
    window_start = now - timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)
    async with pool.connection() as conn:
        kill_switch = await _effective_kill_switch(conn, settings)
        breakers: list[BreakerState] = []
        rate_limits: list[RateLimitState] = []
        for action_id in sorted(ACTION_CATALOG):
            stored = await _system_state(conn, f"{BREAKER_KEY_PREFIX}{action_id}")
            if stored:
                breakers.append(BreakerState.model_validate(stored))
            else:
                breakers.append(BreakerState(action_id=action_id))
            used = await _simulated_count(conn, action_id, window_start)
            rate_limits.append(
                RateLimitState(
                    action_id=action_id,
                    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
                    max_per_window=settings.rate_limit_per_hour,
                    used_in_window=used,
                )
            )
    return AutomationStatus(
        kill_switch=kill_switch,
        breakers=breakers,
        rate_limits=rate_limits,
        config_profile=settings.config_profile,
        approval_channel=settings.approval_channel,
        oob_topology=settings.oob_topology,
        autonomy_version=AUTONOMY_VERSION,
        thresholds_version=THRESHOLDS_VERSION,
        promotion_enabled=settings.enable_autonomy_promotion,
        checked_at=now,
    )


async def scorecards(
    pool: AsyncConnectionPool, *, now: datetime | None = None
) -> list[Scorecard]:
    now = now or utcnow()
    window_start = approval_window_start(now)
    async with pool.connection() as conn:
        proposal_rows = await (
            await conn.execute(
                """
                SELECT action_id, count(*) AS n FROM proposals
                WHERE created_at > %s GROUP BY action_id
                """,
                (window_start,),
            )
        ).fetchall()
        decision_rows = await (
            await conn.execute(
                """
                SELECT p.action_id AS action_id, d.decision AS decision,
                       count(*) AS n
                FROM policy_decisions d
                JOIN proposals p ON p.id = d.proposal_id
                WHERE d.evaluated_at > %s
                GROUP BY p.action_id, d.decision
                """,
                (window_start,),
            )
        ).fetchall()
        approval_rows = await (
            await conn.execute(
                """
                SELECT action_id, count(*) AS total,
                    count(*) FILTER (
                        WHERE expires_at <= %s AND NOT EXISTS (
                            SELECT 1 FROM action_executions e
                            WHERE e.approval_id = containment_approvals.id
                              AND e.status = 'simulated'
                        )
                    ) AS expired,
                    count(*) FILTER (
                        WHERE EXISTS (
                            SELECT 1 FROM action_executions e
                            WHERE e.approval_id = containment_approvals.id
                              AND e.status = 'simulated'
                        )
                    ) AS consumed
                FROM containment_approvals
                WHERE decided_at > %s
                GROUP BY action_id
                """,
                (now, window_start),
            )
        ).fetchall()
        execution_rows = await (
            await conn.execute(
                """
                SELECT action_id, status, count(*) AS n
                FROM action_executions
                WHERE started_at > %s
                GROUP BY action_id, status
                """,
                (window_start,),
            )
        ).fetchall()
        trip_rows = await (
            await conn.execute(
                """
                SELECT payload->>'action_id' AS action_id, count(*) AS n
                FROM events
                WHERE event_type = 'automation.breaker_tripped'
                  AND recorded_at > %s
                GROUP BY 1
                """,
                (window_start,),
            )
        ).fetchall()
        level_rows = await (
            await conn.execute(
                """
                SELECT key, value FROM system_state
                WHERE key LIKE %s
                """,
                (f"{LEVEL_KEY_PREFIX}%",),
            )
        ).fetchall()

    stats_by_action: dict[str, ActionWindowStats] = {}

    def _stats_for(action_id: str) -> ActionWindowStats:
        return stats_by_action.setdefault(
            action_id,
            ActionWindowStats(
                action_id=action_id, window_start=window_start, window_end=now
            ),
        )

    for row in proposal_rows:
        _stats_for(row["action_id"]).proposals = row["n"]
    for row in decision_rows:
        stats = _stats_for(row["action_id"])
        if row["decision"] == "allow":
            stats.allows = row["n"]
        elif row["decision"] == "deny":
            stats.denies = row["n"]
        elif row["decision"] == "escalate":
            stats.escalates = row["n"]
    for row in approval_rows:
        stats = _stats_for(row["action_id"])
        stats.approvals = row["total"]
        stats.approvals_expired = row["expired"]
        stats.approvals_consumed = row["consumed"]
    for row in execution_rows:
        stats = _stats_for(row["action_id"])
        if row["status"] == "simulated":
            stats.simulated = row["n"]
        elif row["status"] == "refused":
            stats.refusals = row["n"]
    for row in trip_rows:
        _stats_for(row["action_id"]).breaker_trips = row["n"]

    levels = {
        row["key"].removeprefix(LEVEL_KEY_PREFIX): row["value"]
        for row in level_rows
    }

    cards: list[Scorecard] = []
    for action_id in sorted(
        set(stats_by_action) | set(k for k, v in levels.items() if v.get("level") != "shadow")
    ):
        stats = stats_by_action.get(action_id)
        if stats is None:
            stats = ActionWindowStats(
                action_id=action_id, window_start=window_start, window_end=now
            )
        level_row = levels.get(action_id, {})
        level = level_row.get("level", "shadow")
        if level not in ("shadow", "suggest", "approve"):
            level = "shadow"
        recommendation = evaluate_autonomy(stats, level, now=now)
        cards.append(
            Scorecard(
                action_id=action_id,
                catalog=get_action(action_id),
                stats=stats,
                recommendation=recommendation,
                level=level,
                level_set_by=level_row.get("set_by"),
                level_set_at=level_row.get("set_at"),
                computed_at=now,
                engine=AUTONOMY_VERSION,
            )
        )
    return cards


async def create_approval_request(
    pool: AsyncConnectionPool, incident_id: UUID, proposal_id: UUID
) -> ApprovalRequest:
    now = utcnow()
    settings = get_settings()
    async with pool.connection() as conn:
        async with conn.transaction():
            proposal = await _proposal_for(conn, incident_id, proposal_id)
            entry = get_action(proposal.action_id)
            if entry is not None and entry.never_automate:
                raise PolicyViolation(
                    "never-automate actions have no in-system approval path "
                    "of any kind; the decision happens entirely outside "
                    "Adjutant"
                )
            decision = await _latest_decision(conn, proposal_id)
            if decision is None or decision.decision != "allow":
                raise PolicyViolation(
                    "approval requests require an 'allow' policy decision; "
                    "run the policy gate first"
                )
            cur = await conn.execute(
                """
                SELECT 1 FROM approval_requests
                WHERE proposal_id = %s AND status = 'pending'
                  AND expires_at > %s
                """,
                (proposal_id, now),
            )
            if await cur.fetchone():
                raise ConflictError(
                    "a pending approval request already exists for this "
                    "proposal"
                )
            request = ApprovalRequest(
                id=uuid4(),
                incident_id=incident_id,
                proposal_id=proposal_id,
                action_id=proposal.action_id,
                action_hash=decision.action_hash,
                nonce=uuid4().hex,
                bundle={},
                topology=settings.oob_topology,
                status="pending",
                created_at=now,
                expires_at=now + timedelta(minutes=OOB_REQUEST_TTL_MINUTES),
            )
            request.bundle = oob_bundle_payload(request)
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="approval.requested",
                payload=request.model_dump(mode="json"),
                source="executor@1",
                valid_at=now,
                recorded_at=now,
            )
    return request


async def list_approval_requests(
    pool: AsyncConnectionPool, incident_id: UUID
) -> list[ApprovalRequest]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, incident_id, proposal_id, action_id, action_hash,
                   nonce, bundle, topology, status, created_at, expires_at,
                   resolved_at, resolved_by
            FROM approval_requests
            WHERE incident_id = %s
            ORDER BY created_at, id
            """,
            (incident_id,),
        )
        rows = await cur.fetchall()
    return [ApprovalRequest.model_validate(row) for row in rows]


async def approve_oob(
    pool: AsyncConnectionPool,
    incident_id: UUID,
    proposal_id: UUID,
    data: OobApprovalCreate,
) -> Approval:
    _require_human(data.approver, "out-of-band approval")
    now = utcnow()
    settings = get_settings()
    if settings.approval_channel != "out-of-band":
        raise PolicyViolation(
            "the configured approval channel is in-band; out-of-band "
            "approvals are only available with the out-of-band config "
            "profile"
        )
    async with pool.connection() as conn:
        async with conn.transaction():
            kill_switch = await _effective_kill_switch(conn, settings)
            if kill_switch.engaged:
                raise PolicyViolation(_kill_switch_reason(kill_switch))
            proposal = await _proposal_for(conn, incident_id, proposal_id)
            decision = await _latest_decision(conn, proposal_id)
            if decision is None:
                raise PolicyViolation(
                    "no policy decision exists; run the policy gate first"
                )
            cur = await conn.execute(
                """
                SELECT id, incident_id, proposal_id, action_id, action_hash,
                       nonce, bundle, topology, status, created_at,
                       expires_at, resolved_at, resolved_by
                FROM approval_requests
                WHERE id = %s AND proposal_id = %s
                """,
                (data.bundle_id, proposal_id),
            )
            row = await cur.fetchone()
            if row is None:
                raise NotFoundError("approval request not found")
            request = ApprovalRequest.model_validate(row)
            reasons = verify_oob_approval(
                request,
                data,
                decision,
                decision.action_hash,
                now,
                settings.mock_oob_signing_key,
            )
            if reasons:
                raise PolicyViolation("; ".join(reasons))
            approval = sign_approval_record(
                proposal,
                decision,
                ApprovalCreate(
                    approver=data.approver,
                    approver_role=data.approver_role,
                    note=data.note
                    or f"out-of-band via {request.topology}",
                ),
                now,
                settings.mock_oob_signing_key,
            )
            approval = approval.model_copy(update={"nonce": request.nonce})
            approval.signature = sign_payload(
                approval_core(approval), settings.mock_oob_signing_key
            )
            approval = approval.model_copy(
                update={"key_id": OOB_SIGNER_KEY_ID}
            )
            payload = approval.model_dump(mode="json")
            payload["bundle_id"] = str(request.id)
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="approval.oob_signed",
                payload=payload,
                source=f"human:{data.approver}",
                valid_at=now,
                recorded_at=now,
            )
    return approval


async def mock_sign_oob_bundle(
    pool: AsyncConnectionPool, bundle_id: UUID
) -> OobSignResult:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, incident_id, proposal_id, action_id, action_hash,
                   nonce, bundle, topology, status, created_at, expires_at,
                   resolved_at, resolved_by
            FROM approval_requests
            WHERE id = %s
            """,
            (bundle_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise NotFoundError("approval request not found")
    request = ApprovalRequest.model_validate(row)
    if request.status != "pending":
        raise PolicyViolation(
            f"approval request is '{request.status}'; only pending requests "
            "can be signed"
        )
    signature = sign_oob_bundle(request, get_settings().mock_oob_signing_key)
    return OobSignResult(
        bundle_id=bundle_id,
        signature=signature,
        note=(
            "mock signing for drills only; a real deployment signs inside "
            "the independent control plane, never inside Adjutant"
        ),
    )


async def verify_audit(pool: AsyncConnectionPool) -> AuditVerification:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT seq, id, incident_id, event_type, payload, source, valid_at,
                   recorded_at, classification, prev_hash, hash
            FROM events
            ORDER BY seq
            """
        )
        rows = await cur.fetchall()

    prev = GENESIS_HASH
    for row in rows:
        if row["prev_hash"] != prev:
            return AuditVerification(
                valid=False,
                entries=len(rows),
                head_hash=prev,
                first_broken_seq=row["seq"],
                reason="prev_hash mismatch",
            )
        expected = compute_event_hash(
            prev_hash=row["prev_hash"],
            event_id=row["id"],
            incident_id=row["incident_id"],
            event_type=row["event_type"],
            payload=row["payload"],
            source=row["source"],
            recorded_at=row["recorded_at"],
            valid_at=row["valid_at"],
            classification=row["classification"],
        )
        if expected != row["hash"]:
            return AuditVerification(
                valid=False,
                entries=len(rows),
                head_hash=prev,
                first_broken_seq=row["seq"],
                reason="hash mismatch",
            )
        prev = row["hash"]

    return AuditVerification(valid=True, entries=len(rows), head_hash=prev)


async def rebuild_facts(pool: AsyncConnectionPool) -> None:
    """Rebuild the facts projection from the event log. Proves replayability."""
    async with pool.connection() as conn:
        async with conn.transaction():
            await conn.execute("TRUNCATE facts")
            cur = await conn.execute("SELECT event_type, payload FROM events ORDER BY seq")
            for row in await cur.fetchall():
                if row["event_type"] in {"fact.appended", "fact.status_changed"}:
                    await _apply_projection(conn, row["event_type"], row["payload"])
