import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from lobster_agent.persistence.models import (
    Action,
    ActionStatus,
    AgentMode,
    AgentState,
    Approval,
    ApprovalSeverity,
    ApprovalStatus,
    ConversationTurn,
    Decision,
    ToolRequest,
    utc_now,
)

VALID_ACTION_TRANSITIONS: dict[ActionStatus, set[ActionStatus]] = {
    ActionStatus.PENDING: {
        ActionStatus.AWAITING_APPROVAL,
        ActionStatus.RUNNING,
        ActionStatus.ABORTED_DRY_RUN,
        ActionStatus.ABORTED_POLICY,
    },
    ActionStatus.AWAITING_APPROVAL: {
        ActionStatus.APPROVED,
        ActionStatus.REJECTED,
        ActionStatus.ABORTED_POLICY,
    },
    ActionStatus.APPROVED: {
        ActionStatus.RUNNING,
        ActionStatus.ABORTED_DRY_RUN,
        ActionStatus.ABORTED_POLICY,
    },
    ActionStatus.REJECTED: set(),
    ActionStatus.RUNNING: {ActionStatus.COMPLETED, ActionStatus.FAILED},
    ActionStatus.COMPLETED: set(),
    ActionStatus.FAILED: set(),
    ActionStatus.ABORTED_DRY_RUN: set(),
    ActionStatus.ABORTED_POLICY: set(),
}


class DecisionRepository:
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self._session_maker = session_maker

    async def save(self, decision: Decision) -> Decision:
        async with self._session_maker() as session:
            session.add(decision)
            await session.commit()
            await session.refresh(decision)
            return decision

    async def get_by_id(self, decision_id: UUID) -> Decision | None:
        async with self._session_maker() as session:
            return await session.get(Decision, decision_id)

    async def list_recent(self, limit: int = 10) -> list[Decision]:
        statement = select(Decision).order_by(text("timestamp DESC")).limit(limit)
        async with self._session_maker() as session:
            result = await session.execute(statement)
            return list(result.scalars().all())

    async def list_by_case_use(self, case_use: str, limit: int = 10) -> list[Decision]:
        statement = (
            select(Decision)
            .where(Decision.case_use == case_use)
            .order_by(text("timestamp DESC"))
            .limit(limit)
        )
        async with self._session_maker() as session:
            result = await session.execute(statement)
            return list(result.scalars().all())


class ActionRepository:
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self._session_maker = session_maker

    async def create(self, action: Action) -> Action:
        action.status = _status_value(action.status)
        action.state = action.status
        action.category = action.category or action.action_type
        action.target_namespace = action.target_namespace or action.namespace
        action.target_name = action.target_name or action.target
        action.updated_at = utc_now()
        async with self._session_maker() as session:
            session.add(action)
            await session.commit()
            await session.refresh(action)
            return action

    async def update_status(
        self,
        action_id: str,
        status: ActionStatus,
        result: dict[str, object] | None = None,
    ) -> Action:
        async with self._session_maker() as session:
            action = await session.get(Action, action_id)
            if action is None:
                raise ValueError(f"action not found: {action_id}")
            current = _status_enum(action.status)
            if status not in VALID_ACTION_TRANSITIONS[current]:
                raise ValueError(f"invalid action transition: {current.value} -> {status.value}")
            action.status = status.value
            action.state = status.value
            action.updated_at = utc_now()
            if status == ActionStatus.RUNNING:
                action.timestamp_started = action.updated_at
            if status in {
                ActionStatus.COMPLETED,
                ActionStatus.FAILED,
                ActionStatus.ABORTED_DRY_RUN,
                ActionStatus.ABORTED_POLICY,
                ActionStatus.REJECTED,
            }:
                action.timestamp_finished = action.updated_at
            if result is not None:
                action.result = json.dumps(result, sort_keys=True)
                if status == ActionStatus.FAILED:
                    error = result.get("error")
                    action.error = str(error) if error is not None else action.result
            session.add(action)
            await session.commit()
            await session.refresh(action)
            return action

    async def set_approval_id(self, action_id: str, approval_id: str) -> Action:
        async with self._session_maker() as session:
            action = await session.get(Action, action_id)
            if action is None:
                raise ValueError(f"action not found: {action_id}")
            action.approval_id = approval_id
            action.updated_at = utc_now()
            session.add(action)
            await session.commit()
            await session.refresh(action)
            return action

    async def get(self, action_id: str) -> Action | None:
        async with self._session_maker() as session:
            return await session.get(Action, action_id)

    async def list_recent(
        self,
        limit: int = 20,
        status: ActionStatus | None = None,
    ) -> list[Action]:
        statement = select(Action).order_by(text("created_at DESC")).limit(limit)
        if status is not None:
            statement = (
                select(Action)
                .where(Action.status == status.value)
                .order_by(text("created_at DESC"))
                .limit(limit)
            )
        async with self._session_maker() as session:
            result = await session.execute(statement)
            return list(result.scalars().all())

    async def count_by_status(self) -> dict[str, int]:
        statement = select(Action.status, func.count()).group_by(Action.status)
        async with self._session_maker() as session:
            result = await session.execute(statement)
            return {str(status): int(count) for status, count in result.all()}


class ApprovalRepository:
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self._session_maker = session_maker

    async def create(self, approval: Approval) -> Approval:
        async with self._session_maker() as session:
            session.add(approval)
            await session.commit()
            await session.refresh(approval)
            return approval

    async def get(self, approval_id: str) -> Approval | None:
        async with self._session_maker() as session:
            return await session.get(Approval, approval_id)

    async def list_pending(self) -> list[Approval]:
        statement = (
            select(Approval)
            .where(Approval.status == ApprovalStatus.PENDING)
            .order_by(text("requested_at ASC"))
        )
        async with self._session_maker() as session:
            result = await session.execute(statement)
            return list(result.scalars().all())

    async def list_pending_critical_due_for_reminder(
        self,
        now: datetime,
        interval_seconds: int,
    ) -> list[Approval]:
        cutoff = now - timedelta(seconds=interval_seconds)
        statement = (
            select(Approval)
            .where(Approval.status == ApprovalStatus.PENDING)
            .where(Approval.severity == ApprovalSeverity.CRITICAL)
            .order_by(text("requested_at ASC"))
        )
        async with self._session_maker() as session:
            result = await session.execute(statement)
            approvals = list(result.scalars().all())
        return [
            approval
            for approval in approvals
            if approval.last_reminder_at is None or _aware(approval.last_reminder_at) <= cutoff
        ]

    async def list_recent(
        self,
        limit: int = 20,
        status: ApprovalStatus | None = None,
    ) -> list[Approval]:
        statement = select(Approval).order_by(text("requested_at DESC")).limit(limit)
        if status is not None:
            statement = (
                select(Approval)
                .where(Approval.status == status)
                .order_by(text("requested_at DESC"))
                .limit(limit)
            )
        async with self._session_maker() as session:
            result = await session.execute(statement)
            return list(result.scalars().all())

    async def update_status(
        self,
        approval_id: str,
        new_status: ApprovalStatus,
        decided_by_user_id: int | None,
        decision_reason: str | None,
    ) -> Approval | None:
        async with self._session_maker() as session:
            approval = await session.get(Approval, approval_id)
            if approval is None:
                return None
            approval.status = new_status
            approval.decided_at = utc_now()
            approval.decided_by_user_id = decided_by_user_id
            approval.decision_reason = decision_reason
            session.add(approval)
            await session.commit()
            await session.refresh(approval)
            return approval

    async def increment_reminder(self, approval_id: str) -> None:
        async with self._session_maker() as session:
            approval = await session.get(Approval, approval_id)
            if approval is None:
                return
            approval.reminder_count += 1
            approval.last_reminder_at = utc_now()
            session.add(approval)
            await session.commit()

    async def set_telegram_message(self, approval_id: str, chat_id: int, message_id: int) -> None:
        async with self._session_maker() as session:
            approval = await session.get(Approval, approval_id)
            if approval is None:
                return
            approval.telegram_chat_id = chat_id
            approval.telegram_message_id = message_id
            session.add(approval)
            await session.commit()

    async def expire_overdue(self, now: datetime) -> int:
        statement = (
            select(Approval)
            .where(Approval.status == ApprovalStatus.PENDING)
            .where(Approval.expires_at < now)
        )
        async with self._session_maker() as session:
            result = await session.execute(statement)
            approvals = list(result.scalars().all())
            for approval in approvals:
                approval.status = ApprovalStatus.EXPIRED
                approval.decided_at = now
                approval.decision_reason = "expired"
                session.add(approval)
            await session.commit()
            return len(approvals)

    async def list_expired_decided_since(self, since: datetime) -> list[Approval]:
        statement = select(Approval).where(Approval.status == ApprovalStatus.EXPIRED)
        async with self._session_maker() as session:
            result = await session.execute(statement)
            approvals = list(result.scalars().all())
        return [
            approval
            for approval in approvals
            if approval.decided_at is not None and _aware(approval.decided_at) >= since
        ]

    async def count_pending(self) -> int:
        statement = (
            select(func.count())
            .select_from(Approval)
            .where(Approval.status == ApprovalStatus.PENDING)
        )
        async with self._session_maker() as session:
            result = await session.execute(statement)
            return int(result.scalar_one())


class AgentStateRepository:
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self._session_maker = session_maker

    async def get(self) -> AgentState:
        async with self._session_maker() as session:
            state = await session.get(AgentState, 1)
            if state is None:
                state = AgentState(id=1, mode=AgentMode.NORMAL, changed_at=datetime.now(UTC))
                session.add(state)
                await session.commit()
                await session.refresh(state)
            return state

    async def set_mode(
        self,
        mode: AgentMode,
        reason: str | None,
        user_id: int | None,
    ) -> AgentState:
        async with self._session_maker() as session:
            state = await session.get(AgentState, 1)
            if state is None:
                state = AgentState(id=1, mode=AgentMode.NORMAL, changed_at=datetime.now(UTC))
                session.add(state)
                await session.commit()
                await session.refresh(state)
            state.mode = mode
            state.reason = reason
            state.changed_at = datetime.now(UTC)
            state.changed_by_user_id = user_id
            session.add(state)
            await session.commit()
            await session.refresh(state)
            return state


class ConversationRepository:
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self._session_maker = session_maker

    async def append(self, chat_id: int, role: str, content: str, case_use: str) -> None:
        turn = ConversationTurn(chat_id=chat_id, role=role, content=content, case_use=case_use)
        async with self._session_maker() as session:
            session.add(turn)
            await session.commit()

    async def load_recent(self, chat_id: int, limit: int) -> list[ConversationTurn]:
        statement = (
            select(ConversationTurn)
            .where(ConversationTurn.chat_id == chat_id)
            .order_by(text("recorded_at DESC"))
            .limit(limit)
        )
        async with self._session_maker() as session:
            result = await session.execute(statement)
            turns = list(result.scalars().all())
        return list(reversed(turns))  # oldest first

    async def clear(self, chat_id: int) -> None:
        async with self._session_maker() as session:
            result = await session.execute(
                select(ConversationTurn).where(ConversationTurn.chat_id == chat_id)
            )
            for turn in result.scalars().all():
                await session.delete(turn)
            await session.commit()


class ToolRequestRepository:
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self._session_maker = session_maker

    async def create(self, tool_request: ToolRequest) -> ToolRequest:
        async with self._session_maker() as session:
            session.add(tool_request)
            await session.commit()
            await session.refresh(tool_request)
            return tool_request

    async def list_recent(
        self,
        limit: int = 20,
        status: str | None = None,
    ) -> list[ToolRequest]:
        if status is not None:
            statement = (
                select(ToolRequest)
                .where(ToolRequest.status == status)
                .order_by(text("requested_at DESC"))
                .limit(limit)
            )
        else:
            statement = select(ToolRequest).order_by(text("requested_at DESC")).limit(limit)
        async with self._session_maker() as session:
            result = await session.execute(statement)
            return list(result.scalars().all())

    async def count_pending(self) -> int:
        statement = (
            select(func.count()).select_from(ToolRequest).where(ToolRequest.status == "pending")
        )
        async with self._session_maker() as session:
            result = await session.execute(statement)
            return int(result.scalar_one())


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _status_value(value: str | ActionStatus) -> str:
    if isinstance(value, ActionStatus):
        return value.value
    return _status_enum(value).value


def _status_enum(value: str | ActionStatus) -> ActionStatus:
    if isinstance(value, ActionStatus):
        return value
    return ActionStatus(value)
