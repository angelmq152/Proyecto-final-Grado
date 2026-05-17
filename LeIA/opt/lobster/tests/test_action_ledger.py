import json
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from lobster_agent.persistence.db import create_db_engine, create_db_schema, create_sessionmaker
from lobster_agent.persistence.models import Action, ActionStatus
from lobster_agent.persistence.repositories import VALID_ACTION_TRANSITIONS, ActionRepository


async def test_action_create_persists(tmp_path: Path) -> None:
    repo, engine = await _repo(tmp_path)
    action = await repo.create(_action("restart_pod", "pod-a"))

    found = await repo.get(action.id)
    assert found is not None
    assert found.action_type == "restart_pod"
    assert found.status == ActionStatus.PENDING.value
    await engine.dispose()


async def test_action_update_status_transitions(tmp_path: Path) -> None:
    repo, engine = await _repo(tmp_path)
    action = await repo.create(_action("restart_pod", "pod-a"))

    for status in (
        ActionStatus.AWAITING_APPROVAL,
        ActionStatus.APPROVED,
        ActionStatus.RUNNING,
        ActionStatus.COMPLETED,
    ):
        action = await repo.update_status(action.id, status, {"status": status.value})
        assert action.status == status.value

    assert action.result is not None
    assert json.loads(action.result)["status"] == ActionStatus.COMPLETED.value
    await engine.dispose()


async def test_action_list_recent_orders_newest_first(tmp_path: Path) -> None:
    repo, engine = await _repo(tmp_path)
    first = await repo.create(_action("restart_pod", "pod-a"))
    second = await repo.create(_action("restart_pod", "pod-b"))

    recent = await repo.list_recent(limit=2)

    assert [action.id for action in recent] == [second.id, first.id]
    await engine.dispose()


async def test_action_count_by_status(tmp_path: Path) -> None:
    repo, engine = await _repo(tmp_path)
    await repo.create(_action("restart_pod", "pod-a", ActionStatus.PENDING))
    await repo.create(_action("restart_pod", "pod-b", ActionStatus.ABORTED_POLICY))

    counts = await repo.count_by_status()

    assert counts[ActionStatus.PENDING.value] == 1
    assert counts[ActionStatus.ABORTED_POLICY.value] == 1
    await engine.dispose()


async def test_action_rejects_invalid_transitions(tmp_path: Path) -> None:
    repo, engine = await _repo(tmp_path)
    action = await repo.create(_action("restart_pod", "pod-a", ActionStatus.COMPLETED))

    with pytest.raises(ValueError, match="invalid action transition"):
        await repo.update_status(action.id, ActionStatus.RUNNING)

    for current, allowed_targets in VALID_ACTION_TRANSITIONS.items():
        for target in ActionStatus:
            candidate = await repo.create(_action("restart_pod", f"{current}-{target}", current))
            if target in allowed_targets:
                updated = await repo.update_status(candidate.id, target)
                assert updated.status == target.value
            else:
                with pytest.raises(ValueError):
                    await repo.update_status(candidate.id, target)
    await engine.dispose()


def _action(
    action_type: str,
    target: str,
    status: ActionStatus = ActionStatus.PENDING,
) -> Action:
    return Action(
        action_type=action_type,
        namespace="tenant-x",
        target=target,
        severity="normal",
        status=status.value,
        payload="{}",
    )


async def _repo(tmp_path: Path) -> tuple[ActionRepository, AsyncEngine]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'state.db'}")
    await create_db_schema(engine)
    session_maker = create_sessionmaker(engine)
    return ActionRepository(session_maker), engine
