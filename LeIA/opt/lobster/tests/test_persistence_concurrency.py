"""Regression test: ensure that long-running mutation flows do not block
unrelated writes to the SQLite database.

Before the persistence refactor a single AsyncSession was shared by all
repositories. A mutation flow that issued a commit and then blocked on
`wait_for_decision()` left the connection in a transactional state; any
concurrent write from another coroutine raised
`Method 'commit()' can't be called here; method '_prepare_impl()' is already
in progress` or `database is locked`. After the refactor each repository
opens its own short-lived session per call.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from lobster_agent.agent.mutations import MutationContext
from lobster_agent.domain.policy import PolicyDecision
from lobster_agent.domain.severity import ActionSeverity
from lobster_agent.persistence.db import create_db_engine, create_db_schema, create_sessionmaker
from lobster_agent.persistence.models import (
    Approval,
    ApprovalSeverity,
    ApprovalStatus,
    ConversationTurn,
    Decision,
)
from lobster_agent.persistence.repositories import (
    ActionRepository,
    ApprovalRepository,
    ConversationRepository,
    DecisionRepository,
)


class _FakePolicy:
    def validate(
        self,
        action_type: str,
        namespace: str,
        manifest=None,
        context=None,
    ) -> PolicyDecision:
        return PolicyDecision(
            allowed=True,
            severity=ActionSeverity.NORMAL,
            reason="ok",
            violations=[],
        )


class _SlowApprovalManager:
    """Approval manager that blocks the mutation flow long enough for other
    coroutines to attempt concurrent writes against SQLite."""

    def __init__(self, wait_seconds: float) -> None:
        self._wait_seconds = wait_seconds

    async def request_approval(self, _request) -> Approval:
        return Approval(
            id="approval-concurrency",
            requested_at=datetime.now(UTC),
            case_use="test",
            action_type="restart_pod",
            action_payload={},
            severity=ApprovalSeverity.NORMAL,
            status=ApprovalStatus.PENDING,
            expires_at=datetime.now(UTC) + timedelta(seconds=60),
        )

    async def wait_for_decision(self, _approval_id: str) -> Approval:
        await asyncio.sleep(self._wait_seconds)
        return Approval(
            id="approval-concurrency",
            requested_at=datetime.now(UTC),
            case_use="test",
            action_type="restart_pod",
            action_payload={},
            severity=ApprovalSeverity.NORMAL,
            status=ApprovalStatus.APPROVED,
            decided_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(seconds=60),
        )


async def test_concurrent_writes_do_not_lock_database(tmp_path: Path) -> None:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'state.db'}")
    await create_db_schema(engine)
    session_maker = create_sessionmaker(engine)

    action_repo = ActionRepository(session_maker)
    decision_repo = DecisionRepository(session_maker)
    conv_repo = ConversationRepository(session_maker)
    approval_repo = ApprovalRepository(session_maker)

    async def action_repo_factory() -> ActionRepository:
        return action_repo

    ctx = MutationContext(
        action_repo_factory,
        _SlowApprovalManager(wait_seconds=0.5),
        _FakePolicy(),
        None,
        False,
    )

    async def executor() -> dict[str, str]:
        return {"ok": "true"}

    async def mutation_flow() -> str:
        result = await ctx.execute(
            "restart_pod",
            "tenant-x",
            "pod-a",
            {},
            None,
            executor,
        )
        return result.status.value

    async def hammer_writes() -> int:
        committed = 0
        for index in range(15):
            await decision_repo.save(
                Decision(
                    case_use="test",
                    model_used="qwen3:8b",
                    think_mode=False,
                    prompt_summary=f"concurrent {index}",
                    conclusion="ok",
                )
            )
            await conv_repo.append(chat_id=42, role="user", content=f"msg {index}", case_use="test")
            await asyncio.sleep(0.02)
            committed += 1
        return committed

    async def hammer_reads() -> int:
        observed = 0
        for _ in range(15):
            await approval_repo.list_pending()
            await asyncio.sleep(0.02)
            observed += 1
        return observed

    mutation_status, writes_done, reads_done = await asyncio.gather(
        mutation_flow(),
        hammer_writes(),
        hammer_reads(),
    )

    assert mutation_status == "completed"
    assert writes_done == 15
    assert reads_done == 15

    decisions = await decision_repo.list_recent(limit=20)
    assert len(decisions) == 15
    turns = await conv_repo.load_recent(chat_id=42, limit=20)
    assert len(turns) == 15
    assert all(isinstance(turn, ConversationTurn) for turn in turns)

    await engine.dispose()
