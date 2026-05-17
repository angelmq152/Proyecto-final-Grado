from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from lobster_agent.agent.mutations import MutationContext
from lobster_agent.domain.policy import PolicyDecision
from lobster_agent.domain.severity import ActionSeverity
from lobster_agent.persistence.db import create_db_engine, create_db_schema, create_sessionmaker
from lobster_agent.persistence.models import (
    ActionStatus,
    Approval,
    ApprovalSeverity,
    ApprovalStatus,
)
from lobster_agent.persistence.repositories import ActionRepository


@dataclass
class FakePolicy:
    decision: PolicyDecision

    def validate(
        self,
        action_type: str,
        namespace: str,
        manifest: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        return self.decision


class FakeApprovalManager:
    def __init__(self, status: ApprovalStatus) -> None:
        self.status = status
        self.requests: list[str] = []

    async def request_approval(self, req: object) -> Approval:
        self.requests.append("request")
        return Approval(
            id="approval-1",
            requested_at=datetime.now(UTC),
            case_use="test",
            action_type="restart_pod",
            action_payload={},
            severity=ApprovalSeverity.NORMAL,
            status=self.status,
            expires_at=datetime.now(UTC) + timedelta(seconds=60),
        )


async def test_autonomous_action_skips_approval_and_completes(tmp_path: Path) -> None:
    ctx, repo, approvals, engine = await _context(tmp_path, ActionSeverity.AUTONOMOUS)
    called = False

    async def executor() -> dict[str, str]:
        nonlocal called
        called = True
        return {"ok": "yes"}

    result = await ctx.execute("annotate_resource", "tenant-x", "pod-a", {}, None, executor)

    action = await repo.get(result.action_id)
    assert called is True
    assert approvals.requests == []
    assert result.status == ActionStatus.COMPLETED
    assert action is not None and action.status == ActionStatus.COMPLETED.value
    await engine.dispose()


async def test_normal_action_approved_runs_executor(tmp_path: Path) -> None:
    ctx, repo, approvals, engine = await _context(tmp_path, ActionSeverity.NORMAL)
    called = False

    async def executor() -> dict[str, str]:
        nonlocal called
        called = True
        return {"done": "true"}

    result = await ctx.execute("restart_pod", "tenant-x", "pod-a", {}, None, executor)

    action = await repo.get(result.action_id)
    assert approvals.requests == ["request"]
    assert called is True
    assert action is not None and action.status == ActionStatus.COMPLETED.value
    await engine.dispose()


async def test_normal_action_rejected_does_not_run_executor(tmp_path: Path) -> None:
    ctx, repo, approvals, engine = await _context(
        tmp_path,
        ActionSeverity.NORMAL,
        approval_status=ApprovalStatus.REJECTED,
    )
    called = False

    async def executor() -> dict[str, str]:
        nonlocal called
        called = True
        return {}

    result = await ctx.execute("restart_pod", "tenant-x", "pod-a", {}, None, executor)

    action = await repo.get(result.action_id)
    assert approvals.requests == ["request"]
    assert called is False
    assert result.status == ActionStatus.REJECTED
    assert action is not None and action.status == ActionStatus.REJECTED.value
    await engine.dispose()


async def test_policy_violation_skips_approval_and_executor(tmp_path: Path) -> None:
    ctx, repo, approvals, engine = await _context(
        tmp_path,
        ActionSeverity.FORBIDDEN,
        allowed=False,
    )
    called = False

    async def executor() -> dict[str, str]:
        nonlocal called
        called = True
        return {}

    result = await ctx.execute("restart_pod", "kube-system", "pod-a", {}, None, executor)

    action = await repo.get(result.action_id)
    assert approvals.requests == []
    assert called is False
    assert result.status == ActionStatus.ABORTED_POLICY
    assert action is not None and action.status == ActionStatus.ABORTED_POLICY.value
    await engine.dispose()


async def test_dry_run_skips_executor_and_stores_manifest(tmp_path: Path) -> None:
    ctx, repo, _approvals, engine = await _context(tmp_path, ActionSeverity.AUTONOMOUS)
    called = False
    manifest = {"kind": "Deployment", "metadata": {"name": "app"}}

    async def executor() -> dict[str, str]:
        nonlocal called
        called = True
        return {}

    result = await ctx.execute(
        "annotate_resource",
        "tenant-x",
        "deployment/app",
        {},
        manifest,
        executor,
        dry_run_override=True,
    )

    action = await repo.get(result.action_id)
    assert called is False
    assert result.status == ActionStatus.ABORTED_DRY_RUN
    assert result.data is not None and result.data["planned_manifest"] == manifest
    assert action is not None and action.result is not None
    assert "planned_manifest" in action.result
    await engine.dispose()


async def test_executor_exception_marks_failed(tmp_path: Path) -> None:
    ctx, repo, _approvals, engine = await _context(tmp_path, ActionSeverity.AUTONOMOUS)

    async def executor() -> dict[str, str]:
        raise RuntimeError("boom")

    result = await ctx.execute("annotate_resource", "tenant-x", "pod-a", {}, None, executor)

    action = await repo.get(result.action_id)
    assert result.status == ActionStatus.FAILED
    assert result.data == {"error": "boom", "type": "RuntimeError"}
    assert action is not None and action.status == ActionStatus.FAILED.value
    await engine.dispose()


async def _context(
    tmp_path: Path,
    severity: ActionSeverity,
    *,
    allowed: bool = True,
    approval_status: ApprovalStatus = ApprovalStatus.APPROVED,
) -> tuple[MutationContext, ActionRepository, FakeApprovalManager, AsyncEngine]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'state.db'}")
    await create_db_schema(engine)
    session_maker = create_sessionmaker(engine)
    repo = ActionRepository(session_maker)
    approvals = FakeApprovalManager(approval_status)

    async def repo_factory() -> ActionRepository:
        return repo

    ctx = MutationContext(
        repo_factory,
        approvals,
        FakePolicy(
            PolicyDecision(
                allowed=allowed,
                severity=severity,
                reason="ok" if allowed else "blocked",
                violations=[] if allowed else ["blocked"],
            )
        ),
        None,
        False,
    )
    return ctx, repo, approvals, engine
