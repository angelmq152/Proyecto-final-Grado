from typer.testing import CliRunner

from lobster_agent.cli import app


def test_cli_approvals_create_test_and_list(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "state.db"
    monkeypatch.setenv("LOBSTER_DATABASE__URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("LOBSTER_TELEGRAM__ENABLED", "false")
    runner = CliRunner()

    created = runner.invoke(
        app,
        [
            "approvals",
            "create-test",
            "--action-type",
            "restart_pod",
            "--severity",
            "normal",
            "--payload",
            '{"namespace":"tenant-x"}',
        ],
    )
    assert created.exit_code == 0
    assert "pending" in created.output

    listed = runner.invoke(app, ["approvals", "list", "--status", "pending"])
    assert listed.exit_code == 0
    assert "restart_pod" in listed.output
