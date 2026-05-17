from sqlalchemy import text

from lobster_agent.persistence.db import create_db_engine, create_db_schema, create_sessionmaker
from lobster_agent.persistence.models import AgentMode
from lobster_agent.persistence.repositories import AgentStateRepository


async def test_agent_state_singleton(tmp_path) -> None:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'state.db'}")
    await create_db_schema(engine)
    session_maker = create_sessionmaker(engine)

    repo = AgentStateRepository(session_maker)
    state = await repo.get()
    assert state.id == 1
    assert state.mode == AgentMode.NORMAL

    changed = await repo.set_mode(AgentMode.DRY_RUN, "maintenance", 123)
    assert changed.id == 1
    assert changed.mode == AgentMode.DRY_RUN
    assert changed.reason == "maintenance"
    assert changed.changed_by_user_id == 123
    assert changed.changed_at >= state.changed_at

    await engine.dispose()


async def test_agent_state_reads_lowercase_and_uppercase_database_values(tmp_path) -> None:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'state.db'}")
    await create_db_schema(engine)
    session_maker = create_sessionmaker(engine)

    async with session_maker() as session:
        await session.execute(
            text(
                "INSERT INTO agent_state (id, mode, changed_at) "
                "VALUES (1, 'normal', CURRENT_TIMESTAMP)"
            )
        )
        await session.commit()

    state = await AgentStateRepository(session_maker).get()
    assert state.mode == AgentMode.NORMAL

    async with session_maker() as session:
        await session.execute(text("UPDATE agent_state SET mode = 'DRY_RUN' WHERE id = 1"))
        await session.commit()

    state = await AgentStateRepository(session_maker).get()
    assert state.mode == AgentMode.DRY_RUN

    await engine.dispose()
