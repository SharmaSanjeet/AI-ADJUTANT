from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from adjutant import store
from adjutant.autonomy import evaluate_autonomy
from adjutant.config import get_settings
from adjutant.errors import ConflictError, PolicyViolation
from adjutant.models import (
    ActionProposalCreate,
    ActionWindowStats,
    ApprovalCreate,
    AutonomyLevelRequest,
    BreakerResetRequest,
    ExecutionRequest,
    FactCreate,
    Confidence,
    IncidentCreate,
    KillSwitchRequest,
    OobApprovalCreate,
)

NOW = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)


def fact_create(attribute: str, value) -> FactCreate:
    return FactCreate(
        attribute=attribute,
        value=value,
        source="test:source",
        confidence=Confidence(source_reliability=0.8),
    )


async def make_allow_proposal(pool, incident_id, asset="FIN-WS-0142"):
    behaviour = await store.append_fact(
        pool,
        incident_id,
        fact_create("asset/FIN-WS-0142/behaviour", "encryption observed"),
    )
    proposal = await store.create_proposal(
        pool,
        incident_id,
        ActionProposalCreate(
            action_id="isolate_endpoint",
            params={"method": "edr_network_isolate"},
            target_asset=asset,
            tier=2,
            justification_refs=[behaviour.id],
            proposed_by="agent:containment-advisor",
        ),
    )
    await store.evaluate_proposal(pool, incident_id, proposal.id)
    return proposal


async def approve_and_execute(pool, incident_id, proposal):
    await store.approve_proposal(
        pool,
        incident_id,
        proposal.id,
        ApprovalCreate(approver="priya.nair", approver_role="ic"),
    )
    return await store.execute_proposal(
        pool,
        incident_id,
        proposal.id,
        ExecutionRequest(requested_by="priya.nair"),
    )


@pytest.mark.asyncio
async def test_kill_switch_blocks_approvals_and_executions(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(title="Kill switch", severity="sev1", declared_by="ic"),
    )
    proposal = await make_allow_proposal(pool, incident.id)

    engaged = await store.engage_kill_switch(
        pool,
        KillSwitchRequest(
            engaged=True, actor="priya.nair", reason="containment drill"
        ),
    )
    assert engaged.engaged is True
    assert engaged.engaged_by == "priya.nair"

    with pytest.raises(PolicyViolation, match="kill switch engaged"):
        await store.approve_proposal(
            pool,
            incident.id,
            proposal.id,
            ApprovalCreate(approver="priya.nair", approver_role="ic"),
        )
    refused = await store.execute_proposal(
        pool,
        incident.id,
        proposal.id,
        ExecutionRequest(requested_by="priya.nair"),
    )
    assert refused.status == "refused"
    assert any("kill switch" in r for r in refused.reasons)

    released = await store.engage_kill_switch(
        pool,
        KillSwitchRequest(engaged=False, actor="priya.nair", reason="drill over"),
    )
    assert released.engaged is False

    approval = await store.approve_proposal(
        pool,
        incident.id,
        proposal.id,
        ApprovalCreate(approver="priya.nair", approver_role="ic"),
    )
    assert approval.decision == "approved"
    result = await store.execute_proposal(
        pool,
        incident.id,
        proposal.id,
        ExecutionRequest(requested_by="priya.nair"),
    )
    assert result.status == "simulated"

    audit = await store.verify_audit(pool)
    assert audit.valid is True


@pytest.mark.asyncio
async def test_kill_switch_environment_override(pool, monkeypatch):
    incident = await store.create_incident(
        pool,
        IncidentCreate(title="Env kill switch", severity="sev1", declared_by="ic"),
    )
    proposal = await make_allow_proposal(pool, incident.id)
    monkeypatch.setattr(get_settings(), "kill_switch", True)

    status = await store.automation_status(pool)
    assert status.kill_switch.engaged is True
    assert status.kill_switch.source == "environment"

    refused = await store.execute_proposal(
        pool,
        incident.id,
        proposal.id,
        ExecutionRequest(requested_by="priya.nair"),
    )
    assert refused.status == "refused"
    assert any("environment" in r for r in refused.reasons)

    monkeypatch.setattr(get_settings(), "kill_switch", False)
    result = await approve_and_execute(pool, incident.id, proposal)
    assert result.status == "simulated"


@pytest.mark.asyncio
async def test_breaker_trips_after_consecutive_refusals_and_resets(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(title="Breaker", severity="sev1", declared_by="ic"),
    )
    proposal1 = await make_allow_proposal(pool, incident.id)
    await store.approve_proposal(
        pool,
        incident.id,
        proposal1.id,
        ApprovalCreate(approver="priya.nair", approver_role="ic"),
    )
    live = await store.execute_proposal(
        pool,
        incident.id,
        proposal1.id,
        ExecutionRequest(requested_by="priya.nair", dry_run=False),
    )
    assert live.status == "refused"
    ok = await store.execute_proposal(
        pool,
        incident.id,
        proposal1.id,
        ExecutionRequest(requested_by="priya.nair"),
    )
    assert ok.status == "simulated"

    proposal2 = await make_allow_proposal(pool, incident.id)
    await store.approve_proposal(
        pool,
        incident.id,
        proposal2.id,
        ApprovalCreate(approver="priya.nair", approver_role="ic"),
    )
    for _ in range(3):
        refused = await store.execute_proposal(
            pool,
            incident.id,
            proposal2.id,
            ExecutionRequest(requested_by="priya.nair", dry_run=False),
        )
        assert refused.status == "refused"

    status = await store.automation_status(pool)
    breaker = next(
        b for b in status.breakers if b.action_id == "isolate_endpoint"
    )
    assert breaker.tripped is True
    assert breaker.consecutive_refusals >= 3

    proposal3 = await make_allow_proposal(pool, incident.id)
    await store.approve_proposal(
        pool,
        incident.id,
        proposal3.id,
        ApprovalCreate(approver="priya.nair", approver_role="ic"),
    )
    blocked = await store.execute_proposal(
        pool,
        incident.id,
        proposal3.id,
        ExecutionRequest(requested_by="priya.nair"),
    )
    assert blocked.status == "refused"
    assert any("circuit breaker" in r for r in blocked.reasons)

    with pytest.raises(PolicyViolation, match="human actor"):
        await store.reset_breaker(
            pool,
            "isolate_endpoint",
            BreakerResetRequest(actor="bot:operator"),
        )
    await store.reset_breaker(
        pool,
        "isolate_endpoint",
        BreakerResetRequest(actor="priya.nair", note="drill complete"),
    )

    result = await store.execute_proposal(
        pool,
        incident.id,
        proposal3.id,
        ExecutionRequest(requested_by="priya.nair"),
    )
    assert result.status == "simulated"

    audit = await store.verify_audit(pool)
    assert audit.valid is True


@pytest.mark.asyncio
async def test_rate_limit_blocks_simulated_executions(pool, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_per_hour", 2)
    incident = await store.create_incident(
        pool,
        IncidentCreate(title="Rate limit", severity="sev1", declared_by="ic"),
    )
    first = await approve_and_execute(
        pool, incident.id, await make_allow_proposal(pool, incident.id)
    )
    second = await approve_and_execute(
        pool, incident.id, await make_allow_proposal(pool, incident.id)
    )
    assert first.status == "simulated"
    assert second.status == "simulated"

    third = await make_allow_proposal(pool, incident.id)
    await store.approve_proposal(
        pool,
        incident.id,
        third.id,
        ApprovalCreate(approver="priya.nair", approver_role="ic"),
    )
    blocked = await store.execute_proposal(
        pool,
        incident.id,
        third.id,
        ExecutionRequest(requested_by="priya.nair"),
    )
    assert blocked.status == "refused"
    assert any("rate limit exceeded" in r for r in blocked.reasons)

    status = await store.automation_status(pool)
    limit = next(
        r for r in status.rate_limits if r.action_id == "isolate_endpoint"
    )
    assert limit.used_in_window >= 2


@pytest.mark.asyncio
async def test_scorecards_reflect_window_stats(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(title="Scorecards", severity="sev1", declared_by="ic"),
    )
    proposal = await make_allow_proposal(pool, incident.id)
    await approve_and_execute(pool, incident.id, proposal)

    cards = await store.scorecards(pool)
    card = next(c for c in cards if c.action_id == "isolate_endpoint")
    assert card.stats.proposals == 1
    assert card.stats.allows == 1
    assert card.stats.simulated == 1
    assert card.stats.refusals == 0
    assert card.level == "shadow"
    assert card.recommendation.eligible_for_promotion is False
    assert any("minimum" in h for h in card.recommendation.hold_reasons)
    assert card.catalog is not None


def test_autonomy_promotion_requires_thresholds():
    now = NOW
    strong = ActionWindowStats(
        action_id="isolate_endpoint",
        window_start=now - timedelta(days=30),
        window_end=now,
        proposals=12,
        allows=11,
        simulated=6,
    )
    rec = evaluate_autonomy(strong, "shadow", now=now)
    assert rec.eligible_for_promotion is True
    assert rec.demotion_reasons == []

    weak = strong.model_copy(update={"proposals": 3, "simulated": 1})
    rec = evaluate_autonomy(weak, "shadow", now=now)
    assert rec.eligible_for_promotion is False
    assert any("proposals" in h for h in rec.hold_reasons)

    refused = strong.model_copy(update={"refusals": 1})
    rec = evaluate_autonomy(refused, "suggest", now=now)
    assert rec.eligible_for_promotion is False
    assert rec.demotion_target == "shadow"
    assert any("refused" in d for d in rec.demotion_reasons)

    tripped = strong.model_copy(update={"breaker_trips": 1})
    rec = evaluate_autonomy(tripped, "approve", now=now)
    assert rec.demotion_target == "shadow"
    assert any("breaker" in d for d in rec.demotion_reasons)

    denied = strong.model_copy(update={"denies": 2})
    rec = evaluate_autonomy(denied, "approve", now=now)
    assert rec.demotion_target == "shadow"


@pytest.mark.asyncio
async def test_autonomy_level_changes_are_gated(pool, monkeypatch):
    incident = await store.create_incident(
        pool,
        IncidentCreate(title="Levels", severity="sev2", declared_by="ic"),
    )
    await approve_and_execute(
        pool, incident.id, await make_allow_proposal(pool, incident.id)
    )

    with pytest.raises(PolicyViolation, match="promotion is disabled"):
        await store.set_autonomy_level(
            pool,
            "isolate_endpoint",
            AutonomyLevelRequest(
                level="suggest", actor="priya.nair", reason="scorecard green"
            ),
        )

    monkeypatch.setattr(get_settings(), "enable_autonomy_promotion", True)
    result = await store.set_autonomy_level(
        pool,
        "isolate_endpoint",
        AutonomyLevelRequest(
            level="suggest", actor="priya.nair", reason="scorecard green"
        ),
    )
    assert result["level"] == "suggest"
    assert result["set_by"] == "priya.nair"

    cards = await store.scorecards(pool)
    card = next(c for c in cards if c.action_id == "isolate_endpoint")
    assert card.level == "suggest"
    assert card.level_set_by == "priya.nair"

    monkeypatch.setattr(get_settings(), "enable_autonomy_promotion", False)
    audit = await store.verify_audit(pool)
    assert audit.valid is True


@pytest.mark.asyncio
async def test_oob_approvals_refused_in_default_profile(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(title="OOB default", severity="sev1", declared_by="ic"),
    )
    proposal = await make_allow_proposal(pool, incident.id)
    request = await store.create_approval_request(pool, incident.id, proposal.id)
    assert request.status == "pending"
    assert request.topology == "independent-control-plane"

    with pytest.raises(PolicyViolation, match="channel is in-band"):
        await store.approve_oob(
            pool,
            incident.id,
            proposal.id,
            OobApprovalCreate(
                bundle_id=request.id,
                approver="priya.nair",
                approver_role="ic",
                attestation_signature="hmac-sha256:deadbeef",
            ),
        )

    signed = await store.mock_sign_oob_bundle(pool, request.id)
    assert signed.signature.startswith("hmac-sha256:")


@pytest.mark.asyncio
async def test_oob_drill_in_out_of_band_profile(pool, monkeypatch):
    monkeypatch.setattr(get_settings(), "config_profile", "out-of-band")
    incident = await store.create_incident(
        pool,
        IncidentCreate(title="OOB drill", severity="sev1", declared_by="ic"),
    )
    proposal = await make_allow_proposal(pool, incident.id)

    with pytest.raises(PolicyViolation, match="channel is out-of-band"):
        await store.approve_proposal(
            pool,
            incident.id,
            proposal.id,
            ApprovalCreate(approver="priya.nair", approver_role="ic"),
        )

    request = await store.create_approval_request(pool, incident.id, proposal.id)
    signed = await store.mock_sign_oob_bundle(pool, request.id)

    with pytest.raises(PolicyViolation, match="signature does not verify"):
        await store.approve_oob(
            pool,
            incident.id,
            proposal.id,
            OobApprovalCreate(
                bundle_id=request.id,
                approver="priya.nair",
                approver_role="ic",
                attestation_signature="hmac-sha256:" + "0" * 64,
            ),
        )

    approval = await store.approve_oob(
        pool,
        incident.id,
        proposal.id,
        OobApprovalCreate(
            bundle_id=request.id,
            approver="priya.nair",
            approver_role="ic",
            attestation_signature=signed.signature,
        ),
    )
    assert approval.decision == "approved"
    assert approval.key_id == "mock-oob-hmac-sha256-v1"
    assert approval.nonce == request.nonce
    assert "out-of-band" in approval.note

    requests = await store.list_approval_requests(pool, incident.id)
    assert requests[0].status == "approved"
    assert requests[0].resolved_by == "priya.nair"

    with pytest.raises(PolicyViolation, match="only pending"):
        await store.approve_oob(
            pool,
            incident.id,
            proposal.id,
            OobApprovalCreate(
                bundle_id=request.id,
                approver="priya.nair",
                approver_role="ic",
                attestation_signature=signed.signature,
            ),
        )

    result = await store.execute_proposal(
        pool,
        incident.id,
        proposal.id,
        ExecutionRequest(requested_by="priya.nair"),
    )
    assert result.status == "simulated"

    audit = await store.verify_audit(pool)
    assert audit.valid is True


@pytest.mark.asyncio
async def test_approval_request_guards(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(title="Request guards", severity="sev1", declared_by="ic"),
    )
    behaviour = await store.append_fact(
        pool,
        incident.id,
        fact_create("asset/FIN-WS-0142/behaviour", "encryption observed"),
    )

    unevaluated = await store.create_proposal(
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
    with pytest.raises(PolicyViolation, match="'allow' policy decision"):
        await store.create_approval_request(pool, incident.id, unevaluated.id)

    wipe = await store.create_proposal(
        pool,
        incident.id,
        ActionProposalCreate(
            action_id="wipe_host",
            params={"method": "secure_wipe"},
            target_asset="FIN-WS-0142",
            tier=3,
            justification_refs=[behaviour.id],
            proposed_by="agent:containment-advisor",
        ),
    )
    await store.evaluate_proposal(pool, incident.id, wipe.id)
    with pytest.raises(PolicyViolation, match="never-automate"):
        await store.create_approval_request(pool, incident.id, wipe.id)

    allowed = await make_allow_proposal(pool, incident.id)
    await store.create_approval_request(pool, incident.id, allowed.id)
    with pytest.raises(ConflictError, match="pending approval request"):
        await store.create_approval_request(pool, incident.id, allowed.id)
