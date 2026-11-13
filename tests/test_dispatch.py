from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from adjutant import store
from adjutant.dispatch import (
    assess_readiness,
    build_assignment,
    escalation_for,
    map_impacts,
    resolve_owner,
)
from adjutant.errors import ConflictError, PolicyViolation
from adjutant.models import (
    Classification,
    Confidence,
    DispatchAckCreate,
    DispatchResolveCreate,
    DispatchStatus,
    Fact,
    FactCreate,
    FactStatus,
    FactTrust,
    HandoffAcknowledgment,
    Incident,
    IncidentCreate,
)

INCIDENT_ID = uuid4()
NOW = datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc)


def make_incident(**updates) -> Incident:
    data = {
        "id": INCIDENT_ID,
        "title": "Dispatch test incident",
        "severity": "sev1",
        "status": "declared",
        "declared_at": NOW,
        "declared_by": "demo-ic",
        "summary": None,
    }
    data.update(updates)
    return Incident(**data)


def make_fact(
    attribute: str,
    value,
    *,
    trust: FactTrust = FactTrust.TRUSTED,
    status: FactStatus = FactStatus.ASSERTED,
    recorded_at: datetime = NOW,
) -> Fact:
    return Fact(
        id=uuid4(),
        incident_id=INCIDENT_ID,
        attribute=attribute,
        value=value,
        source="test:source",
        valid_at=recorded_at,
        recorded_at=recorded_at,
        confidence=Confidence(),
        status=status,
        classification=Classification.INTERNAL,
        trust=trust,
        evidence=[],
    )


def fact_create(
    attribute: str,
    value,
    *,
    trust: FactTrust = FactTrust.TRUSTED,
) -> FactCreate:
    return FactCreate(
        attribute=attribute,
        value=value,
        source="test:source",
        confidence=Confidence(source_reliability=0.8),
        trust=trust,
    )


def test_fallback_chain_prefers_cmdb_and_records_steps():
    incident = make_incident()
    facts = [
        make_fact("asset/FIN-WS-0142/owner", "cmdb-owner"),
        make_fact("asset/FIN-WS-0142/service", "settlement-batch"),
        make_fact("service/settlement-batch/owner", "service-owner"),
        make_fact("service/settlement-batch/oncall", "oncall-owner"),
    ]

    resolution = resolve_owner("FIN-WS-0142", facts, incident, NOW)

    assert resolution.status == "resolved"
    assert resolution.owner == "cmdb-owner"
    assert resolution.owner_source == "cmdb"
    assert resolution.confidence == pytest.approx(0.95)
    outcomes = {step.attribute: step.outcome for step in resolution.steps}
    assert outcomes["asset/FIN-WS-0142/owner"] == "used"


def test_unknown_cmdb_owner_falls_back_to_service_catalog():
    incident = make_incident()
    facts = [
        make_fact("asset/FIN-WS-0142/owner", "unknown"),
        make_fact("asset/FIN-WS-0142/service", "settlement-batch"),
        make_fact("service/settlement-batch/owner", "Priya Raman"),
        make_fact("service/settlement-batch/oncall", "settlement-oncall"),
    ]

    resolution = resolve_owner("FIN-WS-0142", facts, incident, NOW)

    assert resolution.status == "resolved"
    assert resolution.owner == "Priya Raman"
    assert resolution.owner_source == "service_catalog"
    assert resolution.confidence == pytest.approx(0.85)
    cmdb_step = next(
        step
        for step in resolution.steps
        if step.attribute == "asset/FIN-WS-0142/owner"
    )
    assert cmdb_step.outcome == "rejected"
    assert "no usable owner" in cmdb_step.detail
    assert [candidate.owner for candidate in resolution.candidates] == [
        "Priya Raman",
        "settlement-oncall",
    ]


def test_untrusted_and_disputed_owners_are_rejected():
    incident = make_incident()
    facts = [
        make_fact(
            "asset/FIN-WS-0142/owner",
            "cmdb-owner",
            trust=FactTrust.UNTRUSTED,
        ),
        make_fact(
            "asset/FIN-WS-0142/service",
            "settlement-batch",
            status=FactStatus.DISPUTED,
        ),
        make_fact("asset/FIN-WS-0142/last_assignee", "night-shift"),
    ]

    resolution = resolve_owner("FIN-WS-0142", facts, incident, NOW)

    assert resolution.status == "resolved"
    assert resolution.owner == "night-shift"
    assert resolution.owner_source == "last_assignee"
    rejected = {
        step.attribute: step.detail
        for step in resolution.steps
        if step.outcome == "rejected"
    }
    assert "untrusted" in rejected["asset/FIN-WS-0142/owner"]
    assert "disputed" in rejected["asset/FIN-WS-0142/service"]


def test_hr_directory_is_used_before_last_assignee():
    incident = make_incident()
    facts = [
        make_fact("asset/FIN-WS-0142/hr_manager", "hr-manager"),
        make_fact("asset/FIN-WS-0142/last_assignee", "night-shift"),
        make_fact("asset/FIN-WS-0142/team_lead", "team-lead"),
    ]

    resolution = resolve_owner("FIN-WS-0142", facts, incident, NOW)

    assert resolution.status == "resolved"
    assert resolution.owner == "hr-manager"
    assert resolution.owner_source == "hr_manager"
    assert resolution.confidence == pytest.approx(0.75)


def test_no_owner_escalates_to_incident_commander():
    incident = make_incident()
    facts = [make_fact("asset/FIN-SRV-0007/service", "backup-vault")]

    resolution = resolve_owner("FIN-SRV-0007", facts, incident, NOW)
    assignment = build_assignment(resolution, incident, NOW)

    assert resolution.status == "unknown_owner"
    assert resolution.confidence == 0
    assert resolution.steps[-1].source == "escalation"
    assert "demo-ic" in resolution.steps[-1].detail
    assert assignment is not None
    assert assignment.owner == "unknown_owner"
    assert assignment.contact == "mock://contacts/demo-ic"
    assert assignment.sla_minutes == 15


def test_blank_owner_is_rejected():
    incident = make_incident()
    resolution = resolve_owner(
        "FIN-WS-0142",
        [make_fact("asset/FIN-WS-0142/owner", "  ")],
        incident,
        NOW,
    )
    assert resolution.status == "unknown_owner"


def test_escalation_only_after_due_and_reroutes_to_deputy_for_ic():
    incident = make_incident()
    resolution = resolve_owner(
        "FIN-WS-0142",
        [make_fact("asset/FIN-WS-0142/owner", "owner")],
        incident,
        NOW,
    )
    assignment = build_assignment(resolution, incident, NOW)
    assert assignment is not None

    assert escalation_for(assignment, incident, NOW + timedelta(minutes=14)) is None
    assert (
        escalation_for(assignment, incident, NOW + timedelta(minutes=15))
        == "demo-ic"
    )

    acked = assignment.model_copy(update={"status": DispatchStatus.ACKED})
    assert escalation_for(acked, incident, NOW + timedelta(hours=1)) is None

    ic_owned = assignment.model_copy(update={"owner": "demo-ic"})
    assert (
        escalation_for(ic_owned, incident, NOW + timedelta(minutes=20))
        == "deputy-ic"
    )


def test_impact_mapping_reports_gaps_instead_of_guessing():
    incident = make_incident()
    facts = [
        make_fact("asset/FIN-WS-0142/criticality", "high"),
        make_fact("asset/FIN-WS-0142/service", "settlement-batch"),
        make_fact("service/settlement-batch/rto_minutes", 60),
        make_fact("asset/FIN-SRV-0007/role", "backup staging"),
    ]

    mappings = {m.asset: m for m in map_impacts(incident, facts, NOW)}

    primary = mappings["FIN-WS-0142"]
    assert primary.status == "partial"
    assert primary.rto_minutes == 60
    assert primary.rto_deadline == NOW + timedelta(minutes=60)
    assert "RPO missing" in primary.gaps

    orphan = mappings["FIN-SRV-0007"]
    assert orphan.status == "unknown"
    assert orphan.service is None
    assert "service mapping missing" in orphan.gaps
    assert "criticality missing" in orphan.gaps


def test_readiness_marks_untrusted_evidence_as_unknown_and_manual():
    incident = make_incident()
    facts = [
        make_fact(
            "identity/svc-settlement/status",
            "credentials possibly exposed",
            status=FactStatus.DISPUTED,
        ),
        make_fact("identity/admin/status", "credentials compromised"),
        make_fact("backup/FIN-SRV-0007/last_verify", "failed"),
        make_fact("integration/edr/status", "operational"),
        make_fact("integration/cmdb/status", "degraded"),
        make_fact("network/segmentation/status", "enforced"),
    ]

    assessment = assess_readiness(incident, facts, NOW)

    planes = {plane.plane: plane for plane in assessment.planes}
    assert planes["identity"].status == "compromised"
    assert planes["backup"].status == "degraded"
    assert planes["edr"].status == "healthy"
    assert planes["itsm"].status == "unknown"
    assert planes["network"].status == "healthy"

    integrations = {i.integration: i for i in assessment.integrations}
    assert integrations["cmdb"].mode == "read_only"
    assert integrations["itsm"].status == "unknown"
    assert integrations["itsm"].mode == "manual"
    assert integrations["comms"].mode == "manual"


@pytest.mark.asyncio
async def test_dispatch_resolve_ack_and_unknown_owner(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(
            title="Dispatch integration", severity="sev1", declared_by="demo-ic"
        ),
    )
    for attribute, value in (
        ("asset/FIN-WS-0142/owner", "unknown"),
        ("asset/FIN-WS-0142/service", "settlement-batch"),
        ("service/settlement-batch/owner", "Priya Raman"),
        ("service/settlement-batch/rto_minutes", 60),
        ("service/settlement-batch/rpo_minutes", 15),
    ):
        await store.append_fact(pool, incident.id, fact_create(attribute, value))

    resolved = await store.resolve_dispatch(
        pool, incident.id, DispatchResolveCreate(asset="FIN-WS-0142")
    )
    assert resolved.resolution.status == "resolved"
    assert resolved.resolution.owner == "Priya Raman"
    assert resolved.assignment is not None
    assert resolved.assignment.status is DispatchStatus.PENDING

    assignment_id = resolved.assignment.id
    with pytest.raises(PolicyViolation):
        await store.ack_dispatch(
            pool,
            incident.id,
            assignment_id,
            DispatchAckCreate(acked_by="agent:dispatch"),
        )

    acked = await store.ack_dispatch(
        pool,
        incident.id,
        assignment_id,
        DispatchAckCreate(acked_by="Priya Raman", note="Synthetic ack"),
    )
    assert acked.assignment is not None
    assert acked.assignment.status is DispatchStatus.ACKED
    assert acked.assignment.ack_by == "Priya Raman"
    assert acked.assignment.sla_met is True

    with pytest.raises(ConflictError):
        await store.ack_dispatch(
            pool,
            incident.id,
            assignment_id,
            DispatchAckCreate(acked_by="Priya Raman"),
        )

    orphan = await store.resolve_dispatch(
        pool, incident.id, DispatchResolveCreate(asset="FIN-SRV-0007")
    )
    assert orphan.resolution.status == "unknown_owner"
    assert orphan.assignment is not None
    assert orphan.assignment.owner == "unknown_owner"
    assert orphan.assignment.contact == "mock://contacts/demo-ic"

    records = await store.list_dispatch(pool, incident.id)
    assert len(records) == 2

    escalated = await store.evaluate_dispatch(
        pool, incident.id, now=datetime.now(timezone.utc) + timedelta(days=1)
    )
    by_asset = {record.assignment.asset: record.assignment for record in escalated}
    assert by_asset["FIN-WS-0142"].status is DispatchStatus.ACKED
    assert by_asset["FIN-SRV-0007"].status is DispatchStatus.ESCALATED
    assert by_asset["FIN-SRV-0007"].escalated_to == "demo-ic"

    timeline = await store.list_timeline(pool, incident.id)
    assert "dispatch.escalated" in [event.event_type for event in timeline]

    audit = await store.verify_audit(pool)
    assert audit.valid is True


@pytest.mark.asyncio
async def test_impact_readiness_and_handoff_flow(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(
            title="BCP integration", severity="sev2", declared_by="demo-ic"
        ),
    )
    for attribute, value in (
        ("asset/FIN-WS-0142/criticality", "high"),
        ("asset/FIN-WS-0142/service", "settlement-batch"),
        ("service/settlement-batch/rto_minutes", 60),
        ("service/settlement-batch/rpo_minutes", 15),
        ("asset/FIN-SRV-0007/role", "backup staging"),
        ("integration/cmdb/status", "degraded"),
        ("backup/FIN-SRV-0007/last_verify", "verified"),
    ):
        await store.append_fact(pool, incident.id, fact_create(attribute, value))

    await store.resolve_dispatch(
        pool, incident.id, DispatchResolveCreate(asset="FIN-SRV-0007")
    )

    mappings = await store.map_impact(pool, incident.id)
    by_asset = {mapping.asset: mapping for mapping in mappings}
    assert by_asset["FIN-WS-0142"].status == "mapped"
    assert by_asset["FIN-WS-0142"].rto_deadline is not None
    assert by_asset["FIN-SRV-0007"].status == "unknown"
    assert "service mapping missing" in by_asset["FIN-SRV-0007"].gaps

    assert len(await store.list_impacts(pool, incident.id)) == 2

    assessment = await store.assess_readiness(pool, incident.id)
    assert assessment.integrations
    latest = await store.latest_readiness(pool, incident.id)
    assert latest is not None
    assert latest.id == assessment.id

    handoff = await store.create_handoff(pool, incident.id)
    assert any(
        item.status == "unknown_owner" for item in handoff.evidence_gaps
    )
    assert any(
        "FIN-SRV-0007" in item.label for item in handoff.open_acks
    )
    assert any("cmdb" in item.label for item in handoff.evidence_gaps)
    assert any(
        check.startswith("open_acks=") for check in handoff.checks
    )
    assert "no send path exists" in handoff.checks[-1]

    latest_handoff = await store.latest_handoff(pool, incident.id)
    assert latest_handoff is not None
    assert latest_handoff.id == handoff.id

    with pytest.raises(PolicyViolation):
        await store.acknowledge_handoff(
            pool,
            incident.id,
            handoff.id,
            HandoffAcknowledgment(acknowledged_by="agent:handoff"),
        )

    acknowledged = await store.acknowledge_handoff(
        pool,
        incident.id,
        handoff.id,
        HandoffAcknowledgment(
            acknowledged_by="deputy-ic", note="Synthetic shift handoff"
        ),
    )
    assert acknowledged.acknowledged_by == "deputy-ic"
    assert acknowledged.acknowledged_at is not None

    with pytest.raises(ConflictError):
        await store.acknowledge_handoff(
            pool,
            incident.id,
            handoff.id,
            HandoffAcknowledgment(acknowledged_by="deputy-ic"),
        )

    audit = await store.verify_audit(pool)
    assert audit.valid is True
