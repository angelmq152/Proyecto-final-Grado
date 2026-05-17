from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, String
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, SQLModel

from lobster_agent.domain.severity import ActionSeverity


def utc_now() -> datetime:
    return datetime.now(UTC)


class Decision(SQLModel, table=True):
    __tablename__ = "decisions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    timestamp: datetime = Field(default_factory=utc_now, index=True)
    trigger: str = Field(default="manual", index=True)
    case_use: str = Field(index=True)
    model_used: str
    think_mode: bool
    prompt_summary: str
    reasoning: str | None = None
    conclusion: str
    tokens_input: int = 0
    tokens_output: int = 0
    latency_ms: int = 0
    tools_called: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    derived_actions: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class ActionStatus(StrEnum):
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED_DRY_RUN = "aborted_dry_run"
    ABORTED_POLICY = "aborted_policy"


class Action(SQLModel, table=True):
    __tablename__ = "actions"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)
    action_type: str = Field(index=True)
    namespace: str = Field(index=True)
    target: str
    severity: str = Field(default=ActionSeverity.NORMAL.value, index=True)
    status: str = Field(default=ActionStatus.PENDING.value, index=True)
    payload: str = Field(default="{}")
    result: str | None = None
    decision_id: str | None = Field(default=None, foreign_key="decisions.id", index=True)
    approval_id: str | None = Field(default=None, index=True)
    dry_run: bool = False

    # Legacy columns kept so databases created from earlier additive migrations remain writable.
    timestamp_created: datetime = Field(default_factory=utc_now, index=True)
    timestamp_started: datetime | None = None
    timestamp_finished: datetime | None = None
    category: str = Field(default="", index=True)
    target_namespace: str | None = Field(default=None, index=True)
    target_kind: str | None = None
    target_name: str | None = None
    idempotency_key: str | None = Field(default=None, index=True)
    state: str = Field(default=ActionStatus.PENDING.value, index=True)
    error: str | None = None


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalSeverity(StrEnum):
    NORMAL = "normal"
    CRITICAL = "critical"


class AgentMode(StrEnum):
    NORMAL = "normal"
    DRY_RUN = "dry_run"
    PAUSED = "paused"


class StrEnumValueType(TypeDecorator[str]):
    """Persist StrEnum values, not enum member names, with legacy name compatibility."""

    impl = String
    cache_ok = True

    def __init__(self, enum_type: type[StrEnum], *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.enum_type = enum_type

    def process_bind_param(self, value: object, dialect: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, self.enum_type):
            return str(value.value)
        if isinstance(value, str):
            return _normalize_enum_string(self.enum_type, value).value
        raise TypeError(f"Unsupported value for {self.enum_type.__name__}: {value!r}")

    def process_result_value(self, value: object, dialect: object) -> StrEnum | None:
        if value is None:
            return None
        if isinstance(value, self.enum_type):
            return value
        if isinstance(value, str):
            return _normalize_enum_string(self.enum_type, value)
        raise TypeError(f"Unsupported database value for {self.enum_type.__name__}: {value!r}")


def _normalize_enum_string(enum_type: type[StrEnum], value: str) -> StrEnum:
    normalized = value.strip()
    for member in enum_type:
        if normalized == member.value or normalized.casefold() == member.value.casefold():
            return member
        if normalized == member.name or normalized.casefold() == member.name.casefold():
            return member
    valid = ", ".join(member.value for member in enum_type)
    raise ValueError(f"{value!r} is not a valid {enum_type.__name__}; expected one of: {valid}")


class Approval(SQLModel, table=True):
    __tablename__ = "approvals"

    id: str = Field(primary_key=True)
    requested_at: datetime = Field(default_factory=utc_now, index=True)
    case_use: str
    action_type: str
    action_payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    tenant_namespace: str | None = None
    severity: ApprovalSeverity = Field(
        default=ApprovalSeverity.NORMAL,
        sa_column=Column(StrEnumValueType(ApprovalSeverity), nullable=False, index=True),
    )
    status: ApprovalStatus = Field(
        default=ApprovalStatus.PENDING,
        sa_column=Column(StrEnumValueType(ApprovalStatus), nullable=False, index=True),
    )
    expires_at: datetime = Field(index=True)
    decided_at: datetime | None = None
    decided_by_user_id: int | None = None
    decision_reason: str | None = None
    telegram_chat_id: int | None = None
    telegram_message_id: int | None = None
    reminder_count: int = 0
    last_reminder_at: datetime | None = None
    related_decision_id: str | None = None


class ConversationTurn(SQLModel, table=True):
    __tablename__ = "conversation_turns"

    id: int | None = Field(default=None, primary_key=True)
    chat_id: int = Field(index=True)
    role: str  # "user" | "assistant"
    content: str
    case_use: str
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ToolRequest(SQLModel, table=True):
    __tablename__ = "tool_requests"

    id: int | None = Field(default=None, primary_key=True)
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    case_use: str
    user_query: str = Field(max_length=500)
    tool_name_suggested: str
    description: str
    suggested_inputs: str = Field(default="[]")  # JSON-encoded list of strings
    status: str = Field(default="pending", index=True)
    decision_id: str | None = None  # nullable reference to decisions.id


class AgentState(SQLModel, table=True):
    __tablename__ = "agent_state"

    id: int = Field(default=1, primary_key=True)
    mode: AgentMode = Field(
        default=AgentMode.NORMAL,
        sa_column=Column(StrEnumValueType(AgentMode), nullable=False, index=True),
    )
    reason: str | None = None
    changed_at: datetime = Field(default_factory=utc_now)
    changed_by_user_id: int | None = None


class Event(SQLModel, table=True):
    __tablename__ = "events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    timestamp: datetime = Field(default_factory=utc_now, index=True)
    source: str = Field(index=True)
    severity: str = Field(index=True)
    target_namespace: str | None = Field(default=None, index=True)
    payload: dict[str, object] = Field(default_factory=dict, sa_column=Column(JSON))
    derived_decision_id: UUID | None = Field(default=None, foreign_key="decisions.id", index=True)


class TenantState(SQLModel, table=True):
    __tablename__ = "tenant_state"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    timestamp: datetime = Field(default_factory=utc_now, index=True)
    namespace: str = Field(index=True)
    tier: str
    type: str
    pods_running: int
    cpu_avg_5m: float
    memory_avg_5m: float
    requests_last_hour: int
    errors_last_hour: int
    last_active: datetime | None = None
    is_scaled_to_zero: bool = False


class MetricsSnapshot(SQLModel, table=True):
    __tablename__ = "metrics_snapshots"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    timestamp: datetime = Field(default_factory=utc_now, index=True)
    node: str = Field(index=True)
    cpu_pct: float
    memory_pct: float
    disk_pct: float
    network_in_bps: int
    network_out_bps: int
    gpu_pct: float | None = None
    gpu_vram_pct: float | None = None
