from datetime import datetime, timezone

import httpx
import pytest

from adjutant import store
from adjutant.clocks import CLOCK_RULES, compute_clock
from adjutant.errors import ConflictError
from adjutant.main import create_app
from adjutant.models import (
    ClockConfirmation,
    ClockStatus,
    Confidence,
    Evidence,
    FactCreate,
    IncidentCreate,
)


def test_calendar_clock_is_deterministic():
    trigger = datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc)

    first = compute_clock(CLOCK_RULES["cert-in-6h"], trigger)
    second = compute_clock(CLOCK_RULES["cert-in-6h"], trigger)

    assert first.due_at == second.due_at
    assert (first.due_at - trigger).total_seconds() == 6 * 3600
    assert first.calendar == "calendar"
    assert any("add 6 calendar hours" in step for step in first.steps)


def test_business_day_clock_skips_weekend():
    trigger = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)

    computation = compute_clock(CLOCK_RULES["sec-4-business-days"], trigger)

    assert computation.due_at.date().isoformat() == "2026-11-18"
    assert computation.due_at.hour == 15
    assert any("weekend" in step for step in computation.steps)


def test_business_day_clock_skips_holiday():
    trigger = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)

    computation = compute_clock(
        CLOCK_RULES["sec-4-business-days"],
        trigger,
        holidays=["2026-11-16"],
    )

    assert computation.due_at.date().isoformat() == "2026-11-19"
    assert any("holiday" in step for step in computation.steps)


def fact_create(attribute: str, value) -> FactCreate:
    return FactCreate(
        attribute=attribute,
        value=value,
        source="test:source",
        confidence=Confidence(
            source_reliability=0.9,
            corroboration=1,
            extraction_certainty=0.9,
        ),
        evidence=[
            Evidence(
                ref="ev-clock-001",
                kind="test",
                content_hash="sha256:ev-clock-001",
                excerpt="Synthetic regulatory evidence",
            )
        ],
    )


@pytest.mark.asyncio
async def test_clock_api_requires_legal_human_confirmation(settings, pool):
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            created = await client.post(
                "/incidents",
                json={
                    "title": "Clock API test",
                    "severity": "sev2",
                    "declared_by": "tester",
                },
            )
            incident_id = created.json()["id"]
            fact = await client.post(
                f"/incidents/{incident_id}/facts",
                json=fact_create(
                    "regulatory/cert-in/clock",
                    {"candidate": True, "deadline_hours": 6},
                ).model_dump(mode="json"),
            )
            fact_id = fact.json()["id"]

            clock_response = await client.post(
                f"/incidents/{incident_id}/clocks",
                json={"regime": "cert-in-6h", "trigger_fact_id": fact_id},
            )
            assert clock_response.status_code == 201
            clock = clock_response.json()
            clock_id = clock["id"]
            trigger = datetime.fromisoformat(
                clock["trigger_at"].replace("Z", "+00:00")
            )
            due = datetime.fromisoformat(
                clock["due_at"].replace("Z", "+00:00")
            )
            assert (due - trigger).total_seconds() == 6 * 3600
            assert clock["status"] == "candidate"
            assert len(clock["computation"]["steps"]) >= 5

            agent_confirm = await client.post(
                f"/incidents/{incident_id}/clocks/{clock_id}/confirm",
                json={
                    "confirmed_by": "agent:clock-advisor",
                    "role": "legal",
                    "attestation": True,
                },
            )
            assert agent_confirm.status_code == 403

            no_attestation = await client.post(
                f"/incidents/{incident_id}/clocks/{clock_id}/confirm",
                json={
                    "confirmed_by": "demo-legal",
                    "role": "legal",
                    "attestation": False,
                },
            )
            assert no_attestation.status_code == 403

            confirmed = await client.post(
                f"/incidents/{incident_id}/clocks/{clock_id}/confirm",
                json={
                    "confirmed_by": "demo-legal",
                    "role": "legal",
                    "attestation": True,
                    "note": "Synthetic legal confirmation",
                },
            )
            assert confirmed.status_code == 200
            assert confirmed.json()["status"] == "confirmed"
            assert confirmed.json()["confirmed_by"] == "demo-legal"

            duplicate = await client.post(
                f"/incidents/{incident_id}/clocks/{clock_id}/confirm",
                json={
                    "confirmed_by": "demo-legal",
                    "role": "legal",
                    "attestation": True,
                },
            )
            assert duplicate.status_code == 409

            clocks = await client.get(f"/incidents/{incident_id}/clocks")
            assert clocks.json()[0]["status"] == "confirmed"

            timeline = await client.get(f"/incidents/{incident_id}/timeline")
            events = timeline.json()
            candidate_event = next(
                event
                for event in events
                if event["event_type"] == "clock.candidate_recorded"
            )
            assert candidate_event["payload"]["computation"]["steps"]
            assert "clock.confirmed" in [
                event["event_type"] for event in events
            ]

            audit = await client.get("/audit/verify")
            assert audit.json()["valid"] is True


@pytest.mark.asyncio
async def test_superseded_trigger_cannot_be_confirmed(pool):
    incident = await store.create_incident(
        pool,
        IncidentCreate(
            title="Clock supersede test",
            severity="sev3",
            declared_by="tester",
        ),
    )
    trigger = await store.append_fact(
        pool,
        incident.id,
        fact_create("regulatory/cert-in/clock", {"candidate": True}),
    )
    clock = await store.create_clock_candidate(
        pool,
        incident.id,
        store.ClockCandidateCreate(
            regime="cert-in-6h", trigger_fact_id=trigger.id
        ),
    )
    assert clock.status is ClockStatus.CANDIDATE

    await store.append_fact(
        pool,
        incident.id,
        fact_create(
            "regulatory/cert-in/clock", {"candidate": False}
        ).model_copy(update={"supersedes": trigger.id}),
    )

    with pytest.raises(ConflictError):
        await store.confirm_clock(
            pool,
            incident.id,
            clock.id,
            ClockConfirmation(
                confirmed_by="demo-legal",
                role="legal",
                attestation=True,
            ),
        )
