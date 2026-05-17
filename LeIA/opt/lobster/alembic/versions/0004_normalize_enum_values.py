"""normalize persisted enum values

Revision ID: 0004_normalize_enums
Revises: 0003_approvals_state
Create Date: 2026-05-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_normalize_enums"
down_revision: str | None = "0003_approvals_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE agent_state SET mode = lower(mode)")
    op.execute("UPDATE approvals SET status = lower(status)")
    op.execute("UPDATE approvals SET severity = lower(severity)")


def downgrade() -> None:
    op.execute("UPDATE agent_state SET mode = upper(mode)")
    op.execute("UPDATE approvals SET status = upper(status)")
    op.execute("UPDATE approvals SET severity = upper(severity)")
