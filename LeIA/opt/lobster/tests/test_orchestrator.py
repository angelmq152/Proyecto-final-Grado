from pydantic_ai.models.test import TestModel

from lobster_agent.agent.orchestrator import LobsterAgent
from lobster_agent.agent.routing import CaseUse
from lobster_agent.persistence.db import create_db_engine, create_db_schema, create_sessionmaker
from lobster_agent.persistence.repositories import DecisionRepository
from tests.conftest import make_test_settings


async def test_agent_run_persists_decision(tmp_path) -> None:
    db_path = tmp_path / "state.db"
    settings = make_test_settings(database={"url": f"sqlite+aiosqlite:///{db_path}"})
    agent = LobsterAgent(
        settings,
        model_factory=lambda _model, _think: TestModel(
            call_tools=[],
            custom_output_text="respuesta ok",
        ),
    )

    result = await agent.run(CaseUse.CONVERSATION, "hola")
    await agent.close()

    assert result.outcome == "success"
    assert result.data == "respuesta ok"

    engine = create_db_engine(settings.database.url)
    await create_db_schema(engine)
    session_maker = create_sessionmaker(engine)
    repo = DecisionRepository(session_maker)
    decision = await repo.get_by_id(result.decision_id)

    assert decision is not None
    assert decision.case_use == CaseUse.CONVERSATION.value
    assert decision.model_used == "qwen3:32b"
    assert decision.think_mode is True
    assert decision.conclusion == "respuesta ok"
    await engine.dispose()


async def test_agent_run_handles_failure_and_persists(tmp_path) -> None:
    db_path = tmp_path / "state.db"
    settings = make_test_settings(database={"url": f"sqlite+aiosqlite:///{db_path}"})

    def broken_model(_model: str, _think: bool) -> TestModel:
        raise RuntimeError("ollama down")

    agent = LobsterAgent(settings, model_factory=broken_model)

    result = await agent.run(CaseUse.SUMMARY, "resume")
    await agent.close()

    assert result.outcome == "failed"
    assert result.error is not None

    engine = create_db_engine(settings.database.url)
    await create_db_schema(engine)
    session_maker = create_sessionmaker(engine)
    repo = DecisionRepository(session_maker)
    decision = await repo.get_by_id(result.decision_id)

    assert decision is not None
    assert decision.case_use == CaseUse.SUMMARY.value
    assert decision.think_mode is False
    assert "ollama down" in decision.conclusion
    await engine.dispose()


async def test_agent_caches_per_model_and_think_mode(tmp_path) -> None:
    db_path = tmp_path / "state.db"
    settings = make_test_settings(database={"url": f"sqlite+aiosqlite:///{db_path}"})
    calls: list[tuple[str, bool]] = []

    def model_factory(model: str, think: bool) -> TestModel:
        calls.append((model, think))
        return TestModel(call_tools=[], custom_output_text="ok")

    agent = LobsterAgent(settings, model_factory=model_factory)

    await agent.run(CaseUse.CONVERSATION, "uno")
    await agent.run(CaseUse.CONVERSATION, "dos")
    await agent.run(CaseUse.SUMMARY, "tres")
    await agent.close()

    assert calls == [("qwen3:32b", True), ("qwen3:8b", False)]
