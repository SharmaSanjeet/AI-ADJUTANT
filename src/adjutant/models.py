from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Confidence(BaseModel):
    source_reliability: float = Field(default=0.5, ge=0, le=1)
    corroboration: int = Field(default=0, ge=0)
    extraction_certainty: float = Field(default=0.5, ge=0, le=1)


class Evidence(BaseModel):
    ref: str
    kind: str
    content_hash: str
    excerpt: str | None = None


class FactStatus(str, Enum):
    ASSERTED = "asserted"
    CORROBORATED = "corroborated"
    DISPUTED = "disputed"
    RETRACTED = "retracted"
    SUPERSEDED = "superseded"


class Classification(str, Enum):
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    PRIVILEGED = "privileged"


class FactTrust(str, Enum):
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"
    MIXED = "mixed"


class SignalKind(str, Enum):
    LOG = "log"
    EMAIL = "email"
    TICKET = "ticket"
    CHAT = "chat"
    EDR = "edr"
    OTHER = "other"


class IncidentSeverity(str, Enum):
    SEV1 = "sev1"
    SEV2 = "sev2"
    SEV3 = "sev3"
    SEV4 = "sev4"


class IncidentStatus(str, Enum):
    DECLARED = "declared"
    CONTAINED = "contained"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Incident(BaseModel):
    id: UUID
    title: str
    severity: IncidentSeverity
    status: IncidentStatus
    declared_at: datetime
    declared_by: str
    summary: str | None = None


class Fact(BaseModel):
    id: UUID
    incident_id: UUID
    attribute: str
    value: Any
    source: str
    valid_at: datetime
    recorded_at: datetime
    confidence: Confidence
    status: FactStatus
    supersedes: UUID | None = None
    classification: Classification
    trust: FactTrust = FactTrust.TRUSTED
    evidence: list[Evidence] = Field(default_factory=list)


class ActionProposal(BaseModel):
    id: UUID
    incident_id: UUID
    action_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    target_asset: str
    tier: Literal[1, 2, 3]
    justification_refs: list[UUID] = Field(default_factory=list)
    proposed_by: str
    created_at: datetime


class Approval(BaseModel):
    id: UUID
    incident_id: UUID
    proposal_id: UUID
    action_id: str
    approver: str
    approver_role: str
    decision: Literal["approved"] = "approved"
    decided_at: datetime
    expires_at: datetime
    nonce: str
    action_hash: str
    signature: str
    key_id: str
    note: str | None = None


class IncidentCreate(BaseModel):
    title: str
    severity: IncidentSeverity = IncidentSeverity.SEV3
    declared_by: str
    summary: str | None = None


class FactCreate(BaseModel):
    attribute: str
    value: Any
    source: str
    valid_at: datetime | None = None
    confidence: Confidence = Field(default_factory=Confidence)
    status: FactStatus = FactStatus.ASSERTED
    supersedes: UUID | None = None
    classification: Classification = Classification.INTERNAL
    trust: FactTrust = FactTrust.TRUSTED
    evidence: list[Evidence] = Field(default_factory=list)


class FactStatusChange(BaseModel):
    status: FactStatus
    reason: str
    changed_by: str


class ActionProposalCreate(BaseModel):
    action_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    target_asset: str
    tier: Literal[1, 2, 3] = 2
    justification_refs: list[UUID] = Field(default_factory=list)
    proposed_by: str


class EventEnvelope(BaseModel):
    seq: int
    id: UUID
    incident_id: UUID
    event_type: str
    payload: dict[str, Any]
    source: str
    valid_at: datetime | None
    recorded_at: datetime
    classification: Classification
    prev_hash: str
    hash: str


class AuditVerification(BaseModel):
    valid: bool
    entries: int
    head_hash: str
    first_broken_seq: int | None = None
    reason: str | None = None


class SignalCreate(BaseModel):
    kind: SignalKind
    source: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=32768)
    observed_at: datetime | None = None


class Signal(BaseModel):
    id: UUID
    incident_id: UUID
    kind: SignalKind
    source: str
    content_hash: str
    content_excerpt: str
    observed_at: datetime
    recorded_at: datetime
    trust: Literal["untrusted"] = "untrusted"


class SignalIngestResult(BaseModel):
    signal: Signal
    extracted_facts: list[Fact] = Field(default_factory=list)
    duplicate: bool = False


class BriefAudience(str, Enum):
    IC = "ic"
    EXEC = "exec"
    TECHNICAL = "technical"
    LEGAL = "legal"


class ClaimKind(str, Enum):
    FACT = "fact"
    JUDGMENT = "judgment"


class BriefStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    SENT_MOCK = "sent_mock"


class CheckStatus(str, Enum):
    PASSED = "passed"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class BriefClaim(BaseModel):
    id: UUID
    kind: ClaimKind = ClaimKind.FACT
    text: str = Field(min_length=1, max_length=800)
    fact_ids: list[UUID] = Field(default_factory=list, max_length=8)
    evidence_refs: list[str] = Field(default_factory=list, max_length=12)


class BriefDraft(BaseModel):
    id: UUID
    incident_id: UUID
    audience: BriefAudience
    title: str
    claims: list[BriefClaim] = Field(default_factory=list)
    delta_since: datetime | None = None
    fact_ids: list[UUID] = Field(default_factory=list)
    generated_by: str
    created_at: datetime
    classification: Classification = Classification.INTERNAL
    status: BriefStatus = BriefStatus.DRAFT
    check_status: CheckStatus | None = None


class CheckIssue(BaseModel):
    code: str
    claim_id: UUID | None = None
    detail: str


class BriefCheck(BaseModel):
    id: UUID
    brief_id: UUID
    incident_id: UUID
    status: CheckStatus
    issues: list[CheckIssue] = Field(default_factory=list)
    claims_checked: int = 0
    evidence: list[Evidence] = Field(default_factory=list)
    checked_at: datetime
    checker: str = "fact-checker@1"


class BriefApproval(BaseModel):
    id: UUID
    brief_id: UUID
    incident_id: UUID
    approver: str
    approver_role: str
    approved_at: datetime
    expires_at: datetime
    check_id: UUID
    acknowledgment: str | None = None


class BriefSend(BaseModel):
    id: UUID
    brief_id: UUID
    incident_id: UUID
    channel: Literal["mock"] = "mock"
    destination: str
    sent_at: datetime
    delivery_id: str
    adapter: Literal["mock"] = "mock"
    requested_by: str


class BriefRecord(BaseModel):
    brief: BriefDraft
    check: BriefCheck | None = None
    approval: BriefApproval | None = None
    send: BriefSend | None = None


class BriefCreate(BaseModel):
    audience: BriefAudience


class BriefApprovalCreate(BaseModel):
    approver: str = Field(min_length=1, max_length=200)
    approver_role: Literal["ic", "exec", "legal", "comms", "security"]
    review_acknowledged: bool = False
    note: str | None = Field(default=None, max_length=500)


class BriefSendCreate(BaseModel):
    requested_by: str = Field(min_length=1, max_length=200)


class ClockStatus(str, Enum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"


class ClockComputation(BaseModel):
    id: UUID
    regime: str
    label: str
    trigger_at: datetime
    due_at: datetime
    duration: str
    calendar: Literal["calendar", "business"]
    timezone: str | None = None
    holidays: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    computed_at: datetime
    engine: str = "clock-engine@1"


class ClockCandidate(BaseModel):
    id: UUID
    incident_id: UUID
    regime: str
    label: str
    trigger_fact_id: UUID | None = None
    trigger_at: datetime
    due_at: datetime
    status: ClockStatus = ClockStatus.CANDIDATE
    requires_legal_confirmation: bool = True
    computation: ClockComputation
    created_at: datetime
    confirmed_by: str | None = None
    confirmed_role: str | None = None
    confirmed_at: datetime | None = None


class ClockCandidateCreate(BaseModel):
    regime: str = Field(min_length=1, max_length=64)
    trigger_fact_id: UUID | None = None
    trigger_at: datetime | None = None
    holidays: list[date] = Field(default_factory=list, max_length=30)


class ClockConfirmation(BaseModel):
    confirmed_by: str = Field(min_length=1, max_length=200)
    role: Literal["legal", "dpo"]
    attestation: bool
    note: str | None = Field(default=None, max_length=500)


class OwnerCandidate(BaseModel):
    source: str
    owner: str
    contact: str
    confidence: float = Field(ge=0, le=1)
    fact_id: UUID | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    note: str | None = None


class ResolutionStep(BaseModel):
    source: str
    attribute: str
    outcome: Literal["used", "missing", "rejected"]
    detail: str
    fact_id: UUID | None = None


class OwnerResolution(BaseModel):
    id: UUID
    incident_id: UUID
    asset: str
    status: Literal["resolved", "unknown_owner", "ambiguous"]
    owner: str | None = None
    owner_source: str | None = None
    contact: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    candidates: list[OwnerCandidate] = Field(default_factory=list)
    steps: list[ResolutionStep] = Field(default_factory=list)
    resolved_at: datetime
    resolver: str = "dispatch-engine@1"


class DispatchStatus(str, Enum):
    PENDING = "pending"
    ACKED = "acked"
    ESCALATED = "escalated"
    CLOSED = "closed"


class DispatchAssignment(BaseModel):
    id: UUID
    incident_id: UUID
    resolution_id: UUID
    asset: str
    owner: str
    contact: str
    role: Literal["primary", "escalation"] = "primary"
    channel: Literal["mock"] = "mock"
    status: DispatchStatus = DispatchStatus.PENDING
    assigned_at: datetime
    ack_due_at: datetime
    sla_minutes: int
    ack_at: datetime | None = None
    ack_by: str | None = None
    sla_met: bool | None = None
    escalated_at: datetime | None = None
    escalated_to: str | None = None
    note: str | None = None


class DispatchRecord(BaseModel):
    resolution: OwnerResolution
    assignment: DispatchAssignment | None = None


class DispatchResolveCreate(BaseModel):
    asset: str = Field(min_length=1, max_length=200)


class DispatchAckCreate(BaseModel):
    acked_by: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class ImpactMapping(BaseModel):
    id: UUID
    incident_id: UUID
    asset: str
    service: str | None = None
    criticality: str | None = None
    rto_minutes: int | None = None
    rpo_minutes: int | None = None
    rto_deadline: datetime | None = None
    status: Literal["mapped", "partial", "unknown"] = "unknown"
    gaps: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    mapped_at: datetime
    engine: str = "bia-engine@1"


class ReadinessCheck(BaseModel):
    name: str
    outcome: Literal["pass", "fail", "unknown"]
    detail: str
    evidence_refs: list[str] = Field(default_factory=list)


class DrPlane(BaseModel):
    plane: str
    status: Literal["healthy", "degraded", "compromised", "unknown"]
    checks: list[ReadinessCheck] = Field(default_factory=list)


class IntegrationHealth(BaseModel):
    integration: str
    status: Literal["operational", "degraded", "down", "unknown"]
    mode: Literal["normal", "read_only", "manual"]
    detail: str
    evidence_refs: list[str] = Field(default_factory=list)


class ReadinessAssessment(BaseModel):
    id: UUID
    incident_id: UUID
    planes: list[DrPlane] = Field(default_factory=list)
    integrations: list[IntegrationHealth] = Field(default_factory=list)
    checked_at: datetime
    engine: str = "readiness-engine@1"


class HandoffItem(BaseModel):
    key: str
    label: str
    status: str
    ref: str | None = None


class HandoffBrief(BaseModel):
    id: UUID
    incident_id: UUID
    title: str
    summary: str
    open_approvals: list[HandoffItem] = Field(default_factory=list)
    open_acks: list[HandoffItem] = Field(default_factory=list)
    evidence_gaps: list[HandoffItem] = Field(default_factory=list)
    pending_clocks: list[HandoffItem] = Field(default_factory=list)
    readiness: list[HandoffItem] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    generated_by: str = "agent:handoff"
    created_at: datetime
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    note: str | None = None


class HandoffAcknowledgment(BaseModel):
    acknowledged_by: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=1000)


class ActionCatalogEntry(BaseModel):
    action_id: str
    title: str
    description: str
    tier: Literal[1, 2, 3]
    blast_radius: str
    rollback: list[str] = Field(default_factory=list)
    evidence_preservation: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    requires_approval: bool = True
    never_automate: bool = False
    business_hours_only: bool = False
    write_scope: str
    catalog_version: str = "action-catalog@1"


class PolicyDecision(BaseModel):
    id: UUID
    incident_id: UUID
    proposal_id: UUID
    decision: Literal["allow", "deny", "escalate"]
    reasons: list[str] = Field(default_factory=list)
    required_approvals: int = 1
    allowed_roles: list[str] = Field(default_factory=list)
    action_hash: str
    policy_version: str = "policy-engine@1"
    evaluated_at: datetime
    evaluator: str = "policy-engine@1"


class ApprovalCreate(BaseModel):
    approver: str = Field(min_length=1, max_length=200)
    approver_role: Literal["ic", "security", "exec", "legal", "comms"]
    note: str | None = Field(default=None, max_length=500)


class ExecutionStep(BaseModel):
    name: str
    status: Literal["simulated", "refused", "planned"]
    detail: str


class CredentialGrant(BaseModel):
    scope: str
    ttl_seconds: int
    broker: Literal["mock-jit-broker@1"] = "mock-jit-broker@1"
    purpose: str
    note: str


class ExecutionResult(BaseModel):
    id: UUID
    incident_id: UUID
    proposal_id: UUID
    approval_id: UUID | None = None
    action_id: str
    target_asset: str
    status: Literal["simulated", "refused"]
    dry_run: bool
    steps: list[ExecutionStep] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    credential: CredentialGrant | None = None
    requested_by: str
    started_at: datetime
    finished_at: datetime
    executor: str = "executor@1"


class ExecutionRequest(BaseModel):
    requested_by: str = Field(min_length=1, max_length=200)
    dry_run: bool = True


class ContainmentRecord(BaseModel):
    proposal: ActionProposal
    catalog: ActionCatalogEntry | None = None
    decision: PolicyDecision | None = None
    approval: Approval | None = None
    execution: ExecutionResult | None = None
    approval_spent: bool = False


AutonomyLevel = Literal["shadow", "suggest", "approve"]


class ActionWindowStats(BaseModel):
    action_id: str
    window_start: datetime
    window_end: datetime
    proposals: int = 0
    allows: int = 0
    denies: int = 0
    escalates: int = 0
    approvals: int = 0
    approvals_expired: int = 0
    approvals_consumed: int = 0
    simulated: int = 0
    refusals: int = 0
    breaker_trips: int = 0


class AutonomyRecommendation(BaseModel):
    action_id: str
    current_level: AutonomyLevel = "shadow"
    eligible_for_promotion: bool = False
    promotion_reasons: list[str] = Field(default_factory=list)
    hold_reasons: list[str] = Field(default_factory=list)
    demotion_reasons: list[str] = Field(default_factory=list)
    demotion_target: AutonomyLevel | None = None
    thresholds_version: str = "autonomy-thresholds@1"
    computed_at: datetime
    engine: str = "autonomy-engine@1"


class Scorecard(BaseModel):
    action_id: str
    catalog: ActionCatalogEntry | None = None
    stats: ActionWindowStats
    recommendation: AutonomyRecommendation
    level: AutonomyLevel = "shadow"
    level_set_by: str | None = None
    level_set_at: datetime | None = None
    computed_at: datetime
    engine: str = "autonomy-engine@1"


class KillSwitchState(BaseModel):
    engaged: bool = False
    engaged_by: str | None = None
    engaged_at: datetime | None = None
    reason: str | None = None
    released_by: str | None = None
    released_at: datetime | None = None
    source: Literal["database", "environment"] = "database"


class BreakerState(BaseModel):
    action_id: str
    tripped: bool = False
    tripped_at: datetime | None = None
    reason: str | None = None
    consecutive_refusals: int = 0
    reset_at: datetime | None = None
    reset_by: str | None = None


class RateLimitState(BaseModel):
    action_id: str
    window_seconds: int = 3600
    max_per_window: int = 5
    used_in_window: int = 0


class AutomationStatus(BaseModel):
    kill_switch: KillSwitchState
    breakers: list[BreakerState] = Field(default_factory=list)
    rate_limits: list[RateLimitState] = Field(default_factory=list)
    config_profile: str = "local/mock"
    approval_channel: Literal["in-band", "out-of-band"] = "in-band"
    oob_topology: str = "independent-control-plane"
    autonomy_version: str = "autonomy-engine@1"
    thresholds_version: str = "autonomy-thresholds@1"
    promotion_enabled: bool = False
    checked_at: datetime


class KillSwitchRequest(BaseModel):
    engaged: bool
    actor: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=500)


class BreakerResetRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class AutonomyLevelRequest(BaseModel):
    level: AutonomyLevel
    actor: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=500)


class ApprovalRequest(BaseModel):
    id: UUID
    incident_id: UUID
    proposal_id: UUID
    action_id: str
    action_hash: str
    nonce: str
    bundle: dict
    topology: str = "independent-control-plane"
    status: Literal["pending", "approved", "expired"] = "pending"
    created_at: datetime
    expires_at: datetime
    resolved_at: datetime | None = None
    resolved_by: str | None = None


class OobApprovalCreate(BaseModel):
    bundle_id: UUID
    approver: str = Field(min_length=1, max_length=200)
    approver_role: Literal["ic", "security", "exec", "legal", "comms"]
    attestation_signature: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class OobSignRequest(BaseModel):
    bundle_id: UUID


class OobSignResult(BaseModel):
    bundle_id: UUID
    signature: str
    key_id: str = "mock-oob-hmac-sha256-v1"
    note: str
