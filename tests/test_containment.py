from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from adjutant import store
from adjutant.containment import (
    ACTION_CATALOG,
    APPROVAL_TTL_MINUTES,
    action_hash,
    catalog,
    check_approval,
    evaluate_policy,
    is_business_hours,
    sign_approval_record,
    verify_signature,
)
from adjutant.errors import ConflictError, PolicyViolation
from adjutant.containment import approval_core
from adjutant.models import (
    ActionProposal,
    ActionProposalCreate,
    ApprovalCreate,
    Classification,
    Confidence,
    ExecutionRequest,
    Fact,
    FactCreate,
    FactStatus,
    FactTrust,
    IncidentCreate,
)

INCIDENT_ID = uuid4()
NOW = datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc)


def make_proposal(
    action_id: str = "isolate_endpoint",
    tier: int = 2,
    refs=None,
    asset: str = "FIN-WS-0142",
    params=None,
) -> ActionProposal:
    return ActionProposal(
        id=uuid4(),
        incident_id=INCIDENT_ID,
        action_id=action_id,
        params=params or {},
        target_asset=asset,
        tier=tier,
        justification_refs=refs or [],
        proposed_by="agent:containment-advisor",
        created_at=NOW,
    )


def make_fact(
    attribute: str,
    value,
    *,
    trust: FactTrust = FactTrust.TRUSTED,
    status: FactStatus = FactStatus.ASSERTED,
) -> Fact:
    return Fact(
        id=uuid4(),
        incident_id=INCIDENT_ID,
        attribute=attribute,
        value=value,
        source="test:source",
        valid_at=NOW,
        recorded_at=NOW,
        confidence=Confidence(),
        status=status,
        classification=Classification.INTERNAL,
        trust=trust,
        evidence=[],
    )


def fact_create(attribute: str, value) -> FactCreate:
    return FactCreate(
        attribute=attribute,
        value=value,
        source="test:source",
        confidence=Confidence(source_reliability=0.8),
    )


def test_catalog_entries_are_complete():
    entries = catalog()
    assert len(entries) == len(ACTION_CATALOG)
    for entry in entries:
        assert entry.title
        assert entry.description
        assert entry.blast_radius
        assert entry.write_scope
        assert entry.evidence_preservation, entry.action_id
        assert entry.preconditions
        assert entry.requires_approval is True
    destructive = [e for e in entries if e.tier == 3]
    assert destructive
    assert all(e.never_automate for e in destructive)
    assert {"wipe_host", "disable_backup_jobs", "pay_ransom"} <= set(
        ACTION_CATALOG
    )
    reversible = [e for e in entries if not e.never_automate]
    assert all(e.rollback for e in reversible)


def test_policy_allows_well_evidenced_proposal():
    behaviour = make_fact("asset/FIN-WS-0142/behaviour", "encryption observed")
    asset_fact = make_fact("asset/FIN-WS-0142/owner", "Priya Raman")
    proposal = make_proposal(refs=[behaviour.id, asset_fact.id])

    decision = evaluate_policy(proposal, [behaviour, asset_fact], NOW)

    assert decision.decision == "allow"
    assert decision.allowed_roles == ["ic"]
    assert decision.action_hash == action_hash(proposal)
    assert any("current, trusted" in reason for reason in decision.reasons)


def test_policy_escalates_on_never_automate():
    behaviour = make_fact("asset/FIN-WS-0142/behaviour", "encryption observed")
    proposal = make_proposal(action_id="wipe_host", tier=3, refs=[behaviour.id])

    decision = evaluate_policy(proposal, [behaviour], NOW)

    assert decision.decision == "escalate"
    assert decision.allowed_roles == []
    assert "never-automate" in decision.reasons[0]


def test_policy_escalates_on_bad_citations():
    trusted = make_fact("asset/FIN-WS-0142/behaviour", "encryption observed")
    disputed = make_fact(
        "asset/FIN-WS-0142/exposure",
        "credentials exposed",
        status=FactStatus.DISPUTED,
    )
    untrusted = make_fact(
        "asset/FIN-WS-0142/actor",
        "attacker",
        trust=FactTrust.UNTRUSTED,
    )
    superseded = make_fact(
        "asset/FIN-WS-0142/owner",
        "someone",
        status=FactStatus.SUPERSEDED,
    )
    asset_fact = make_fact("asset/FIN-WS-0142/owner", "Priya Raman")
    facts = [trusted, disputed, untrusted, superseded, asset_fact]

    no_refs = evaluate_policy(make_proposal(refs=[]), facts, NOW)
    missing = evaluate_policy(make_proposal(refs=[uuid4()]), facts, NOW)
    disputed_decision = evaluate_policy(
        make_proposal(refs=[disputed.id]), facts, NOW
    )
    untrusted_decision = evaluate_policy(
        make_proposal(refs=[untrusted.id]), facts, NOW
    )
    superseded_decision = evaluate_policy(
        make_proposal(refs=[superseded.id]), facts, NOW
    )

    for decision in (
        no_refs,
        missing,
        disputed_decision,
        untrusted_decision,
        superseded_decision,
    ):
        assert decision.decision == "escalate"
        assert decision.allowed_roles == ["ic"]
    assert "no cited facts" in no_refs.reasons[0]
    assert "do not exist" in missing.reasons[0]
    assert "disputed" in disputed_decision.reasons[0]
    assert "untrusted" in untrusted_decision.reasons[0]
    assert "superseded" in superseded_decision.reasons[0]


def test_policy_denies_unknown_action_and_tier_mismatch():
    asset_fact = make_fact("asset/FIN-WS-0142/owner", "Priya Raman")

    unknown = evaluate_policy(
        make_proposal(action_id="nuke_everything"), [asset_fact], NOW
    )
    mismatch = evaluate_policy(
        make_proposal(action_id="isolate_endpoint", tier=1, refs=[asset_fact.id]),
        [asset_fact],
        NOW,
    )

    assert unknown.decision == "deny"
    assert unknown.allowed_roles == []
    assert mismatch.decision == "deny"
    assert "tier" in mismatch.reasons[0]


def test_policy_escalates_outside_business_hours():
    asset_fact = make_fact("asset/FIN-WS-0142/owner", "Priya Raman")
    proposal = make_proposal(
        action_id="disable_service_account", tier=1, refs=[asset_fact.id]
    )
    facts = [asset_fact]

    wednesday = datetime(2026, 1, 7, 10, 0, tzinfo=timezone.utc)
    sunday = datetime(2026, 1, 4, 12, 0, tzinfo=timezone.utc)
    early = datetime(2026, 1, 7, 6, 0, tzinfo=timezone.utc)
    evening = datetime(2026, 1, 7, 19, 0, tzinfo=timezone.utc)

    assert is_business_hours(wednesday)
    assert not is_business_hours(sunday)
    assert not is_business_hours(early)
    assert not is_business_hours(evening)

    assert evaluate_policy(proposal, facts, wednesday).decision == "allow"
    for moment in (sunday, early, evening):
        decision = evaluate_policy(proposal, facts, moment)
        assert decision.decision == "escalate"
        assert "business hours" in decision.reasons[0]


def test_action_hash_binds_proposal_content():
    base = make_proposal(params={"method": "edr_network_isolate"})
    identical = base.model_copy()
    changed_params = base.model_copy(update={"params": {"method": "manual"}})
    changed_asset = base.model_copy(update={"target_asset": "FIN-WS-9999"})
    re_proposed = make_proposal(params={"method": "edr_network_isolate"})

    assert action_hash(base) == action_hash(identical)
    assert action_hash(base) != action_hash(changed_params)
    assert action_hash(base) != action_hash(changed_asset)
    # A re-proposed action is a different proposal id, so it binds separately.
    assert action_hash(base) != action_hash(re_proposed)
    assert action_hash(base).startswith("sha256:")


def test_signature_roundtrip_and_forgery_detection():
    behaviour = make_fact("asset/FIN-WS-0142/behaviour", "encryption observed")
    proposal = make_proposal(refs=[behaviour.id])
    decision = evaluate_policy(proposal, [behaviour], NOW)
    key = "unit-test-key"

    approval = sign_approval_record(proposal, decision, ApprovalCreate(
        approver="priya.nair", approver_role="ic"
    ), NOW, key)

    core = approval_core(approval)
    assert verify_signature(core, approval.signature, key)
    assert not verify_signature(core, approval.signature, "wrong-key")

    tampered = approval.model_copy(update={"approver": "mallory"})
    assert not verify_signature(
        approval_core(tampered), approval.signature, key
    )
    assert approval.key_id == "mock-hmac-sha256-v1"
    assert approval.nonce


def test_expired_approval_fails_verification():
    behaviour = make_fact("asset/FIN-WS-0142/behaviour", "encryption observed")
    proposal = make_proposal(refs=[behaviour.id])
    decision = evaluate_policy(proposal, [behaviour], NOW)
    key = "unit-test-key"

    approval = sign_approval_record(proposal, decision, ApprovalCreate(
        approver="priya.nair", approver_role="ic"
    ), NOW, key)

    within_ttl = NOW + timedelta(minutes=APPROVAL_TTL_MINUTES - 1)
    after_ttl = NOW + timedelta(minutes=APPROVAL_TTL_MINUTES + 1)

    assert check_approval(approval, proposal, decision, within_ttl, key) == []
    reasons = check_approval(approval, proposal, decision, after_ttl, key)
    assert any("expired" in reason for reason in reasons)


@pytest.mark.asyncio
async def test_evaluate_approve_dryrun_end_to_end(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(
            title="Containment flow", severity="sev1", declared_by="demo-ic"
        ),
    )
    behaviour = await store.append_fact(
        pool,
        incident.id,
        fact_create("asset/FIN-WS-0142/behaviour", "encryption observed"),
    )
    await store.append_fact(
        pool, incident.id, fact_create("asset/FIN-WS-0142/owner", "Priya Raman")
    )

    proposal = await store.create_proposal(
        pool,
        incident.id,
        ActionProposalCreate(
            action_id="isolate_endpoint",
            params={"method": "edr_network_isolate"},
            target_asset="FIN-WS-0142",
            tier=2,
            justification_refs=[behaviour.id],
            proposed_by="agent:containment-advisor",
        ),
    )

    decision = await store.evaluate_proposal(pool, incident.id, proposal.id)
    assert decision.decision == "allow"

    approval = await store.approve_proposal(
        pool,
        incident.id,
        proposal.id,
        ApprovalCreate(approver="priya.nair", approver_role="ic"),
    )
    assert approval.decision == "approved"
    assert approval.signature.startswith("hmac-sha256:")
    assert approval.key_id == "mock-hmac-sha256-v1"
    assert approval.expires_at > approval.decided_at

    before = (await store.containment_records(pool, incident.id))[0]
    assert before.approval_spent is False

    result = await store.execute_proposal(
        pool,
        incident.id,
        proposal.id,
        ExecutionRequest(requested_by="priya.nair"),
    )
    assert result.status == "simulated"
    assert result.dry_run is True
    assert result.approval_id == approval.id
    assert result.steps[0].name == "preserve-evidence"
    assert result.credential is not None
    assert result.credential.scope == "edr:endpoints:isolate:{asset}"
    assert result.credential.broker == "mock-jit-broker@1"

    event_types = [
        event.event_type for event in await store.list_timeline(pool, incident.id)
    ]
    for expected in ("policy.decided", "approval.signed", "execution.simulated"):
        assert expected in event_types

    records = await store.containment_records(pool, incident.id)
    assert len(records) == 1
    record = records[0]
    assert record.catalog is not None
    assert record.catalog.action_id == "isolate_endpoint"
    assert record.decision is not None and record.decision.decision == "allow"
    assert record.approval is not None
    assert record.execution is not None and record.execution.status == "simulated"
    assert record.approval_spent is True

    audit = await store.verify_audit(pool)
    assert audit.valid is True


@pytest.mark.asyncio
async def test_approval_guards_role_human_and_conflict(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(
            title="Approval guards", severity="sev2", declared_by="demo-ic"
        ),
    )
    behaviour = await store.append_fact(
        pool,
        incident.id,
        fact_create("asset/FIN-WS-0142/behaviour", "encryption observed"),
    )
    proposal = await store.create_proposal(
        pool,
        incident.id,
        ActionProposalCreate(
            action_id="isolate_endpoint",
            params={},
            target_asset="FIN-WS-0142",
            tier=2,
            justification_refs=[behaviour.id],
            proposed_by="agent:containment-advisor",
        ),
    )

    with pytest.raises(PolicyViolation):
        await store.approve_proposal(
            pool,
            incident.id,
            proposal.id,
            ApprovalCreate(approver="priya.nair", approver_role="ic"),
        )

    with pytest.raises(PolicyViolation):
        await store.approve_proposal(
            pool,
            incident.id,
            proposal.id,
            ApprovalCreate(approver="agent:advisor", approver_role="ic"),
        )

    decision = await store.evaluate_proposal(pool, incident.id, proposal.id)
    assert decision.decision == "allow"

    with pytest.raises(PolicyViolation):
        await store.approve_proposal(
            pool,
            incident.id,
            proposal.id,
            ApprovalCreate(approver="sam.chen", approver_role="security"),
        )

    approval = await store.approve_proposal(
        pool,
        incident.id,
        proposal.id,
        ApprovalCreate(approver="priya.nair", approver_role="ic"),
    )
    assert approval.approver == "priya.nair"

    with pytest.raises(ConflictError):
        await store.approve_proposal(
            pool,
            incident.id,
            proposal.id,
            ApprovalCreate(approver="priya.nair", approver_role="ic"),
        )


@pytest.mark.asyncio
async def test_replay_and_live_execution_refused(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(
            title="Execution guards", severity="sev1", declared_by="demo-ic"
        ),
    )
    behaviour = await store.append_fact(
        pool,
        incident.id,
        fact_create("asset/FIN-WS-0142/behaviour", "encryption observed"),
    )
    proposal = await store.create_proposal(
        pool,
        incident.id,
        ActionProposalCreate(
            action_id="isolate_endpoint",
            params={},
            target_asset="FIN-WS-0142",
            tier=2,
            justification_refs=[behaviour.id],
            proposed_by="agent:containment-advisor",
        ),
    )
    await store.evaluate_proposal(pool, incident.id, proposal.id)
    await store.approve_proposal(
        pool,
        incident.id,
        proposal.id,
        ApprovalCreate(approver="priya.nair", approver_role="ic"),
    )

    live = await store.execute_proposal(
        pool,
        incident.id,
        proposal.id,
        ExecutionRequest(requested_by="priya.nair", dry_run=False),
    )
    assert live.status == "refused"
    assert any("dry-run is mandatory" in reason for reason in live.reasons)

    after_refusal = (await store.containment_records(pool, incident.id))[0]
    assert after_refusal.approval_spent is False

    first = await store.execute_proposal(
        pool,
        incident.id,
        proposal.id,
        ExecutionRequest(requested_by="priya.nair"),
    )
    assert first.status == "simulated"

    replay = await store.execute_proposal(
        pool,
        incident.id,
        proposal.id,
        ExecutionRequest(requested_by="priya.nair"),
    )
    assert replay.status == "refused"
    assert any("already used" in reason for reason in replay.reasons)

    executions = await store.list_executions(pool, incident.id)
    assert [item.status for item in executions] == ["refused", "simulated", "refused"]

    after_simulated = (await store.containment_records(pool, incident.id))[0]
    assert after_simulated.approval_spent is True

    audit = await store.verify_audit(pool)
    assert audit.valid is True


@pytest.mark.asyncio
async def test_never_automate_cannot_be_approved_or_executed(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(
            title="Never automate", severity="sev1", declared_by="demo-ic"
        ),
    )
    behaviour = await store.append_fact(
        pool,
        incident.id,
        fact_create("asset/FIN-WS-0142/behaviour", "encryption observed"),
    )
    proposal = await store.create_proposal(
        pool,
        incident.id,
        ActionProposalCreate(
            action_id="wipe_host",
            params={},
            target_asset="FIN-WS-0142",
            tier=3,
            justification_refs=[behaviour.id],
            proposed_by="agent:containment-advisor",
        ),
    )

    decision = await store.evaluate_proposal(pool, incident.id, proposal.id)
    assert decision.decision == "escalate"
    assert decision.allowed_roles == []

    with pytest.raises(PolicyViolation):
        await store.approve_proposal(
            pool,
            incident.id,
            proposal.id,
            ApprovalCreate(approver="priya.nair", approver_role="ic"),
        )

    result = await store.execute_proposal(
        pool,
        incident.id,
        proposal.id,
        ExecutionRequest(requested_by="priya.nair"),
    )
    assert result.status == "refused"
    assert any("only 'allow'" in reason for reason in result.reasons)

    audit = await store.verify_audit(pool)
    assert audit.valid is True
