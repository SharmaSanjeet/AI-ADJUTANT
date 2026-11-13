from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Iterable
from uuid import UUID, uuid4

from .models import (
    ActionProposal,
    BriefRecord,
    BriefStatus,
    ClockCandidate,
    ClockStatus,
    DispatchAssignment,
    DispatchRecord,
    DispatchStatus,
    DrPlane,
    Fact,
    FactStatus,
    FactTrust,
    HandoffBrief,
    HandoffItem,
    ImpactMapping,
    Incident,
    IntegrationHealth,
    OwnerCandidate,
    OwnerResolution,
    ReadinessAssessment,
    ReadinessCheck,
    ResolutionStep,
)

ACK_SLA_MINUTES = {"sev1": 15, "sev2": 30, "sev3": 60, "sev4": 120}
UNKNOWN_VALUES = {"", "unknown", "tbd", "none", "n/a", "unassigned"}
OWNER_SOURCES = [
    ("cmdb", 0.95),
    ("service_catalog", 0.85),
    ("oncall_roster", 0.80),
    ("hr_manager", 0.75),
    ("last_assignee", 0.65),
    ("team_lead", 0.55),
]
INTEGRATIONS = ["edr", "cmdb", "itsm", "backup", "comms"]


def contact_handle(owner: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", owner.strip().lower()).strip("-")
    return f"mock://contacts/{slug or 'unassigned'}"


def _current(facts: Iterable[Fact]) -> list[Fact]:
    return [
        fact
        for fact in facts
        if fact.status not in (FactStatus.SUPERSEDED, FactStatus.RETRACTED)
    ]


def _latest(facts: list[Fact], attribute: str) -> Fact | None:
    matches = [fact for fact in facts if fact.attribute == attribute]
    if not matches:
        return None
    return max(matches, key=lambda fact: fact.recorded_at)


def _identifier(value: Any) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.lower() in UNKNOWN_VALUES:
            return None
        return normalized
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _reject_reason(fact: Fact) -> str | None:
    if fact.trust is not FactTrust.TRUSTED:
        return f"source is {fact.trust.value}"
    if fact.status is FactStatus.DISPUTED:
        return "fact is disputed"
    return None


def _evidence_refs(fact: Fact) -> list[str]:
    return [evidence.ref for evidence in fact.evidence]


def resolve_owner(
    asset: str,
    facts: list[Fact],
    incident: Incident,
    now: datetime,
) -> OwnerResolution:
    current = _current(facts)
    steps: list[ResolutionStep] = []
    candidates: list[OwnerCandidate] = []
    confidence_by_source = dict(OWNER_SOURCES)

    def consider(source: str, attribute: str, note: str | None = None) -> str | None:
        fact = _latest(current, attribute)
        if fact is None:
            steps.append(
                ResolutionStep(
                    source=source,
                    attribute=attribute,
                    outcome="missing",
                    detail="no fact recorded",
                )
            )
            return None
        reason = _reject_reason(fact)
        owner = _identifier(fact.value)
        if reason:
            steps.append(
                ResolutionStep(
                    source=source,
                    attribute=attribute,
                    outcome="rejected",
                    detail=reason,
                    fact_id=fact.id,
                )
            )
            return None
        if owner is None:
            steps.append(
                ResolutionStep(
                    source=source,
                    attribute=attribute,
                    outcome="rejected",
                    detail=f"no usable owner (value {fact.value!r})",
                    fact_id=fact.id,
                )
            )
            return None
        steps.append(
            ResolutionStep(
                source=source,
                attribute=attribute,
                outcome="used",
                detail=f"owner {owner}",
                fact_id=fact.id,
            )
        )
        candidates.append(
            OwnerCandidate(
                source=source,
                owner=owner,
                contact=contact_handle(owner),
                confidence=confidence_by_source[source],
                fact_id=fact.id,
                evidence_refs=_evidence_refs(fact),
                note=note,
            )
        )
        return owner

    consider("cmdb", f"asset/{asset}/owner", "CMDB asset record")

    service: str | None = None
    service_fact = _latest(current, f"asset/{asset}/service")
    if service_fact is None:
        steps.append(
            ResolutionStep(
                source="service_catalog",
                attribute=f"asset/{asset}/service",
                outcome="missing",
                detail="no service mapping",
            )
        )
    else:
        reason = _reject_reason(service_fact)
        service = _identifier(service_fact.value)
        if reason or service is None:
            steps.append(
                ResolutionStep(
                    source="service_catalog",
                    attribute=f"asset/{asset}/service",
                    outcome="rejected",
                    detail=reason or "no usable service name",
                    fact_id=service_fact.id,
                )
            )
            service = None
        else:
            steps.append(
                ResolutionStep(
                    source="service_catalog",
                    attribute=f"asset/{asset}/service",
                    outcome="used",
                    detail=f"service {service}",
                    fact_id=service_fact.id,
                )
            )

    if service:
        consider("service_catalog", f"service/{service}/owner", "service catalog owner")
        consider("oncall_roster", f"service/{service}/oncall", "on-call roster")

    consider("hr_manager", f"asset/{asset}/hr_manager", "HR directory manager")
    consider("last_assignee", f"asset/{asset}/last_assignee", "last known assignee")
    if service:
        consider("team_lead", f"service/{service}/team_lead", "service team lead")

    if not candidates:
        steps.append(
            ResolutionStep(
                source="escalation",
                attribute="incident/commander",
                outcome="used",
                detail=(
                    "no accountable owner resolved; acknowledgements route to the "
                    f"incident commander {incident.declared_by}"
                ),
            )
        )
        return OwnerResolution(
            id=uuid4(),
            incident_id=incident.id,
            asset=asset,
            status="unknown_owner",
            contact=contact_handle(incident.declared_by),
            confidence=0.0,
            candidates=[],
            steps=steps,
            resolved_at=now,
        )

    top = candidates[0]
    ambiguous = any(
        candidate.confidence == top.confidence and candidate.owner != top.owner
        for candidate in candidates[1:]
    )
    return OwnerResolution(
        id=uuid4(),
        incident_id=incident.id,
        asset=asset,
        status="ambiguous" if ambiguous else "resolved",
        owner=None if ambiguous else top.owner,
        owner_source=None if ambiguous else top.source,
        contact=None if ambiguous else top.contact,
        confidence=0.0 if ambiguous else top.confidence,
        candidates=candidates,
        steps=steps,
        resolved_at=now,
    )


def ack_due_at(assigned_at: datetime, severity: str) -> tuple[datetime, int]:
    minutes = ACK_SLA_MINUTES.get(severity, 60)
    return assigned_at + timedelta(minutes=minutes), minutes


def build_assignment(
    resolution: OwnerResolution,
    incident: Incident,
    now: datetime,
) -> DispatchAssignment | None:
    if resolution.status == "ambiguous":
        return None
    due_at, minutes = ack_due_at(now, incident.severity.value)
    if resolution.status == "unknown_owner":
        return DispatchAssignment(
            id=uuid4(),
            incident_id=incident.id,
            resolution_id=resolution.id,
            asset=resolution.asset,
            owner="unknown_owner",
            contact=resolution.contact or contact_handle(incident.declared_by),
            status=DispatchStatus.PENDING,
            assigned_at=now,
            ack_due_at=due_at,
            sla_minutes=minutes,
            note=(
                "No accountable owner resolved. Acknowledgement routed to the "
                f"incident commander {incident.declared_by}."
            ),
        )
    return DispatchAssignment(
        id=uuid4(),
        incident_id=incident.id,
        resolution_id=resolution.id,
        asset=resolution.asset,
        owner=resolution.owner or "unknown_owner",
        contact=resolution.contact or contact_handle(incident.declared_by),
        status=DispatchStatus.PENDING,
        assigned_at=now,
        ack_due_at=due_at,
        sla_minutes=minutes,
        note=f"Owner resolved via {resolution.owner_source}.",
    )


def escalation_for(
    assignment: DispatchAssignment,
    incident: Incident,
    now: datetime,
) -> str | None:
    if assignment.status is not DispatchStatus.PENDING:
        return None
    if now < assignment.ack_due_at:
        return None
    target = incident.declared_by
    if assignment.owner == target:
        return "deputy-ic"
    return target


def _asset_names(facts: list[Fact]) -> list[str]:
    assets = set()
    for fact in facts:
        parts = fact.attribute.split("/")
        if len(parts) >= 3 and parts[0] == "asset" and parts[1]:
            assets.add(parts[1])
    return sorted(assets)


def map_impacts(
    incident: Incident,
    facts: list[Fact],
    now: datetime,
) -> list[ImpactMapping]:
    current = _current(facts)
    mappings: list[ImpactMapping] = []

    for asset in _asset_names(current):
        gaps: list[str] = []
        evidence: list[str] = []

        criticality_fact = _latest(current, f"asset/{asset}/criticality")
        criticality = None
        if criticality_fact is None:
            gaps.append("criticality missing")
        else:
            reason = _reject_reason(criticality_fact)
            value = _identifier(criticality_fact.value)
            if reason or value is None:
                gaps.append(f"criticality unusable ({reason or 'empty value'})")
            else:
                criticality = value
                evidence.extend(_evidence_refs(criticality_fact))

        service_fact = _latest(current, f"asset/{asset}/service")
        service = None
        if service_fact is None:
            gaps.append("service mapping missing")
        else:
            reason = _reject_reason(service_fact)
            service = _identifier(service_fact.value)
            if reason or service is None:
                gaps.append(f"service mapping unusable ({reason or 'empty value'})")
                service = None
            else:
                evidence.extend(_evidence_refs(service_fact))

        rto = rpo = None
        if service:
            for name, attribute, target in (
                ("RTO", f"service/{service}/rto_minutes", "rto"),
                ("RPO", f"service/{service}/rpo_minutes", "rpo"),
            ):
                fact = _latest(current, attribute)
                if fact is None:
                    gaps.append(f"{name} missing")
                    continue
                reason = _reject_reason(fact)
                if reason:
                    gaps.append(f"{name} unusable ({reason})")
                    continue
                try:
                    minutes = int(fact.value)
                except (TypeError, ValueError):
                    gaps.append(f"{name} is not an integer")
                    continue
                if target == "rto":
                    rto = minutes
                else:
                    rpo = minutes
                evidence.extend(_evidence_refs(fact))
        else:
            gaps.extend(["RTO missing", "RPO missing"])

        if service and (rto is not None or rpo is not None):
            status = "mapped" if not gaps else "partial"
        elif service or criticality:
            status = "partial"
        else:
            status = "unknown"

        mappings.append(
            ImpactMapping(
                id=uuid4(),
                incident_id=incident.id,
                asset=asset,
                service=service,
                criticality=criticality,
                rto_minutes=rto,
                rpo_minutes=rpo,
                rto_deadline=(
                    incident.declared_at + timedelta(minutes=rto)
                    if rto is not None
                    else None
                ),
                status=status,
                gaps=gaps,
                evidence_refs=sorted(set(evidence)),
                mapped_at=now,
            )
        )
    return mappings


def _integration_health(facts: list[Fact], name: str) -> IntegrationHealth:
    fact = _latest(_current(facts), f"integration/{name}/status")
    if fact is None:
        return IntegrationHealth(
            integration=name,
            status="unknown",
            mode="manual",
            detail="no health fact recorded; assume manual operations",
        )
    reason = _reject_reason(fact)
    status = _identifier(fact.value)
    status = status.lower() if isinstance(status, str) else None
    if reason or status not in {"operational", "degraded", "down"}:
        return IntegrationHealth(
            integration=name,
            status="unknown",
            mode="manual",
            detail=f"health fact unusable ({reason or fact.value!r}); assume manual",
            evidence_refs=_evidence_refs(fact),
        )
    mode = {"operational": "normal", "degraded": "read_only", "down": "manual"}[status]
    return IntegrationHealth(
        integration=name,
        status=status,
        mode=mode,
        detail=f"reported {status} by {fact.source}",
        evidence_refs=_evidence_refs(fact),
    )


def _plane_status(checks: list[ReadinessCheck]) -> str:
    outcomes = {check.outcome for check in checks}
    if "fail" in outcomes:
        return "degraded"
    if "unknown" in outcomes:
        return "unknown"
    return "healthy"


def assess_readiness(
    incident: Incident,
    facts: list[Fact],
    now: datetime,
) -> ReadinessAssessment:
    current = _current(facts)
    integrations = [_integration_health(current, name) for name in INTEGRATIONS]
    by_name = {health.integration: health for health in integrations}

    planes: list[DrPlane] = []

    identity_checks: list[ReadinessCheck] = []
    identity_facts = [
        fact for fact in current if fact.attribute.startswith("identity/")
    ]
    for fact in identity_facts:
        value = _identifier(fact.value) or ""
        refs = _evidence_refs(fact)
        if fact.status is FactStatus.DISPUTED:
            identity_checks.append(
                ReadinessCheck(
                    name=fact.attribute,
                    outcome="fail",
                    detail=f"identity claim is disputed ({value})",
                    evidence_refs=refs,
                )
            )
        elif "compromised" in value.lower():
            identity_checks.append(
                ReadinessCheck(
                    name=fact.attribute,
                    outcome="fail",
                    detail=f"identity compromise asserted ({value})",
                    evidence_refs=refs,
                )
            )
        elif any(token in value.lower() for token in ("exposed", "possible")):
            identity_checks.append(
                ReadinessCheck(
                    name=fact.attribute,
                    outcome="unknown",
                    detail=f"possible exposure, not confirmed ({value})",
                    evidence_refs=refs,
                )
            )
        else:
            identity_checks.append(
                ReadinessCheck(
                    name=fact.attribute,
                    outcome="pass",
                    detail=f"no compromise indicated ({value})",
                    evidence_refs=refs,
                )
            )
    if not identity_checks:
        identity_checks.append(
            ReadinessCheck(
                name="identity/evidence",
                outcome="unknown",
                detail="no identity-plane evidence recorded",
            )
        )
    identity_status = _plane_status(identity_checks)
    if any(
        "compromise asserted" in check.detail and check.outcome == "fail"
        for check in identity_checks
    ):
        identity_status = "compromised"
    planes.append(DrPlane(plane="identity", status=identity_status, checks=identity_checks))

    backup_checks: list[ReadinessCheck] = []
    for fact in current:
        if not fact.attribute.startswith("backup/"):
            continue
        value = (_identifier(fact.value) or "").lower()
        refs = _evidence_refs(fact)
        if fact.status is FactStatus.DISPUTED or _reject_reason(fact):
            outcome, detail = "unknown", "backup evidence is not trustworthy"
        elif value in {"verified", "healthy", "ok"}:
            outcome, detail = "pass", f"backup {value}"
        elif value in {"failed", "corrupt", "missing"}:
            outcome, detail = "fail", f"backup {value}"
        else:
            outcome, detail = "unknown", f"backup state {value or 'empty'}"
        backup_checks.append(
            ReadinessCheck(
                name=fact.attribute,
                outcome=outcome,
                detail=detail,
                evidence_refs=refs,
            )
        )
    if not backup_checks:
        backup_checks.append(
            ReadinessCheck(
                name="backup/evidence",
                outcome="unknown",
                detail="no backup verification evidence recorded",
            )
        )
    planes.append(
        DrPlane(plane="backup", status=_plane_status(backup_checks), checks=backup_checks)
    )

    for plane, name in (("edr", "edr"), ("itsm", "itsm")):
        health = by_name[name]
        if health.status == "operational":
            outcome = "pass"
        elif health.status == "unknown":
            outcome = "unknown"
        else:
            outcome = "fail"
        planes.append(
            DrPlane(
                plane=plane,
                status="healthy" if outcome == "pass" else (
                    "degraded" if outcome == "fail" else "unknown"
                ),
                checks=[
                    ReadinessCheck(
                        name=f"integration/{name}",
                        outcome=outcome,
                        detail=health.detail,
                        evidence_refs=health.evidence_refs,
                    )
                ],
            )
        )

    network_fact = _latest(current, "network/segmentation/status")
    if network_fact is None:
        network_checks = [
            ReadinessCheck(
                name="network/segmentation/status",
                outcome="unknown",
                detail="no segmentation evidence recorded",
            )
        ]
    else:
        value = (_identifier(network_fact.value) or "").lower()
        outcome = "pass" if value in {"enforced", "healthy", "ok"} else "unknown"
        network_checks = [
            ReadinessCheck(
                name="network/segmentation/status",
                outcome=outcome,
                detail=f"segmentation {value or 'empty'}",
                evidence_refs=_evidence_refs(network_fact),
            )
        ]
    planes.append(
        DrPlane(
            plane="network",
            status=_plane_status(network_checks),
            checks=network_checks,
        )
    )

    return ReadinessAssessment(
        id=uuid4(),
        incident_id=incident.id,
        planes=planes,
        integrations=integrations,
        checked_at=now,
    )


def _brief_label(record: BriefRecord) -> str:
    title = record.brief.title
    if len(title) > 140:
        title = f"{title[:137]}…"
    return title


def build_handoff(
    incident: Incident,
    facts: list[Fact],
    briefs: list[BriefRecord],
    proposals: list[ActionProposal],
    clocks: list[ClockCandidate],
    dispatches: list[DispatchRecord],
    impacts: list[ImpactMapping],
    readiness: ReadinessAssessment | None,
    now: datetime,
) -> HandoffBrief:
    current = _current(facts)

    open_approvals: list[HandoffItem] = []
    for record in briefs:
        if record.brief.status is BriefStatus.DRAFT:
            open_approvals.append(
                HandoffItem(
                    key=f"brief:{record.brief.id}",
                    label=_brief_label(record),
                    status="draft awaiting approval",
                    ref=str(record.brief.id),
                )
            )
        elif record.brief.status is BriefStatus.APPROVED and record.send is None:
            open_approvals.append(
                HandoffItem(
                    key=f"brief:{record.brief.id}",
                    label=_brief_label(record),
                    status="approved, not sent",
                    ref=str(record.brief.id),
                )
            )
    for proposal in proposals:
        open_approvals.append(
            HandoffItem(
                key=f"proposal:{proposal.id}",
                label=f"{proposal.action_id} on {proposal.target_asset}",
                status="proposal awaiting decision",
                ref=str(proposal.id),
            )
        )

    open_acks: list[HandoffItem] = []
    for record in dispatches:
        assignment = record.assignment
        if assignment is None or assignment.status is DispatchStatus.ACKED:
            continue
        if assignment.status is DispatchStatus.ESCALATED:
            status = f"escalated to {assignment.escalated_to}"
        else:
            status = "acknowledgement pending"
        open_acks.append(
            HandoffItem(
                key=f"assignment:{assignment.id}",
                label=f"{assignment.asset} → {assignment.owner}",
                status=status,
                ref=str(assignment.id),
            )
        )

    evidence_gaps: list[HandoffItem] = []
    for record in dispatches:
        if record.resolution.status == "unknown_owner":
            evidence_gaps.append(
                HandoffItem(
                    key=f"owner:{record.resolution.asset}",
                    label=f"no accountable owner for {record.resolution.asset}",
                    status="unknown_owner",
                    ref=str(record.resolution.id),
                )
            )
    for mapping in impacts:
        for gap in mapping.gaps:
            evidence_gaps.append(
                HandoffItem(
                    key=f"impact:{mapping.asset}:{gap}",
                    label=f"{mapping.asset}: {gap}",
                    status="impact gap",
                    ref=str(mapping.id),
                )
            )
    if readiness:
        for plane in readiness.planes:
            if plane.status != "healthy":
                evidence_gaps.append(
                    HandoffItem(
                        key=f"plane:{plane.plane}",
                        label=f"DR plane {plane.plane} is {plane.status}",
                        status=plane.status,
                        ref=str(readiness.id),
                    )
                )
        for health in readiness.integrations:
            if health.status != "operational":
                evidence_gaps.append(
                    HandoffItem(
                        key=f"integration:{health.integration}",
                        label=(
                            f"integration {health.integration} is {health.status} "
                            f"({health.mode})"
                        ),
                        status=health.status,
                        ref=str(readiness.id),
                    )
                )
    for fact in current:
        if fact.trust is FactTrust.TRUSTED and not fact.evidence:
            evidence_gaps.append(
                HandoffItem(
                    key=f"evidence:{fact.id}",
                    label=f"fact {fact.attribute} has no evidence reference",
                    status="missing evidence",
                    ref=str(fact.id),
                )
            )

    pending_clocks: list[HandoffItem] = []
    for clock in clocks:
        if clock.status is ClockStatus.CANDIDATE:
            pending_clocks.append(
                HandoffItem(
                    key=f"clock:{clock.id}",
                    label=f"{clock.label} due {clock.due_at.isoformat()}",
                    status="awaiting legal confirmation",
                    ref=str(clock.id),
                )
            )

    readiness_items: list[HandoffItem] = []
    if readiness:
        for plane in readiness.planes:
            readiness_items.append(
                HandoffItem(
                    key=f"plane:{plane.plane}",
                    label=f"DR plane {plane.plane}",
                    status=plane.status,
                    ref=str(readiness.id),
                )
            )
        for health in readiness.integrations:
            readiness_items.append(
                HandoffItem(
                    key=f"integration:{health.integration}",
                    label=f"integration {health.integration}",
                    status=f"{health.status} / {health.mode}",
                    ref=str(readiness.id),
                )
            )

    checks = [
        f"open_approvals={len(open_approvals)} "
        f"(briefs={len(briefs)}, proposals={len(proposals)})",
        f"open_acks={len(open_acks)} (dispatch records={len(dispatches)})",
        f"evidence_gaps={len(evidence_gaps)} (facts checked={len(current)})",
        f"pending_clocks={len(pending_clocks)} (clocks={len(clocks)})",
        (
            f"readiness_planes={len(readiness.planes)} "
            f"integrations={len(readiness.integrations)}"
            if readiness
            else "readiness=not assessed"
        ),
        "handoff is display-only; no send path exists",
    ]

    summary = (
        f"{len(open_approvals)} open approvals, {len(open_acks)} open "
        f"acknowledgements, {len(evidence_gaps)} evidence gaps, and "
        f"{len(pending_clocks)} pending clocks."
    )

    return HandoffBrief(
        id=uuid4(),
        incident_id=incident.id,
        title=f"Shift handoff — {incident.title}"[:200],
        summary=summary,
        open_approvals=open_approvals,
        open_acks=open_acks,
        evidence_gaps=evidence_gaps,
        pending_clocks=pending_clocks,
        readiness=readiness_items,
        checks=checks,
        created_at=now,
    )
