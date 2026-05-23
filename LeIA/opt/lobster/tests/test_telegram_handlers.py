from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from lobster_agent.agent.orchestrator import AgentResult
from lobster_agent.agent.routing import CaseUse
from lobster_agent.persistence.db import create_db_engine, create_db_schema, create_sessionmaker
from lobster_agent.persistence.models import AgentMode, Approval, ApprovalStatus, ToolRequest
from lobster_agent.persistence.repositories import (
    AgentStateRepository,
    ApprovalRepository,
    ToolRequestRepository,
)
from lobster_agent.telegram.handlers import (
    handle_approve_callback,
    handle_forget,
    handle_free_text,
    handle_pause,
    handle_resume,
    handle_status,
    handle_think,
    handle_toolrequests,
)
from lobster_agent.telegram.notifier import FakeTelegramNotifier
from tests.conftest import make_test_settings


class FakePlaceholder:
    def __init__(self) -> None:
        self.edits: list[str] = []

    async def edit_text(self, text: str, **_: object) -> "FakePlaceholder":
        self.edits.append(text)
        return self


class FakeMessage:
    def __init__(self, text: str, user_id: int = 111) -> None:
        self.text = text
        self.from_user = SimpleNamespace(id=user_id, username="alice")
        self.chat = SimpleNamespace(id=user_id)
        self.answers: list[str] = []
        self.edits: list[str] = []
        self._placeholder = FakePlaceholder()

    async def answer(self, text: str, **_: object) -> FakePlaceholder:
        self.answers.append(text)
        return self._placeholder

    async def edit_text(self, text: str, **_: object) -> None:
        self.edits.append(text)


class FakeAgent:
    def __init__(self, result_data: str = "respuesta de prueba") -> None:
        self.calls: list[tuple[str, str]] = []
        self._result_data = result_data
        self.should_fail = False
        self.last_history: list[tuple[str, str]] | None = None

    async def run(
        self,
        case_use: CaseUse,
        user_input: str,
        message_history: list[tuple[str, str]] | None = None,
        **_: object,
    ) -> AgentResult:
        self.calls.append((case_use.value, user_input))
        self.last_history = message_history
        if self.should_fail:
            raise RuntimeError("fallo simulado")
        return AgentResult(
            decision_id=uuid4(),
            outcome="success",
            data=self._result_data,
        )


class FakeMemory:
    def __init__(self, history: list[tuple[str, str]] | None = None) -> None:
        self._history: dict[int, list[tuple[str, str]]] = {}
        self.appended: list[tuple[int, str, str, str]] = []
        self.cleared: list[int] = []
        self.warmed: list[int] = []
        if history:
            self._history[111] = list(history)

    async def warm_up(self, chat_id: int) -> None:
        self.warmed.append(chat_id)

    def get_history(self, chat_id: int) -> list[tuple[str, str]]:
        return list(self._history.get(chat_id, []))

    async def append(self, chat_id: int, role: str, content: str, case_use: str) -> None:
        self.appended.append((chat_id, role, content, case_use))

    async def clear(self, chat_id: int) -> None:
        self.cleared.append(chat_id)
        self._history.pop(chat_id, None)


class FakeCallback:
    def __init__(self, data: str, user_id: int = 111) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=user_id, username="alice")
        self.message = FakeMessage("")
        self.answers: list[str] = []

    async def answer(self, text: str, **_: object) -> None:
        self.answers.append(text)


async def test_status_ignores_unauthorized_user(tmp_path) -> None:
    settings, repo_factory, state_factory, notifier, engine, *_ = await _ctx(tmp_path)
    message = FakeMessage("/status", user_id=999)
    await handle_status(message, settings, repo_factory, state_factory, notifier=notifier)
    assert message.answers == []
    await engine.dispose()


async def test_status_authorized_reports_state(tmp_path) -> None:
    settings, repo_factory, state_factory, notifier, engine, *_ = await _ctx(tmp_path)
    message = FakeMessage("/status")
    await handle_status(message, settings, repo_factory, state_factory, notifier=notifier)
    assert "Modo: normal" in message.answers[0]
    await engine.dispose()


async def test_pause_and_resume_change_state(tmp_path) -> None:
    settings, _repo_factory, state_factory, notifier, engine, *_ = await _ctx(tmp_path)
    await handle_pause(FakeMessage("/pause prueba"), settings, state_factory, notifier)
    state_repo = await state_factory()
    assert (await state_repo.get()).mode == AgentMode.PAUSED

    await handle_resume(FakeMessage("/resume"), settings, state_factory, notifier)
    assert (await state_repo.get()).mode == AgentMode.NORMAL
    await engine.dispose()


async def test_approve_callback_updates_pending_approval(tmp_path) -> None:
    settings, repo_factory, _state_factory, _notifier, engine, *_ = await _ctx(tmp_path)
    repo = await repo_factory()
    now = datetime.now(UTC)
    await repo.create(
        Approval(
            id="approval-123",
            requested_at=now,
            case_use="test",
            action_type="restart",
            action_payload={},
            expires_at=now + timedelta(minutes=5),
        )
    )
    callback = FakeCallback("approve:approval-123")
    await handle_approve_callback(callback, settings, repo_factory)
    approval = await repo.get("approval-123")
    assert approval is not None
    assert approval.status == ApprovalStatus.APPROVED
    assert callback.message.edits
    await engine.dispose()


async def test_approve_callback_resolved_noops(tmp_path) -> None:
    settings, repo_factory, _state_factory, _notifier, engine, *_ = await _ctx(tmp_path)
    repo = await repo_factory()
    now = datetime.now(UTC)
    await repo.create(
        Approval(
            id="approval-123",
            requested_at=now,
            case_use="test",
            action_type="restart",
            action_payload={},
            status=ApprovalStatus.REJECTED,
            expires_at=now + timedelta(minutes=5),
        )
    )
    callback = FakeCallback("approve:approval-123")
    await handle_approve_callback(callback, settings, repo_factory)
    assert callback.answers == ["Esta aprobación ya estaba resuelta"]
    await engine.dispose()


async def test_think_with_text_calls_agent(tmp_path) -> None:
    settings, _, _, _, engine, *_ = await _ctx(tmp_path)
    agent = FakeAgent()
    memory = FakeMemory()
    message = FakeMessage("/think cuántos nodos hay")
    await handle_think(message, settings, agent, memory)
    assert len(agent.calls) == 1
    assert agent.calls[0] == ("think", "cuántos nodos hay")
    assert message.answers == ["🧠 Pensando con razonamiento profundo…"]
    assert message._placeholder.edits == ["respuesta de prueba"]
    await engine.dispose()


async def test_think_without_args_returns_error(tmp_path) -> None:
    settings, _, _, _, engine, *_ = await _ctx(tmp_path)
    agent = FakeAgent()
    memory = FakeMemory()
    message = FakeMessage("/think")
    await handle_think(message, settings, agent, memory)
    assert agent.calls == []
    assert any("Uso:" in a for a in message.answers)
    await engine.dispose()


async def test_free_text_allowed_user_calls_agent(tmp_path) -> None:
    settings, _, _, _, engine, *_ = await _ctx(tmp_path)
    agent = FakeAgent()
    memory = FakeMemory()
    message = FakeMessage("hola, cómo estás")
    await handle_free_text(message, settings, agent, memory)
    assert len(agent.calls) == 1
    assert agent.calls[0] == ("chat", "hola, cómo estás")
    assert message.answers == ["🤔 Pensando…"]
    assert message._placeholder.edits == ["respuesta de prueba"]
    await engine.dispose()


async def test_free_text_unknown_user_no_response(tmp_path) -> None:
    settings, _, _, _, engine, *_ = await _ctx(tmp_path)
    agent = FakeAgent()
    memory = FakeMemory()
    message = FakeMessage("hola", user_id=999)
    await handle_free_text(message, settings, agent, memory)
    assert agent.calls == []
    assert message.answers == []
    await engine.dispose()


async def test_free_text_slash_command_ignored(tmp_path) -> None:
    settings, _, _, _, engine, *_ = await _ctx(tmp_path)
    agent = FakeAgent()
    memory = FakeMemory()
    message = FakeMessage("/desconocido")
    await handle_free_text(message, settings, agent, memory)
    assert agent.calls == []
    assert message.answers == []
    await engine.dispose()


async def test_agent_exception_sends_error_message(tmp_path) -> None:
    settings, _, _, _, engine, *_ = await _ctx(tmp_path)
    agent = FakeAgent()
    agent.should_fail = True
    memory = FakeMemory()
    message = FakeMessage("esto fallará")
    await handle_free_text(message, settings, agent, memory)
    assert message.answers == ["🤔 Pensando…"]
    assert len(message._placeholder.edits) == 1
    assert "Error" in message._placeholder.edits[0]
    await engine.dispose()


async def test_free_text_passes_history_to_agent(tmp_path) -> None:
    settings, _, _, _, engine, *_ = await _ctx(tmp_path)
    existing = [("user", "antes"), ("assistant", "sí")]
    agent = FakeAgent()
    memory = FakeMemory(history=existing)
    message = FakeMessage("ahora")
    await handle_free_text(message, settings, agent, memory)
    assert agent.last_history == existing
    # Both user and assistant turns are appended after success
    roles = [(r, content) for _, r, content, _ in memory.appended]
    assert ("user", "ahora") in roles
    assert ("assistant", "respuesta de prueba") in roles
    await engine.dispose()


async def test_forget_clears_memory(tmp_path) -> None:
    settings, _, _, _, engine, *_ = await _ctx(tmp_path)
    memory = FakeMemory(history=[("user", "algo")])
    message = FakeMessage("/forget")
    await handle_forget(message, settings, memory)
    assert 111 in memory.cleared
    assert "Memoria borrada" in message.answers[0]
    await engine.dispose()


async def test_toolrequests_with_pending_items(tmp_path) -> None:
    settings, _, _, _, engine, tool_request_repo_factory, tool_request_repo = await _ctx(tmp_path)
    await tool_request_repo.create(
        ToolRequest(
            case_use="chat",
            user_query="necesito escalar pods",
            tool_name_suggested="scale_deployment",
            description="Scale a deployment to a given replica count",
        )
    )
    message = FakeMessage("/toolrequests")
    await handle_toolrequests(message, settings, tool_request_repo_factory)
    assert len(message.answers) == 1
    assert "scale" in message.answers[0]
    await engine.dispose()


async def test_toolrequests_empty(tmp_path) -> None:
    settings, _, _, _, engine, tool_request_repo_factory, _ = await _ctx(tmp_path)
    message = FakeMessage("/toolrequests")
    await handle_toolrequests(message, settings, tool_request_repo_factory)
    assert len(message.answers) == 1
    assert "pendientes" in message.answers[0]
    await engine.dispose()


async def _ctx(tmp_path):
    settings = make_test_settings(telegram={"allowed_user_ids": [111]})
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'state.db'}")
    await create_db_schema(engine)
    session_maker = create_sessionmaker(engine)
    approval_repo = ApprovalRepository(session_maker)
    state_repo = AgentStateRepository(session_maker)
    tool_request_repo = ToolRequestRepository(session_maker)
    notifier = FakeTelegramNotifier(settings)

    async def approval_repo_factory() -> ApprovalRepository:
        return approval_repo

    async def agent_state_repo_factory() -> AgentStateRepository:
        return state_repo

    async def tool_request_repo_factory() -> ToolRequestRepository:
        return tool_request_repo

    return (
        settings,
        approval_repo_factory,
        agent_state_repo_factory,
        notifier,
        engine,
        tool_request_repo_factory,
        tool_request_repo,
    )
