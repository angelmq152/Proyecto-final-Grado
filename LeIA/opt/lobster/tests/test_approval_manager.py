import asyncio

from lobster_agent.agent.approvals import ApprovalManager, ApprovalRequest
from lobster_agent.persistence.db import create_db_engine, create_db_schema, create_sessionmaker
from lobster_agent.persistence.models import AgentMode, ApprovalSeverity, ApprovalStatus
from lobster_agent.persistence.repositories import AgentStateRepository, ApprovalRepository
from lobster_agent.telegram.notifier import FakeTelegramNotifier
from tests.conftest import make_test_settings


async def test_approval_manager_normal_posts_request(tmp_path) -> None:
    manager, repo, _state_repo, notifier, engine = await _manager(tmp_path)
    approval = await manager.request_approval(
        ApprovalRequest(case_use="test", action_type="restart", action_payload={"pod": "x"})
    )
    assert approval.status == ApprovalStatus.PENDING
    assert ("post_approval_request", approval.id) in notifier.calls
    assert await repo.count_pending() == 1
    await engine.dispose()


async def test_approval_manager_dry_run_auto_approves(tmp_path) -> None:
    manager, _repo, state_repo, _notifier, engine = await _manager(tmp_path)
    await state_repo.set_mode(AgentMode.DRY_RUN, "test", None)
    approval = await manager.request_approval(
        ApprovalRequest(case_use="test", action_type="restart", action_payload={})
    )
    assert approval.status == ApprovalStatus.APPROVED
    assert approval.decision_reason == "dry_run_auto_approved"
    await engine.dispose()


async def test_approval_manager_paused_rejects(tmp_path) -> None:
    manager, _repo, state_repo, _notifier, engine = await _manager(tmp_path)
    await state_repo.set_mode(AgentMode.PAUSED, "test", None)
    approval = await manager.request_approval(
        ApprovalRequest(case_use="test", action_type="restart", action_payload={})
    )
    assert approval.status == ApprovalStatus.REJECTED
    assert approval.decision_reason == "agent_paused"
    await engine.dispose()


async def test_approval_manager_wait_for_decision(tmp_path) -> None:
    manager, repo, _state_repo, _notifier, engine = await _manager(tmp_path)
    approval = await manager.request_approval(
        ApprovalRequest(case_use="test", action_type="restart", action_payload={})
    )

    async def approve_later() -> None:
        await asyncio.sleep(0.01)
        await repo.update_status(approval.id, ApprovalStatus.APPROVED, 1, None)

    task = asyncio.create_task(approve_later())
    resolved = await manager.wait_for_decision(approval.id, poll_interval_seconds=0.01)
    await task
    assert resolved.status == ApprovalStatus.APPROVED
    await engine.dispose()


async def test_approval_manager_cancel_updates_message(tmp_path) -> None:
    manager, _repo, _state_repo, notifier, engine = await _manager(tmp_path)
    approval = await manager.request_approval(
        ApprovalRequest(case_use="test", action_type="restart", action_payload={})
    )
    cancelled = await manager.cancel(approval.id, "operator")
    assert cancelled is not None
    assert cancelled.status == ApprovalStatus.CANCELLED
    assert ("update_approval_message", approval.id) in notifier.calls
    await engine.dispose()


async def test_approval_manager_queue_full_rejects(tmp_path) -> None:
    settings = make_test_settings()
    settings.approval.max_pending_approvals = 1
    manager, _repo, _state_repo, _notifier, engine = await _manager(tmp_path, settings=settings)
    await manager.request_approval(
        ApprovalRequest(
            case_use="test",
            action_type="first",
            action_payload={},
            severity=ApprovalSeverity.NORMAL,
            custom_timeout_seconds=60,
        )
    )
    second = await manager.request_approval(
        ApprovalRequest(case_use="test", action_type="second", action_payload={})
    )
    assert second.status == ApprovalStatus.REJECTED
    assert second.decision_reason == "queue_full"
    await engine.dispose()


async def _manager(tmp_path, settings=None):
    settings = settings or make_test_settings()
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'state.db'}")
    await create_db_schema(engine)
    session_maker = create_sessionmaker(engine)
    repo = ApprovalRepository(session_maker)
    state_repo = AgentStateRepository(session_maker)
    notifier = FakeTelegramNotifier(settings)

    async def approval_repo_factory() -> ApprovalRepository:
        return repo

    async def agent_state_repo_factory() -> AgentStateRepository:
        return state_repo

    manager = ApprovalManager(
        approval_repo_factory,
        agent_state_repo_factory,
        notifier,
        settings.approval,
    )
    return manager, repo, state_repo, notifier, engine
