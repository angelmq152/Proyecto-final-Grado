import asyncio

from typer.testing import CliRunner

from lobster_agent.cli import app
from lobster_agent.persistence.db import create_db_engine, create_db_schema, create_sessionmaker
from lobster_agent.persistence.repositories import ApprovalRepository
from lobster_agent.telegram.messages import format_approval_request


def test_create_test_approval_formats_without_error(tmp_path, monkeypatch) -> None:
    """approvals create-test must succeed and leave a PENDING approval in DB.

    After the approval is persisted, its datetime fields come back from SQLite as
    naive UTC.  format_approval_request must handle them without raising TypeError.
    """
    db_path = tmp_path / "state.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    monkeypatch.setenv("LOBSTER_DATABASE__URL", db_url)
    monkeypatch.setenv("LOBSTER_TELEGRAM__ENABLED", "false")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "approvals",
            "create-test",
            "--action-type",
            "restart_pod",
            "--severity",
            "normal",
            "--payload",
            '{"namespace":"tenant-x","pod":"wordpress-abc"}',
        ],
    )
    assert result.exit_code == 0, result.output
    assert "pending" in result.output

    # Last line is "<uuid> pending"; earlier lines may contain structlog output.
    approval_id = result.output.strip().split("\n")[-1].split()[0]

    async def _verify() -> None:
        # Use db_url directly from closure — avoids re-instantiating Settings(),
        # which could pick up a different config source.
        engine = create_db_engine(db_url)
        await create_db_schema(engine)
        session_maker = create_sessionmaker(engine)
        approval = await ApprovalRepository(session_maker).get(approval_id)
        await engine.dispose()

        assert approval is not None
        assert approval.status.value == "pending"
        # expires_at is naive after the SQLite round-trip — this must not raise TypeError
        msg = format_approval_request(approval)
        assert "restart" in msg

    asyncio.run(_verify())
