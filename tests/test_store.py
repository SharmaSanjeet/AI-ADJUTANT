import pytest

from adjutant import store
from adjutant.models import (
    Confidence,
    FactCreate,
    FactStatus,
    FactStatusChange,
    IncidentCreate,
)


def confidence(reliability: float = 0.6) -> Confidence:
    return Confidence(
        source_reliability=reliability,
        corroboration=0,
        extraction_certainty=0.9,
    )


@pytest.mark.asyncio
async def test_fact_is_projected(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(title="Test incident", severity="sev2", declared_by="tester"),
    )
    fact = await store.append_fact(
        pool,
        incident.id,
        FactCreate(
            attribute="asset/FIN-WS-0142/owner",
            value="unknown",
            source="cmdb:mock",
            confidence=confidence(0.35),
        ),
    )

    facts = await store.list_facts(pool, incident.id)

    assert len(facts) == 1
    assert facts[0].id == fact.id
    assert facts[0].value == "unknown"
    assert facts[0].status == FactStatus.ASSERTED
    assert facts[0].source == "cmdb:mock"


@pytest.mark.asyncio
async def test_supersede_hides_old_fact_but_keeps_history(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(title="Supersede test", severity="sev2", declared_by="tester"),
    )
    first = await store.append_fact(
        pool,
        incident.id,
        FactCreate(
            attribute="asset/FIN-WS-0142/owner",
            value="unknown",
            source="cmdb:mock",
            confidence=confidence(0.35),
        ),
    )
    second = await store.append_fact(
        pool,
        incident.id,
        FactCreate(
            attribute="asset/FIN-WS-0142/owner",
            value="priya.nair",
            source="human:ic",
            confidence=confidence(0.95),
            supersedes=first.id,
        ),
    )

    current = await store.list_facts(pool, incident.id)
    history = await store.list_facts(pool, incident.id, include_history=True)

    assert [fact.id for fact in current] == [second.id]
    assert len(history) == 2
    old = next(fact for fact in history if fact.id == first.id)
    assert old.status == FactStatus.SUPERSEDED


@pytest.mark.asyncio
async def test_status_change_is_projected(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(title="Dispute test", severity="sev3", declared_by="tester"),
    )
    fact = await store.append_fact(
        pool,
        incident.id,
        FactCreate(
            attribute="identity/svc-settlement/status",
            value="credentials possibly exposed",
            source="edr:mock",
            confidence=confidence(0.6),
        ),
    )

    await store.change_fact_status(
        pool,
        incident.id,
        fact.id,
        FactStatusChange(
            status=FactStatus.DISPUTED,
            reason="Owner says the token was rotated yesterday",
            changed_by="tester",
        ),
    )

    facts = await store.list_facts(pool, incident.id)

    assert facts[0].status == FactStatus.DISPUTED
    timeline = await store.list_timeline(pool, incident.id)
    assert [event.event_type for event in timeline] == [
        "incident.created",
        "fact.appended",
        "fact.status_changed",
    ]


@pytest.mark.asyncio
async def test_rebuild_facts_replays_event_log(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(title="Replay test", severity="sev2", declared_by="tester"),
    )
    first = await store.append_fact(
        pool,
        incident.id,
        FactCreate(
            attribute="asset/1/owner",
            value="unknown",
            source="cmdb:mock",
            confidence=confidence(),
        ),
    )
    await store.append_fact(
        pool,
        incident.id,
        FactCreate(
            attribute="asset/1/owner",
            value="owner.one",
            source="human:ic",
            confidence=confidence(0.95),
            supersedes=first.id,
        ),
    )
    await store.change_fact_status(
        pool,
        incident.id,
        first.id,
        FactStatusChange(
            status=FactStatus.RETRACTED,
            reason="Synthetic retraction test",
            changed_by="tester",
        ),
    )

    before = await store.list_facts(pool, incident.id, include_history=True)
    await store.rebuild_facts(pool)
    after = await store.list_facts(pool, incident.id, include_history=True)

    assert before == after


@pytest.mark.asyncio
async def test_supersedes_must_belong_to_same_incident(pool):
    one = await store.create_incident(
        pool,
        IncidentCreate(title="One", severity="sev2", declared_by="tester"),
    )
    two = await store.create_incident(
        pool,
        IncidentCreate(title="Two", severity="sev2", declared_by="tester"),
    )
    foreign = await store.append_fact(
        pool,
        one.id,
        FactCreate(
            attribute="asset/1/owner",
            value="unknown",
            source="cmdb:mock",
        ),
    )

    with pytest.raises(ValueError):
        await store.append_fact(
            pool,
            two.id,
            FactCreate(
                attribute="asset/1/owner",
                value="owner.one",
                source="human:ic",
                supersedes=foreign.id,
            ),
        )
