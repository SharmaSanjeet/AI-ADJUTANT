from datetime import datetime, timezone
from uuid import uuid4

import pytest
from psycopg import errors

from adjutant import store
from adjutant.audit import GENESIS_HASH, compute_event_hash
from adjutant.models import FactCreate, IncidentCreate


@pytest.mark.asyncio
async def test_audit_chain_verifies(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(title="Audit test", severity="sev2", declared_by="tester"),
    )
    await store.append_fact(
        pool,
        incident.id,
        FactCreate(
            attribute="asset/1/owner",
            value="unknown",
            source="cmdb:mock",
        ),
    )

    result = await store.verify_audit(pool)

    assert result.valid is True
    assert result.entries == 2
    assert result.head_hash != GENESIS_HASH
    assert result.first_broken_seq is None


@pytest.mark.asyncio
async def test_events_reject_updates(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(title="Append-only test", severity="sev2", declared_by="tester"),
    )

    with pytest.raises(errors.RaiseException):
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE events SET source = 'tampered' WHERE incident_id = %s",
                (incident.id,),
            )
            await conn.commit()


@pytest.mark.asyncio
async def test_events_reject_deletes(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(title="Delete test", severity="sev2", declared_by="tester"),
    )

    with pytest.raises(errors.RaiseException):
        async with pool.connection() as conn:
            await conn.execute(
                "DELETE FROM events WHERE incident_id = %s",
                (incident.id,),
            )
            await conn.commit()


def test_hash_changes_when_payload_changes():
    kwargs = dict(
        prev_hash=GENESIS_HASH,
        event_id=uuid4(),
        incident_id=uuid4(),
        event_type="fact.appended",
        source="test",
        recorded_at=datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc),
        valid_at=None,
        classification="internal",
    )

    first = compute_event_hash(payload={"value": "unknown"}, **kwargs)
    second = compute_event_hash(payload={"value": "owner.one"}, **kwargs)

    assert first != second
