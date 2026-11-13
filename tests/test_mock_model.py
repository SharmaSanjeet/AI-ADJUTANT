import pytest

from adjutant.ports.model import ExtractedSignal, MockModelAdapter


@pytest.mark.asyncio
async def test_mock_extraction_is_deterministic():
    model = MockModelAdapter()

    first = await model.extract("synthetic alert text", ExtractedSignal)
    second = await model.extract("synthetic alert text", ExtractedSignal)

    assert first == second
    assert first.kind == "unknown"
    assert first.confidence == 0.5


@pytest.mark.asyncio
async def test_mock_draft_is_deterministic():
    model = MockModelAdapter()

    first = await model.draft("Draft a stakeholder brief", {})
    second = await model.draft("Draft a stakeholder brief", {})

    assert first == second
    assert first.startswith("[MOCK DRAFT]")
