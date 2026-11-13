"""Phase 5 tabletop suite: synthetic scenarios exercising the full gate chain.

Each scenario seeds typed facts through the normal store API, raises
proposals, and asserts the deterministic policy outcomes a real incident
commander would need to trust. No external systems are contacted; the audit
chain must verify after every scenario.
"""

import pytest

from adjutant import store
from adjutant.errors import PolicyViolation
from adjutant.models import (
    ActionProposalCreate,
    ApprovalCreate,
    Classification,
    Confidence,
    ExecutionRequest,
    FactCreate,
    FactStatus,
    FactTrust,
    IncidentCreate,
)


def fact_create(attribute: str, value) -> FactCreate:
    return FactCreate(
        attribute=attribute,
        value=value,
        source="test:source",
        confidence=Confidence(source_reliability=0.8),
    )


async def run_proposal(pool, incident_id, proposal_create):
    proposal = await store.create_proposal(pool, incident_id, proposal_create)
    return proposal, await store.evaluate_proposal(
        pool, incident_id, proposal.id
    )


@pytest.mark.asyncio
async def test_tabletop_ransomware(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(
            title="Tabletop: ransomware on finance workstation",
            severity="sev1",
            declared_by="demo-ic",
        ),
    )
    behaviour = await store.append_fact(
        pool,
        incident.id,
        fact_create("asset/FIN-WS-0142/behaviour", "mass file encryption"),
    )
    await store.append_fact(
        pool,
        incident.id,
        fact_create("asset/FIN-WS-0142/criticality", "high"),
    )

    isolate, decision = await run_proposal(
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
    assert decision.decision == "allow"

    wipe, wipe_decision = await run_proposal(
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
    assert wipe_decision.decision == "escalate"
    assert any("never-automate" in r for r in wipe_decision.reasons)

    await store.approve_proposal(
        pool,
        incident.id,
        isolate.id,
        ApprovalCreate(approver="priya.nair", approver_role="ic"),
    )
    result = await store.execute_proposal(
        pool,
        incident.id,
        isolate.id,
        ExecutionRequest(requested_by="priya.nair"),
    )
    assert result.status == "simulated"
    assert result.steps[0].name == "preserve-evidence"

    audit = await store.verify_audit(pool)
    assert audit.valid is True


@pytest.mark.asyncio
async def test_tabletop_insider_exfiltration(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(
            title="Tabletop: insider exfiltration via service account",
            severity="sev2",
            declared_by="demo-ic",
        ),
    )
    trusted = await store.append_fact(
        pool,
        incident.id,
        fact_create(
            "identity/sso-vault/exposure",
            "service account pulled 2GB from customer share",
        ),
    )
    disputed = await store.append_fact(
        pool,
        incident.id,
        FactCreate(
            attribute="identity/sso-vault/owner",
            value="contractor.mallory",
            source="test:source",
            confidence=Confidence(source_reliability=0.8),
            status=FactStatus.DISPUTED,
        ),
    )

    weak, weak_decision = await run_proposal(
        pool,
        incident.id,
        ActionProposalCreate(
            action_id="revoke_active_sessions",
            params={},
            target_asset="sso-vault",
            tier=1,
            justification_refs=[disputed.id],
            proposed_by="agent:containment-advisor",
        ),
    )
    assert weak_decision.decision == "escalate"
    assert any("disputed" in r for r in weak_decision.reasons)

    strong, strong_decision = await run_proposal(
        pool,
        incident.id,
        ActionProposalCreate(
            action_id="revoke_active_sessions",
            params={},
            target_asset="sso-vault",
            tier=1,
            justification_refs=[trusted.id],
            proposed_by="agent:containment-advisor",
        ),
    )
    assert strong_decision.decision == "allow"
    assert strong_decision.allowed_roles == ["security", "ic"]

    approval = await store.approve_proposal(
        pool,
        incident.id,
        strong.id,
        ApprovalCreate(approver="arjun.mehta", approver_role="security"),
    )
    assert approval.approver_role == "security"
    result = await store.execute_proposal(
        pool,
        incident.id,
        strong.id,
        ExecutionRequest(requested_by="arjun.mehta"),
    )
    assert result.status == "simulated"

    audit = await store.verify_audit(pool)
    assert audit.valid is True


@pytest.mark.asyncio
async def test_tabletop_supply_chain_ioc(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(
            title="Tabletop: compromised build agent beaconing",
            severity="sev1",
            declared_by="demo-ic",
        ),
    )
    ioc = await store.append_fact(
        pool,
        incident.id,
        fact_create(
            "network/FIN-SRV-0301/destination",
            "cdn-update.example attacker-controlled domain",
        ),
    )

    block, decision = await run_proposal(
        pool,
        incident.id,
        ActionProposalCreate(
            action_id="block_domain",
            params={"domain": "cdn-update.example"},
            target_asset="FIN-SRV-0301",
            tier=2,
            justification_refs=[ioc.id],
            proposed_by="agent:containment-advisor",
        ),
    )
    assert decision.decision == "allow"

    result = await store.execute_proposal(
        pool,
        incident.id,
        block.id,
        ExecutionRequest(requested_by="priya.nair", dry_run=False),
    )
    assert result.status == "refused"
    assert any("dry-run is mandatory" in r for r in result.reasons)

    audit = await store.verify_audit(pool)
    assert audit.valid is True


@pytest.mark.asyncio
async def test_tabletop_dr_plane_compromise(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(
            title="Tabletop: DR plane compromise, backup jobs targeted",
            severity="sev1",
            declared_by="demo-ic",
        ),
    )
    behaviour = await store.append_fact(
        pool,
        incident.id,
        fact_create(
            "backup/FIN-SRV-0007/behaviour", "backup jobs disabled remotely"
        ),
    )

    wipe_jobs, decision = await run_proposal(
        pool,
        incident.id,
        ActionProposalCreate(
            action_id="disable_backup_jobs",
            params={},
            target_asset="FIN-SRV-0007",
            tier=3,
            justification_refs=[behaviour.id],
            proposed_by="agent:containment-advisor",
        ),
    )
    assert decision.decision == "escalate"
    assert any("never-automate" in r for r in decision.reasons)
    with pytest.raises(PolicyViolation, match="only 'allow'"):
        await store.approve_proposal(
            pool,
            incident.id,
            wipe_jobs.id,
            ApprovalCreate(approver="priya.nair", approver_role="ic"),
        )

    unknown_asset, unknown_decision = await run_proposal(
        pool,
        incident.id,
        ActionProposalCreate(
            action_id="isolate_endpoint",
            params={},
            target_asset="FIN-WS-9999",
            tier=2,
            justification_refs=[behaviour.id],
            proposed_by="agent:containment-advisor",
        ),
    )
    assert unknown_decision.decision == "escalate"
    assert any("no recorded facts" in r for r in unknown_decision.reasons)

    audit = await store.verify_audit(pool)
    assert audit.valid is True


@pytest.mark.asyncio
async def test_tabletop_idp_compromise(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(
            title="Tabletop: IdP compromise, disputed identity evidence",
            severity="sev1",
            declared_by="demo-ic",
        ),
    )
    signal_message = await store.append_fact(
        pool,
        incident.id,
        FactCreate(
            attribute="identity/idp-core/behaviour",
            value="impossible travel logins reported by email",
            source="email:report",
            confidence=Confidence(source_reliability=0.4),
            trust=FactTrust.UNTRUSTED,
            classification=Classification.INTERNAL,
        ),
    )

    weak, weak_decision = await run_proposal(
        pool,
        incident.id,
        ActionProposalCreate(
            action_id="revoke_active_sessions",
            params={},
            target_asset="idp-core",
            tier=1,
            justification_refs=[signal_message.id],
            proposed_by="agent:containment-advisor",
        ),
    )
    assert weak_decision.decision == "escalate"
    assert any("untrusted" in r for r in weak_decision.reasons)

    verified = await store.append_fact(
        pool,
        incident.id,
        FactCreate(
            attribute="identity/idp-core/behaviour",
            value="impossible travel logins confirmed in IdP audit log",
            source="idp:mock",
            confidence=Confidence(source_reliability=0.9),
            supersedes=signal_message.id,
        ),
    )
    strong, strong_decision = await run_proposal(
        pool,
        incident.id,
        ActionProposalCreate(
            action_id="revoke_active_sessions",
            params={},
            target_asset="idp-core",
            tier=1,
            justification_refs=[verified.id],
            proposed_by="agent:containment-advisor",
        ),
    )
    assert strong_decision.decision == "allow"

    await store.approve_proposal(
        pool,
        incident.id,
        strong.id,
        ApprovalCreate(approver="priya.nair", approver_role="ic"),
    )
    result = await store.execute_proposal(
        pool,
        incident.id,
        strong.id,
        ExecutionRequest(requested_by="priya.nair"),
    )
    assert result.status == "simulated"

    audit = await store.verify_audit(pool)
    assert audit.valid is True


def test_tabletop_business_hours_gate_is_deterministic():
    from datetime import datetime, timezone

    from adjutant.containment import is_business_hours

    assert is_business_hours(datetime(2026, 11, 11, 10, 0, tzinfo=timezone.utc))
    assert not is_business_hours(
        datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    )
    assert not is_business_hours(
        datetime(2026, 11, 11, 19, 0, tzinfo=timezone.utc)
    )
