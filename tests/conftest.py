import os
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
import pytest_asyncio
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from adjutant.config import Settings
from adjutant.db import init_db


def _test_database_url(base_url: str) -> str:
    parts = urlsplit(base_url)
    return urlunsplit(parts._replace(path="/adjutant_test"))


@pytest.fixture(scope="session")
def settings() -> Settings:
    base_url = os.getenv(
        "DATABASE_URL",
        "postgresql://adjutant:adjutant@localhost:5432/adjutant",
    )
    test_url = _test_database_url(base_url)

    with psycopg.connect(base_url, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'adjutant_test'"
        ).fetchone()
        if not exists:
            conn.execute("CREATE DATABASE adjutant_test")

    return Settings(database_url=test_url, seed_demo=False)


@pytest_asyncio.fixture
async def pool(settings: Settings):
    p = AsyncConnectionPool(
        conninfo=settings.database_url,
        open=False,
        kwargs={"row_factory": dict_row},
    )
    await p.open()
    await init_db(p)
    async with p.connection() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                TRUNCATE approval_requests, system_state, handoffs,
                         readiness_assessments, impact_mappings,
                         dispatch_assignments, dispatch_resolutions,
                         action_executions, containment_approvals,
                         policy_decisions, brief_sends, brief_approvals,
                         brief_checks, briefs, clocks, proposals, signals,
                         facts, incidents, events
                RESTART IDENTITY
                """
            )
    yield p
    await p.close()
