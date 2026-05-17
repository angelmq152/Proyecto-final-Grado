"""add conversation_turns table

Revision ID: 0005_conversation_turns
Revises: 0004_normalize_enums
Create Date: 2026-05-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_conversation_turns"
down_revision: str | None = "0004_normalize_enums"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_turns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("case_use", sa.String(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_conversation_turns_chat_id"),
        "conversation_turns",
        ["chat_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_conversation_turns_chat_id"), table_name="conversation_turns")
    op.drop_table("conversation_turns")
