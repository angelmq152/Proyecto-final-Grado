import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import structlog

from lobster_agent.config import ApprovalConfig
from lobster_agent.observability.metrics import lobster_approvals_pending
from lobster_agent.persistence.models import (
    AgentMode,
    Approval,
    ApprovalSeverity,
    ApprovalStatus,
)
from lobster_agent.persistence.repositories import AgentStateRepository, ApprovalRepository
from lobster_agent.telegram.notifier import TelegramNotifier

log = structlog.get_logger()


ApprovalRepoFactory = Callable[[], Awaitable[ApprovalRepository]]
AgentStateRepoFactory = Callable[[], Awaitable[AgentStateRepository]]


@dataclass(frozen=True)
class ApprovalRequest:
    case_use: str
    action_type: str
    action_payload: dict[str, Any]
    severity: ApprovalSeverity = ApprovalSeverity.NORMAL
    tenant_namespace: str | None = None
    related_decision_id: str | None = None
    custom_timeout_seconds: int | None = None


class ApprovalManager:
    """Create and resolve human approvals.

    wait_for_decision can block for minutes. Callers that run inside LLM tools should configure
    compatible timeouts or prefer returning a pending approval id and re-checking in a later cycle.
    """

    def __init__(
        self,
        approval_repo_factory: ApprovalRepoFactory,
        agent_state_repo_factory: AgentStateRepoFactory,
        notifier: TelegramNotifier,
        config: ApprovalConfig,
    ) -> None:
        self._approval_repo_factory = approval_repo_factory
        self._agent_state_repo_factory = agent_state_repo_factory
        self._notifier = notifier
        self._config = config

    async def request_approval(self, req: ApprovalRequest) -> Approval:
        approval_repo = await self._approval_repo_factory()
        state_repo = await self._agent_state_repo_factory()
        state = await state_repo.get()
        now = datetime.now(UTC)
        timeout = req.custom_timeout_seconds
        if timeout is None:
            timeout = (
                self._config.critical_timeout_seconds
                if req.severity == ApprovalSeverity.CRITICAL
                else self._config.default_timeout_seconds
            )
        approval = Approval(
            id=str(uuid4()),
            requested_at=now,
            case_use=req.case_use,
            action_type=req.action_type,
            action_payload=req.action_payload,
            tenant_namespace=req.tenant_namespace,
            severity=req.severity,
            status=ApprovalStatus.PENDING,
            expires_at=now + timedelta(seconds=timeout),
            related_decision_id=req.related_decision_id,
        )

        if state.mode == AgentMode.PAUSED:
            approval.status = ApprovalStatus.REJECTED
            approval.decided_at = now
            approval.decision_reason = "agent_paused"
            return await approval_repo.create(approval)

        if await approval_repo.count_pending() >= self._config.max_pending_approvals:
            approval.status = ApprovalStatus.REJECTED
            approval.decided_at = now
            approval.decision_reason = "queue_full"
            return await approval_repo.create(approval)

        approval = await approval_repo.create(approval)
        if state.mode == AgentMode.DRY_RUN:
            return (
                await approval_repo.update_status(
                    approval.id,
                    ApprovalStatus.APPROVED,
                    None,
                    "dry_run_auto_approved",
                )
                or approval
            )

        chat_id, message_id = await self._notifier.post_approval_request(approval)
        if chat_id and message_id:
            await approval_repo.set_telegram_message(approval.id, chat_id, message_id)
            refreshed = await approval_repo.get(approval.id)
            if refreshed is not None:
                approval = refreshed
        return approval

    async def wait_for_decision(
        self,
        approval_id: str,
        poll_interval_seconds: float = 1.0,
    ) -> Approval:
        repo = await self._approval_repo_factory()
        while True:
            approval = await repo.get(approval_id)
            if approval is None:
                raise ValueError(f"approval not found: {approval_id}")
            if approval.status != ApprovalStatus.PENDING:
                return approval
            if _aware(approval.expires_at) <= datetime.now(UTC):
                expired = await repo.update_status(
                    approval_id,
                    ApprovalStatus.EXPIRED,
                    None,
                    "expired",
                )
                return expired or approval
            await asyncio.sleep(poll_interval_seconds)

    async def cancel(self, approval_id: str, reason: str) -> Approval | None:
        repo = await self._approval_repo_factory()
        approval = await repo.update_status(approval_id, ApprovalStatus.CANCELLED, None, reason)
        if approval is not None:
            await self._notifier.update_approval_message(approval)
        return approval


class ApprovalMaintenanceLoop:
    def __init__(
        self,
        approval_repo_factory: ApprovalRepoFactory,
        notifier: TelegramNotifier,
        config: ApprovalConfig,
    ) -> None:
        self._approval_repo_factory = approval_repo_factory
        self._notifier = notifier
        self._config = config
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if self._task is None:
            self._stopping.clear()
            self._task = asyncio.create_task(self._run(), name="lobster-approval-maintenance")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def tick(self) -> None:
        repo = await self._approval_repo_factory()
        now = datetime.now(UTC)
        await repo.expire_overdue(now)
        lobster_approvals_pending.set(await repo.count_pending())
        expired = await repo.list_expired_decided_since(now - timedelta(seconds=5))
        for approval in expired:
            await self._notifier.update_approval_message(approval)

        due = await repo.list_pending_critical_due_for_reminder(
            now,
            self._config.critical_reminder_interval_seconds,
        )
        for approval in due:
            await self._notifier.send_reminder(approval)
            await repo.increment_reminder(approval.id)

    async def _run(self) -> None:
        interval = min(30.0, max(1.0, self._config.critical_reminder_interval_seconds / 2))
        while not self._stopping.is_set():
            try:
                await self.tick()
            except Exception as exc:
                log.warning("lobster.approvals.maintenance_failed", error=str(exc))
            await asyncio.sleep(interval)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
