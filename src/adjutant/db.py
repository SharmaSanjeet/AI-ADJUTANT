from importlib import resources

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


def make_pool(database_url: str) -> AsyncConnectionPool:
    return AsyncConnectionPool(
        conninfo=database_url,
        open=False,
        kwargs={"row_factory": dict_row},
    )


async def init_db(pool: AsyncConnectionPool) -> None:
    schema = resources.files("adjutant").joinpath("schema.sql").read_text(encoding="utf-8")
    async with pool.connection() as conn:
        await conn.execute(schema)
        await conn.commit()
