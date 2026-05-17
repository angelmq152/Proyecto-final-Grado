from lobster_agent.persistence.db import create_db_engine, create_db_schema, create_sessionmaker
from lobster_agent.persistence.models import Decision
from lobster_agent.persistence.repositories import DecisionRepository


async def test_decision_repository_crud(tmp_path) -> None:
    db_path = tmp_path / "state.db"
    engine = create_db_engine(f"sqlite+aiosqlite:///{db_path}")
    await create_db_schema(engine)
    session_maker = create_sessionmaker(engine)

    repo = DecisionRepository(session_maker)
    saved = await repo.save(
        Decision(
            case_use="conversation",
            model_used="qwen3:32b",
            think_mode=True,
            prompt_summary="hola",
            conclusion="ok",
        )
    )

    loaded = await repo.get_by_id(saved.id)
    recent = await repo.list_recent()
    by_case_use = await repo.list_by_case_use("conversation")

    assert loaded is not None
    assert loaded.id == saved.id
    assert len(recent) == 1
    assert len(by_case_use) == 1
    assert by_case_use[0].case_use == "conversation"

    await engine.dispose()
