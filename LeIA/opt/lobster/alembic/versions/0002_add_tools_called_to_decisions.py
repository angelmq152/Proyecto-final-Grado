"""add tools_called to decisions

Revision ID: 0002_tools_called
Revises: 0001_initial
Create Date: 2026-05-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_tools_called"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("decisions", sa.Column("tools_called", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("decisions", "tools_called")
