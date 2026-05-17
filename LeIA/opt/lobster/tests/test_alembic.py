from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command


def test_alembic_initial_migration_upgrade_and_downgrade(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "state.db"
    monkeypatch.setenv("LOBSTER_DATABASE__URL", f"sqlite+aiosqlite:///{db_path}")

    config = Config("alembic.ini")
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).scalars()
        assert "decisions" in set(tables)

    command.downgrade(config, "base")
    with engine.connect() as conn:
        tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).scalars()
        assert "decisions" not in set(tables)

    engine.dispose()


def test_alembic_normalizes_phase4_enum_values(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "state.db"
    monkeypatch.setenv("LOBSTER_DATABASE__URL", f"sqlite+aiosqlite:///{db_path}")

    config = Config("alembic.ini")
    command.upgrade(config, "0003_approvals_state")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("UPDATE agent_state SET mode = 'NORMAL' WHERE id = 1"))
        conn.execute(
            text(
                "INSERT INTO approvals "
                "(id, requested_at, case_use, action_type, action_payload, severity, status, "
                "expires_at, reminder_count) "
                "VALUES "
                "('a1', CURRENT_TIMESTAMP, 'test', 'restart', '{}', 'CRITICAL', 'PENDING', "
                "CURRENT_TIMESTAMP, 0)"
            )
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        mode = conn.execute(text("SELECT mode FROM agent_state WHERE id = 1")).scalar_one()
        row = conn.execute(text("SELECT severity, status FROM approvals WHERE id = 'a1'")).one()
        assert mode == "normal"
        assert row == ("critical", "pending")
    engine.dispose()
