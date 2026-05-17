"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("trigger", sa.String(), nullable=False),
        sa.Column("case_use", sa.String(), nullable=False),
        sa.Column("model_used", sa.String(), nullable=False),
        sa.Column("think_mode", sa.Boolean(), nullable=False),
        sa.Column("prompt_summary", sa.String(), nullable=False),
        sa.Column("reasoning", sa.String(), nullable=True),
        sa.Column("conclusion", sa.String(), nullable=False),
        sa.Column("tokens_input", sa.Integer(), nullable=False),
        sa.Column("tokens_output", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("derived_actions", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decisions_case_use", "decisions", ["case_use"])
    op.create_index("ix_decisions_timestamp", "decisions", ["timestamp"])
    op.create_index("ix_decisions_trigger", "decisions", ["trigger"])

    op.create_table(
        "actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=True),
        sa.Column("timestamp_created", sa.DateTime(), nullable=False),
        sa.Column("timestamp_started", sa.DateTime(), nullable=True),
        sa.Column("timestamp_finished", sa.DateTime(), nullable=True),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("target_namespace", sa.String(), nullable=True),
        sa.Column("target_kind", sa.String(), nullable=True),
        sa.Column("target_name", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["decision_id"], ["decisions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_actions_category", "actions", ["category"])
    op.create_index("ix_actions_decision_id", "actions", ["decision_id"])
    op.create_index("ix_actions_idempotency_key", "actions", ["idempotency_key"])
    op.create_index("ix_actions_state", "actions", ["state"])
    op.create_index("ix_actions_target_namespace", "actions", ["target_namespace"])
    op.create_index("ix_actions_timestamp_created", "actions", ["timestamp_created"])

    op.create_table(
        "approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("timestamp_requested", sa.DateTime(), nullable=False),
        sa.Column("timestamp_responded", sa.DateTime(), nullable=True),
        sa.Column("requested_by", sa.String(), nullable=False),
        sa.Column("responded_by", sa.String(), nullable=True),
        sa.Column("decision", sa.String(), nullable=True),
        sa.Column("repromptings", sa.Integer(), nullable=False),
        sa.Column("is_critical", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["action_id"], ["actions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approvals_action_id", "approvals", ["action_id"])
    op.create_index("ix_approvals_decision", "approvals", ["decision"])
    op.create_index("ix_approvals_timestamp_requested", "approvals", ["timestamp_requested"])

    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("target_namespace", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("derived_decision_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["derived_decision_id"], ["decisions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_derived_decision_id", "events", ["derived_decision_id"])
    op.create_index("ix_events_severity", "events", ["severity"])
    op.create_index("ix_events_source", "events", ["source"])
    op.create_index("ix_events_target_namespace", "events", ["target_namespace"])
    op.create_index("ix_events_timestamp", "events", ["timestamp"])

    op.create_table(
        "tenant_state",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("namespace", sa.String(), nullable=False),
        sa.Column("tier", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("pods_running", sa.Integer(), nullable=False),
        sa.Column("cpu_avg_5m", sa.Float(), nullable=False),
        sa.Column("memory_avg_5m", sa.Float(), nullable=False),
        sa.Column("requests_last_hour", sa.Integer(), nullable=False),
        sa.Column("errors_last_hour", sa.Integer(), nullable=False),
        sa.Column("last_active", sa.DateTime(), nullable=True),
        sa.Column("is_scaled_to_zero", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tenant_state_namespace", "tenant_state", ["namespace"])
    op.create_index("ix_tenant_state_timestamp", "tenant_state", ["timestamp"])

    op.create_table(
        "metrics_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("node", sa.String(), nullable=False),
        sa.Column("cpu_pct", sa.Float(), nullable=False),
        sa.Column("memory_pct", sa.Float(), nullable=False),
        sa.Column("disk_pct", sa.Float(), nullable=False),
        sa.Column("network_in_bps", sa.Integer(), nullable=False),
        sa.Column("network_out_bps", sa.Integer(), nullable=False),
        sa.Column("gpu_pct", sa.Float(), nullable=True),
        sa.Column("gpu_vram_pct", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_metrics_snapshots_node", "metrics_snapshots", ["node"])
    op.create_index("ix_metrics_snapshots_timestamp", "metrics_snapshots", ["timestamp"])


def downgrade() -> None:
    op.drop_table("metrics_snapshots")
    op.drop_table("tenant_state")
    op.drop_table("events")
    op.drop_table("approvals")
    op.drop_table("actions")
    op.drop_table("decisions")
