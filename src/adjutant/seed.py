from datetime import timedelta
from uuid import uuid4

from psycopg_pool import AsyncConnectionPool

from .audit import sha256_hex
from .clocks import compute_clock, get_clock_rule
from .comms import build_claims, evaluate_brief
from .containment import evaluate_policy
from .dispatch import (
    assess_readiness,
    build_assignment,
    build_handoff,
    map_impacts,
    resolve_owner,
)
from .models import (
    ActionProposal,
    BriefAudience,
    BriefDraft,
    BriefRecord,
    ClockCandidate,
    ClockStatus,
    Confidence,
    DispatchRecord,
    DispatchStatus,
    Evidence,
    Fact,
    FactTrust,
    Incident,
    Signal,
)
from .store import SEED_LOCK_ID, append_event, utcnow


async def seed_demo(pool: AsyncConnectionPool) -> None:
    """Load one clearly-labelled synthetic ransomware incident. Idempotent."""
    async with pool.connection() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(%s)", (SEED_LOCK_ID,))
            cur = await conn.execute("SELECT count(*) AS n FROM incidents")
            row = await cur.fetchone()
            if row["n"]:
                return

            now = utcnow()
            incident_id = uuid4()
            incident = Incident(
                id=incident_id,
                title="SYNTHETIC — Ransomware activity on finance workstation FIN-WS-0142",
                severity="sev1",
                status="declared",
                declared_at=now,
                declared_by="demo-ic",
                summary=(
                    "Synthetic demo incident. No real customers, credentials, or systems. "
                    "Used to exercise Adjutant's state model end to end."
                ),
            )
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="incident.created",
                payload=incident.model_dump(mode="json"),
                source="human:demo-ic",
                valid_at=now,
                recorded_at=now,
            )

            signal_content = (
                '{"host":"FIN-WS-0142","user":"svc-settlement",'
                '"process":"encrypt.exe","action":"mass_file_rename",'
                '"severity":"high","message":"Synthetic EDR alert: mass file '
                'rename followed by encryption"}'
            )
            signal = Signal(
                id=uuid4(),
                incident_id=incident_id,
                kind="edr",
                source="edr:mock",
                content_hash="sha256:" + sha256_hex(signal_content),
                content_excerpt=signal_content[:280],
                observed_at=now,
                recorded_at=now,
            )
            signal_payload = signal.model_dump(mode="json")
            signal_payload["content"] = signal_content
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="signal.received",
                payload=signal_payload,
                source="ingest:edr:mock",
                valid_at=now,
                recorded_at=now,
            )

            fact_clock = {"n": 0}

            def make_fact(
                attribute: str,
                value,
                source: str,
                reliability: float,
                evidence_ref: str,
                evidence_kind: str,
                evidence_excerpt: str,
                status: str = "asserted",
                classification: str = "internal",
                corroboration: int = 0,
                trust: FactTrust = FactTrust.TRUSTED,
            ) -> Fact:
                fact_clock["n"] += 1
                stamp = now + timedelta(milliseconds=fact_clock["n"])
                return Fact(
                    id=uuid4(),
                    incident_id=incident_id,
                    attribute=attribute,
                    value=value,
                    source=source,
                    valid_at=stamp,
                    recorded_at=stamp,
                    confidence=Confidence(
                        source_reliability=reliability,
                        corroboration=corroboration,
                        extraction_certainty=0.9,
                    ),
                    status=status,
                    classification=classification,
                    trust=trust,
                    evidence=[
                        Evidence(
                            ref=evidence_ref,
                            kind=evidence_kind,
                            content_hash=f"sha256:synthetic-{evidence_ref}",
                            excerpt=evidence_excerpt,
                        )
                    ],
                )

            facts = [
                make_fact(
                    "signal/edr/message",
                    "Synthetic EDR alert: mass file rename followed by encryption",
                    "extractor:deterministic-json",
                    0.5,
                    f"signal:{signal.content_hash}",
                    "signal",
                    signal_content[:280],
                    trust=FactTrust.UNTRUSTED,
                ),
                make_fact(
                    "alert/edr/behavior",
                    "Ransomware-like encryption behavior detected",
                    "edr:mock",
                    0.9,
                    "ev-edr-001",
                    "edr",
                    "Synthetic EDR alert: mass file rename followed by encryption",
                    corroboration=1,
                ),
                make_fact(
                    "asset/FIN-WS-0142/owner",
                    "unknown",
                    "cmdb:mock",
                    0.35,
                    "ev-cmdb-001",
                    "cmdb",
                    "Synthetic CMDB record has no owner or support group",
                ),
                make_fact(
                    "asset/FIN-WS-0142/criticality",
                    "high: month-end settlement preparation",
                    "cmdb:mock",
                    0.8,
                    "ev-cmdb-002",
                    "cmdb",
                    "Synthetic CMDB business criticality: high",
                ),
                make_fact(
                    "identity/svc-settlement/status",
                    "credentials possibly exposed",
                    "edr:mock",
                    0.6,
                    "ev-edr-002",
                    "edr",
                    "Synthetic EDR observation: service account token in process memory",
                    status="disputed",
                ),
                make_fact(
                    "regulatory/cert-in/clock",
                    {
                        "candidate": True,
                        "deadline_hours": 6,
                        "trigger": "confirmation of incident",
                    },
                    "policy:mock",
                    0.5,
                    "ev-policy-001",
                    "policy",
                    "Synthetic clock candidate. Requires legal confirmation before starting.",
                    classification="confidential",
                ),
                make_fact(
                    "incident/containment/assessment",
                    "Isolating FIN-WS-0142 would stop spread but may interrupt month-end settlement",
                    "agent:containment-advisor",
                    0.7,
                    "ev-analysis-001",
                    "analysis",
                    "Synthetic containment analysis",
                ),
            ]

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

            proposal = ActionProposal(
                id=uuid4(),
                incident_id=incident_id,
                action_id="isolate_endpoint",
                params={"method": "edr_network_isolate"},
                target_asset="FIN-WS-0142",
                tier=2,
                justification_refs=[facts[1].id, facts[6].id],
                proposed_by="agent:containment-advisor",
                created_at=now,
            )
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="proposal.created",
                payload=proposal.model_dump(mode="json"),
                source=proposal.proposed_by,
                valid_at=now,
                recorded_at=now,
            )

            wipe_proposal = ActionProposal(
                id=uuid4(),
                incident_id=incident_id,
                action_id="wipe_host",
                params={"method": "secure_wipe", "reimage": True},
                target_asset="FIN-WS-0142",
                tier=3,
                justification_refs=[facts[1].id],
                proposed_by="agent:containment-advisor",
                created_at=now,
            )
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="proposal.created",
                payload=wipe_proposal.model_dump(mode="json"),
                source=wipe_proposal.proposed_by,
                valid_at=now,
                recorded_at=now,
            )

            decision = make_fact(
                "decision/containment/001",
                {
                    "decision": "pending_ic_approval",
                    "proposal_id": str(proposal.id),
                    "note": "Advisory only. No action has been executed.",
                },
                "agent:containment-advisor",
                0.7,
                "ev-analysis-002",
                "analysis",
                "Synthetic decision record awaiting human approval",
            )
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="fact.appended",
                payload=decision.model_dump(mode="json"),
                source=decision.source,
                valid_at=decision.valid_at,
                recorded_at=decision.recorded_at,
                classification=decision.classification.value,
            )

            all_facts = [*facts, decision]
            brief_created = now + timedelta(milliseconds=30)
            claims = build_claims(all_facts, BriefAudience.IC)
            brief = BriefDraft(
                id=uuid4(),
                incident_id=incident_id,
                audience=BriefAudience.IC,
                title=f"Incident Commander brief — {incident.title}"[:200],
                claims=claims,
                delta_since=None,
                fact_ids=sorted(
                    {fact_id for claim in claims for fact_id in claim.fact_ids},
                    key=str,
                ),
                generated_by="agent:scribe",
                created_at=brief_created,
            )
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="brief.drafted",
                payload=brief.model_dump(mode="json"),
                source="agent:scribe",
                valid_at=brief_created,
                recorded_at=brief_created,
            )
            check = evaluate_brief(
                brief, {fact.id: fact for fact in all_facts}
            )
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="brief.checked",
                payload=check.model_dump(mode="json"),
                source="agent:fact-checker",
                valid_at=check.checked_at,
                recorded_at=check.checked_at,
            )

            regulatory = next(
                fact
                for fact in facts
                if fact.attribute == "regulatory/cert-in/clock"
            )
            rule = get_clock_rule("cert-in-6h")
            clock_created = now + timedelta(milliseconds=40)
            computation = compute_clock(
                rule, regulatory.valid_at, computed_at=clock_created
            )
            clock = ClockCandidate(
                id=uuid4(),
                incident_id=incident_id,
                regime=rule.regime,
                label=rule.label,
                trigger_fact_id=regulatory.id,
                trigger_at=computation.trigger_at,
                due_at=computation.due_at,
                status=ClockStatus.CANDIDATE,
                requires_legal_confirmation=True,
                computation=computation,
                created_at=clock_created,
            )
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="clock.candidate_recorded",
                payload=clock.model_dump(mode="json"),
                source="agent:clock-advisor",
                valid_at=computation.trigger_at,
                recorded_at=clock_created,
            )

            phase3_facts = [
                make_fact(
                    "asset/FIN-WS-0142/service",
                    "settlement-batch",
                    "cmdb:mock",
                    0.85,
                    "ev-cmdb-003",
                    "cmdb",
                    "Synthetic CMDB service mapping: settlement-batch",
                ),
                make_fact(
                    "service/settlement-batch/owner",
                    "Priya Raman",
                    "service_catalog:mock",
                    0.85,
                    "ev-svc-001",
                    "service_catalog",
                    "Synthetic service catalog lists Priya Raman as owner",
                ),
                make_fact(
                    "service/settlement-batch/oncall",
                    "settlement-oncall",
                    "oncall_roster:mock",
                    0.8,
                    "ev-svc-002",
                    "oncall_roster",
                    "Synthetic on-call roster for settlement-batch",
                ),
                make_fact(
                    "service/settlement-batch/rto_minutes",
                    60,
                    "service_catalog:mock",
                    0.85,
                    "ev-svc-003",
                    "service_catalog",
                    "Synthetic service catalog RTO: 60 minutes",
                ),
                make_fact(
                    "service/settlement-batch/rpo_minutes",
                    15,
                    "service_catalog:mock",
                    0.85,
                    "ev-svc-004",
                    "service_catalog",
                    "Synthetic service catalog RPO: 15 minutes",
                ),
                make_fact(
                    "asset/FIN-SRV-0007/criticality",
                    "medium: backup staging",
                    "cmdb:mock",
                    0.7,
                    "ev-cmdb-004",
                    "cmdb",
                    "Synthetic CMDB business criticality: medium",
                ),
                make_fact(
                    "asset/FIN-SRV-0007/service",
                    "backup-vault",
                    "cmdb:mock",
                    0.7,
                    "ev-cmdb-005",
                    "cmdb",
                    "Synthetic CMDB service mapping: backup-vault (no owner recorded)",
                ),
                make_fact(
                    "service/backup-vault/rto_minutes",
                    240,
                    "service_catalog:mock",
                    0.8,
                    "ev-svc-005",
                    "service_catalog",
                    "Synthetic service catalog RTO: 240 minutes",
                ),
                make_fact(
                    "service/backup-vault/rpo_minutes",
                    60,
                    "service_catalog:mock",
                    0.8,
                    "ev-svc-006",
                    "service_catalog",
                    "Synthetic service catalog RPO: 60 minutes",
                ),
                make_fact(
                    "backup/FIN-SRV-0007/last_verify",
                    "verified",
                    "backup:mock",
                    0.8,
                    "ev-backup-001",
                    "backup",
                    "Synthetic backup verification succeeded",
                ),
                make_fact(
                    "integration/edr/status",
                    "operational",
                    "status:mock",
                    0.9,
                    "ev-int-001",
                    "integration",
                    "Synthetic EDR integration health: operational",
                ),
                make_fact(
                    "integration/cmdb/status",
                    "degraded",
                    "status:mock",
                    0.9,
                    "ev-int-002",
                    "integration",
                    "Synthetic CMDB integration health: degraded",
                ),
                make_fact(
                    "integration/itsm/status",
                    "operational",
                    "status:mock",
                    0.9,
                    "ev-int-003",
                    "integration",
                    "Synthetic ITSM integration health: operational",
                ),
                make_fact(
                    "integration/backup/status",
                    "degraded",
                    "status:mock",
                    0.9,
                    "ev-int-004",
                    "integration",
                    "Synthetic backup integration health: degraded",
                ),
                make_fact(
                    "integration/comms/status",
                    "operational",
                    "status:mock",
                    0.9,
                    "ev-int-005",
                    "integration",
                    "Synthetic comms integration health: operational",
                ),
                make_fact(
                    "network/segmentation/status",
                    "partial enforcement during containment",
                    "network:mock",
                    0.6,
                    "ev-net-001",
                    "network",
                    "Synthetic segmentation status is unspecified during containment",
                ),
            ]

            for fact in phase3_facts:
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

            all_facts = [*all_facts, *phase3_facts]
            dispatch_time = now + timedelta(milliseconds=100)

            primary_resolution = resolve_owner(
                "FIN-WS-0142", all_facts, incident, dispatch_time
            )
            primary_assignment = build_assignment(
                primary_resolution, incident, dispatch_time
            )
            assert primary_assignment is not None
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="dispatch.resolved",
                payload={
                    "resolution": primary_resolution.model_dump(mode="json"),
                    "assignment": primary_assignment.model_dump(mode="json"),
                },
                source="agent:dispatch",
                valid_at=dispatch_time,
                recorded_at=dispatch_time,
            )

            ack_time = dispatch_time + timedelta(minutes=3)
            acked = primary_assignment.model_copy(
                update={
                    "status": DispatchStatus.ACKED,
                    "ack_at": ack_time,
                    "ack_by": "Priya Raman",
                    "sla_met": ack_time <= primary_assignment.ack_due_at,
                    "note": "Owner acknowledged the synthetic dispatch.",
                }
            )
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="dispatch.acknowledged",
                payload={
                    "assignment_id": str(primary_assignment.id),
                    "incident_id": str(incident_id),
                    "acked_by": acked.ack_by,
                    "ack_at": ack_time.isoformat(),
                    "sla_met": acked.sla_met,
                    "note": acked.note,
                },
                source="human:Priya Raman",
                valid_at=ack_time,
                recorded_at=ack_time,
            )

            second_time = dispatch_time + timedelta(milliseconds=1)
            orphan_resolution = resolve_owner(
                "FIN-SRV-0007", all_facts, incident, second_time
            )
            orphan_assignment = build_assignment(
                orphan_resolution, incident, second_time
            )
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="dispatch.resolved",
                payload={
                    "resolution": orphan_resolution.model_dump(mode="json"),
                    "assignment": (
                        orphan_assignment.model_dump(mode="json")
                        if orphan_assignment
                        else None
                    ),
                },
                source="agent:dispatch",
                valid_at=second_time,
                recorded_at=second_time,
            )

            impact_time = now + timedelta(milliseconds=110)
            mappings = map_impacts(incident, all_facts, impact_time)
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="impact.mapped",
                payload={
                    "incident_id": str(incident_id),
                    "mappings": [m.model_dump(mode="json") for m in mappings],
                    "mapped_at": impact_time.isoformat(),
                },
                source="agent:bia",
                valid_at=impact_time,
                recorded_at=impact_time,
            )

            readiness_time = now + timedelta(milliseconds=120)
            readiness = assess_readiness(incident, all_facts, readiness_time)
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="readiness.assessed",
                payload=readiness.model_dump(mode="json"),
                source="agent:readiness",
                valid_at=readiness_time,
                recorded_at=readiness_time,
            )

            policy_time = now + timedelta(milliseconds=125)
            for prop in (proposal, wipe_proposal):
                policy_decision = evaluate_policy(prop, all_facts, policy_time)
                await append_event(
                    conn,
                    incident_id=incident_id,
                    event_type="policy.decided",
                    payload=policy_decision.model_dump(mode="json"),
                    source=policy_decision.evaluator,
                    valid_at=policy_time,
                    recorded_at=policy_time,
                )

            dispatches = [
                DispatchRecord(
                    resolution=primary_resolution, assignment=acked
                ),
                DispatchRecord(
                    resolution=orphan_resolution,
                    assignment=orphan_assignment,
                ),
            ]
            handoff_time = now + timedelta(milliseconds=130)
            handoff = build_handoff(
                incident,
                all_facts,
                [BriefRecord(brief=brief, check=check)],
                [proposal, wipe_proposal],
                [clock],
                dispatches,
                mappings,
                readiness,
                handoff_time,
            )
            await append_event(
                conn,
                incident_id=incident_id,
                event_type="handoff.drafted",
                payload=handoff.model_dump(mode="json"),
                source="agent:handoff",
                valid_at=handoff_time,
                recorded_at=handoff_time,
            )
