"""add mutation action ledger columns

Revision ID: 0007_actions
Revises: 0006_tool_requests
Create Date: 2026-05-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_actions"
down_revision: str | None = "0006_tool_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "actions",
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.add_column(
        "actions",
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.add_column(
        "actions",
        sa.Column("action_type", sa.String(), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "actions",
        sa.Column("namespace", sa.String(), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "actions",
        sa.Column("target", sa.String(), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "actions",
        sa.Column("severity", sa.String(), nullable=False, server_default="normal"),
    )
    op.add_column(
        "actions",
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
    )
    op.add_column("actions", sa.Column("result", sa.String(), nullable=True))
    op.add_column("actions", sa.Column("approval_id", sa.String(), nullable=True))
    op.create_index(op.f("ix_actions_action_type"), "actions", ["action_type"])
    op.create_index(op.f("ix_actions_approval_id"), "actions", ["approval_id"])
    op.create_index(op.f("ix_actions_created_at"), "actions", ["created_at"])
    op.create_index(op.f("ix_actions_namespace"), "actions", ["namespace"])
    op.create_index(op.f("ix_actions_severity"), "actions", ["severity"])
    op.create_index(op.f("ix_actions_status"), "actions", ["status"])
    op.create_index(op.f("ix_actions_updated_at"), "actions", ["updated_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_actions_updated_at"), table_name="actions")
    op.drop_index(op.f("ix_actions_status"), table_name="actions")
    op.drop_index(op.f("ix_actions_severity"), table_name="actions")
    op.drop_index(op.f("ix_actions_namespace"), table_name="actions")
    op.drop_index(op.f("ix_actions_created_at"), table_name="actions")
    op.drop_index(op.f("ix_actions_approval_id"), table_name="actions")
    op.drop_index(op.f("ix_actions_action_type"), table_name="actions")
    op.drop_column("actions", "approval_id")
    op.drop_column("actions", "result")
    op.drop_column("actions", "status")
    op.drop_column("actions", "severity")
    op.drop_column("actions", "target")
    op.drop_column("actions", "namespace")
    op.drop_column("actions", "action_type")
    op.drop_column("actions", "updated_at")
    op.drop_column("actions", "created_at")
