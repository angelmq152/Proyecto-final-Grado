from sqlalchemy import text

from lobster_agent.persistence.db import create_db_engine, create_db_schema


async def test_create_db_schema_creates_decisions_table(tmp_path) -> None:
    db_path = tmp_path / "state.db"
    engine = create_db_engine(f"sqlite+aiosqlite:///{db_path}")

    await create_db_schema(engine)

    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='decisions'")
        )

    assert result.scalar_one() == "decisions"
    await engine.dispose()
