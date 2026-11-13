import httpx
import pytest

from adjutant.main import create_app


def fact_payload(attribute: str, value, ref: str) -> dict:
    return {
        "attribute": attribute,
        "value": value,
        "source": "test:source",
        "evidence": [
            {
                "ref": ref,
                "kind": "test",
                "content_hash": f"sha256:{ref}",
                "excerpt": "Synthetic test evidence",
            }
        ],
    }


@pytest.mark.asyncio
async def test_brief_requires_approval_and_only_mock_sends(settings, pool):
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            created = await client.post(
                "/incidents",
                json={
                    "title": "Brief API test",
                    "severity": "sev2",
                    "declared_by": "tester",
                },
            )
            incident_id = created.json()["id"]

            await client.post(
                f"/incidents/{incident_id}/facts",
                json=fact_payload(
                    "alert/edr/behavior",
                    "Synthetic encryption behavior detected",
                    "ev-brief-001",
                ),
            )
            await client.post(
                f"/incidents/{incident_id}/facts",
                json=fact_payload(
                    "asset/FIN-WS-0142/criticality",
                    "high: month-end settlement",
                    "ev-brief-002",
                ),
            )

            drafted = await client.post(
                f"/incidents/{incident_id}/briefs",
                json={"audience": "ic"},
            )
            assert drafted.status_code == 201
            record = drafted.json()
            brief_id = record["brief"]["id"]
            assert record["brief"]["check_status"] == "passed"
            assert record["check"]["issues"] == []
            assert len(record["brief"]["claims"]) == 2

            early_send = await client.post(
                f"/incidents/{incident_id}/briefs/{brief_id}/send",
                json={"requested_by": "demo-ic"},
            )
            assert early_send.status_code == 409

            agent_approval = await client.post(
                f"/incidents/{incident_id}/briefs/{brief_id}/approve",
                json={
                    "approver": "agent:scribe",
                    "approver_role": "ic",
                },
            )
            assert agent_approval.status_code == 403

            approved = await client.post(
                f"/incidents/{incident_id}/briefs/{brief_id}/approve",
                json={
                    "approver": "demo-ic",
                    "approver_role": "ic",
                    "note": "Synthetic approval",
                },
            )
            assert approved.status_code == 200
            assert approved.json()["brief"]["status"] == "approved"
            assert approved.json()["approval"]["approver"] == "demo-ic"

            sent = await client.post(
                f"/incidents/{incident_id}/briefs/{brief_id}/send",
                json={"requested_by": "demo-ic"},
            )
            assert sent.status_code == 200
            body = sent.json()
            assert body["brief"]["status"] == "sent_mock"
            assert body["send"]["channel"] == "mock"
            assert body["send"]["adapter"] == "mock"
            assert body["send"]["destination"].startswith("mock://")

            duplicate_send = await client.post(
                f"/incidents/{incident_id}/briefs/{brief_id}/send",
                json={"requested_by": "demo-ic"},
            )
            assert duplicate_send.status_code == 409

            no_new_facts = await client.post(
                f"/incidents/{incident_id}/briefs",
                json={"audience": "ic"},
            )
            assert no_new_facts.status_code == 409

            briefs = await client.get(f"/incidents/{incident_id}/briefs")
            assert briefs.json()[0]["brief"]["status"] == "sent_mock"

            timeline = await client.get(f"/incidents/{incident_id}/timeline")
            event_types = [event["event_type"] for event in timeline.json()]
            for expected in (
                "brief.drafted",
                "brief.checked",
                "brief.approved",
                "brief.send_mocked",
            ):
                assert expected in event_types

            audit = await client.get("/audit/verify")
            assert audit.json()["valid"] is True


@pytest.mark.asyncio
async def test_brief_audience_filters_claims(settings, pool):
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            created = await client.post(
                "/incidents",
                json={
                    "title": "Audience filter test",
                    "severity": "sev3",
                    "declared_by": "tester",
                },
            )
            incident_id = created.json()["id"]
            await client.post(
                f"/incidents/{incident_id}/facts",
                json=fact_payload(
                    "alert/edr/behavior",
                    "Synthetic alert",
                    "ev-aud-001",
                ),
            )
            await client.post(
                f"/incidents/{incident_id}/facts",
                json=fact_payload(
                    "regulatory/cert-in/clock",
                    {"candidate": True, "deadline_hours": 6},
                    "ev-aud-002",
                ),
            )

            technical = await client.post(
                f"/incidents/{incident_id}/briefs",
                json={"audience": "technical"},
            )
            legal = await client.post(
                f"/incidents/{incident_id}/briefs",
                json={"audience": "legal"},
            )

            assert technical.status_code == 201
            assert legal.status_code == 201
            assert all(
                "alert/" in claim["text"]
                for claim in technical.json()["brief"]["claims"]
            )
            assert all(
                "regulatory/" in claim["text"]
                for claim in legal.json()["brief"]["claims"]
            )
