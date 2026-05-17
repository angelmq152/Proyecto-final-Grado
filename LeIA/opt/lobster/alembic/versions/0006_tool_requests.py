"""add tool_requests table

Revision ID: 0006_tool_requests
Revises: 0005_conversation_turns
Create Date: 2026-05-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_tool_requests"
down_revision: str | None = "0005_conversation_turns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tool_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("case_use", sa.String(), nullable=False),
        sa.Column("user_query", sa.String(500), nullable=False),
        sa.Column("tool_name_suggested", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("suggested_inputs", sa.String(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("decision_id", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tool_requests_requested_at"),
        "tool_requests",
        ["requested_at"],
    )
    op.create_index(
        op.f("ix_tool_requests_status"),
        "tool_requests",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_tool_requests_status"), table_name="tool_requests")
    op.drop_index(op.f("ix_tool_requests_requested_at"), table_name="tool_requests")
    op.drop_table("tool_requests")
