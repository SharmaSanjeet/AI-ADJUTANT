import httpx
import pytest

from adjutant.main import create_app


@pytest.mark.asyncio
async def test_api_flow(settings, pool):
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            health = await client.get("/health")
            assert health.status_code == 200
            assert health.json()["status"] == "ok"

            created = await client.post(
                "/incidents",
                json={
                    "title": "API test incident",
                    "severity": "sev2",
                    "declared_by": "tester",
                },
            )
            assert created.status_code == 201
            incident_id = created.json()["id"]

            fact = await client.post(
                f"/incidents/{incident_id}/facts",
                json={
                    "attribute": "asset/FIN-WS-0142/owner",
                    "value": "unknown",
                    "source": "cmdb:mock",
                    "confidence": {
                        "source_reliability": 0.35,
                        "corroboration": 0,
                        "extraction_certainty": 0.9,
                    },
                },
            )
            assert fact.status_code == 201

            timeline = await client.get(f"/incidents/{incident_id}/timeline")
            assert timeline.status_code == 200
            assert len(timeline.json()) == 2

            facts = await client.get(f"/incidents/{incident_id}/facts")
            assert facts.status_code == 200
            assert facts.json()[0]["value"] == "unknown"

            audit = await client.get("/audit/verify")
            assert audit.status_code == 200
            assert audit.json()["valid"] is True
