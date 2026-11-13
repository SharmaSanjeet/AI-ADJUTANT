import httpx
import pytest

from adjutant.main import create_app


@pytest.mark.asyncio
async def test_signal_ingest_api(settings, pool):
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            created = await client.post(
                "/incidents",
                json={
                    "title": "Signal API test",
                    "severity": "sev2",
                    "declared_by": "tester",
                },
            )
            incident_id = created.json()["id"]

            signal = await client.post(
                f"/incidents/{incident_id}/signals",
                json={
                    "kind": "edr",
                    "source": "edr:mock",
                    "content": (
                        '{"host":"FIN-WS-0142","severity":"high",'
                        '"message":"synthetic alert"}'
                    ),
                },
            )
            assert signal.status_code == 201
            body = signal.json()
            assert body["duplicate"] is False
            assert body["signal"]["trust"] == "untrusted"
            assert len(body["extracted_facts"]) >= 1

            duplicate = await client.post(
                f"/incidents/{incident_id}/signals",
                json={
                    "kind": "edr",
                    "source": "edr:mock",
                    "content": (
                        '{"host":"FIN-WS-0142","severity":"high",'
                        '"message":"synthetic alert"}'
                    ),
                },
            )
            assert duplicate.json()["duplicate"] is True

            signals = await client.get(f"/incidents/{incident_id}/signals")
            assert len(signals.json()) == 1

            await client.post(
                f"/incidents/{incident_id}/facts",
                json={
                    "attribute": "decision/containment/001",
                    "value": {"decision": "pending"},
                    "source": "agent:test",
                },
            )
            decisions = await client.get(f"/incidents/{incident_id}/decisions")
            assert decisions.status_code == 200
            assert len(decisions.json()) == 1

            timeline = await client.get(f"/incidents/{incident_id}/timeline")
            event_types = [event["event_type"] for event in timeline.json()]
            assert "signal.received" in event_types

            audit = await client.get("/audit/verify")
            assert audit.json()["valid"] is True
