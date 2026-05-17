from datetime import UTC, datetime, timedelta

from lobster_agent.agent.approvals import ApprovalMaintenanceLoop
from lobster_agent.persistence.db import create_db_engine, create_db_schema, create_sessionmaker
from lobster_agent.persistence.models import Approval, ApprovalSeverity, ApprovalStatus
from lobster_agent.persistence.repositories import ApprovalRepository
from lobster_agent.telegram.notifier import FakeTelegramNotifier
from tests.conftest import make_test_settings


async def test_approval_maintenance_expires_and_reminds(tmp_path) -> None:
    settings = make_test_settings()
    settings.approval.critical_reminder_interval_seconds = 60
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'state.db'}")
    await create_db_schema(engine)
    session_maker = create_sessionmaker(engine)
    repo = ApprovalRepository(session_maker)
    notifier = FakeTelegramNotifier(settings)
    now = datetime.now(UTC)
    await repo.create(
        Approval(
            id="old",
            requested_at=now - timedelta(minutes=10),
            case_use="test",
            action_type="old",
            action_payload={},
            expires_at=now - timedelta(seconds=1),
        )
    )
    await repo.create(
        Approval(
            id="critical",
            requested_at=now,
            case_use="test",
            action_type="critical",
            action_payload={},
            severity=ApprovalSeverity.CRITICAL,
            expires_at=now + timedelta(minutes=5),
            last_reminder_at=now - timedelta(minutes=5),
        )
    )

    async def repo_factory() -> ApprovalRepository:
        return repo

    loop = ApprovalMaintenanceLoop(repo_factory, notifier, settings.approval)
    await loop.tick()
    expired = await repo.get("old")
    reminded = await repo.get("critical")
    assert expired is not None and expired.status == ApprovalStatus.EXPIRED
    assert reminded is not None and reminded.reminder_count == 1
    assert ("send_reminder", "critical") in notifier.calls
    assert ("update_approval_message", "old") in notifier.calls
    await engine.dispose()
