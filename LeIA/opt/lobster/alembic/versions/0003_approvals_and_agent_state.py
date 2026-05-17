"""approvals queue and agent state

Revision ID: 0003_approvals_state
Revises: 0002_tools_called
Create Date: 2026-05-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_approvals_state"
down_revision: str | None = "0002_tools_called"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "approvals" in inspector.get_table_names():
        op.rename_table("approvals", "approvals_legacy")

    op.create_table(
        "approvals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("case_use", sa.String(), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("action_payload", sa.JSON(), nullable=False),
        sa.Column("tenant_namespace", sa.String(), nullable=True),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decided_by_user_id", sa.Integer(), nullable=True),
        sa.Column("decision_reason", sa.String(), nullable=True),
        sa.Column("telegram_chat_id", sa.Integer(), nullable=True),
        sa.Column("telegram_message_id", sa.Integer(), nullable=True),
        sa.Column("reminder_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_reminder_at", sa.DateTime(), nullable=True),
        sa.Column("related_decision_id", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_approvals_status_requested_at",
        "approvals",
        ["status", "requested_at"],
    )
    op.create_index("ix_approvals_expires_at", "approvals", ["expires_at"])

    op.create_table(
        "agent_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False, server_default="normal"),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
        sa.Column("changed_by_user_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_agent_state_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "INSERT INTO agent_state (id, mode, changed_at) VALUES (1, 'normal', CURRENT_TIMESTAMP)"
    )


def downgrade() -> None:
    op.drop_table("agent_state")
    op.drop_index("ix_approvals_expires_at", table_name="approvals")
    op.drop_index("ix_approvals_status_requested_at", table_name="approvals")
    op.drop_table("approvals")

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "approvals_legacy" in inspector.get_table_names():
        op.rename_table("approvals_legacy", "approvals")
