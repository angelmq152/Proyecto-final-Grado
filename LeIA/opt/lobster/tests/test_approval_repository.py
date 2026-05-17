from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from lobster_agent.persistence.db import create_db_engine, create_db_schema, create_sessionmaker
from lobster_agent.persistence.models import Approval, ApprovalSeverity, ApprovalStatus
from lobster_agent.persistence.repositories import ApprovalRepository


async def test_approval_repository_lifecycle(tmp_path) -> None:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'state.db'}")
    await create_db_schema(engine)
    session_maker = create_sessionmaker(engine)
    now = datetime.now(UTC)

    repo = ApprovalRepository(session_maker)
    approval = await repo.create(
        Approval(
            id="approval-1",
            requested_at=now,
            case_use="test",
            action_type="restart_pod",
            action_payload={"pod": "x"},
            severity=ApprovalSeverity.CRITICAL,
            expires_at=now + timedelta(minutes=5),
            last_reminder_at=now - timedelta(minutes=10),
        )
    )
    pending = await repo.list_pending()
    assert any(item.id == approval.id for item in pending)
    assert await repo.count_pending() == 1

    due = await repo.list_pending_critical_due_for_reminder(now, 60)
    assert [item.id for item in due] == ["approval-1"]

    await repo.set_telegram_message("approval-1", 123, 456)
    loaded = await repo.get("approval-1")
    assert loaded is not None
    assert loaded.telegram_chat_id == 123
    assert loaded.telegram_message_id == 456

    updated = await repo.update_status("approval-1", ApprovalStatus.APPROVED, 99, "ok")
    assert updated is not None
    assert updated.status == ApprovalStatus.APPROVED
    assert await repo.list_pending() == []
    assert await repo.count_pending() == 0

    await engine.dispose()


async def test_approval_repository_reads_lowercase_and_uppercase_enum_values(tmp_path) -> None:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'state.db'}")
    await create_db_schema(engine)
    session_maker = create_sessionmaker(engine)

    async with session_maker() as session:
        await session.execute(
            text(
                "INSERT INTO approvals "
                "(id, requested_at, case_use, action_type, action_payload, severity, status, "
                "expires_at, reminder_count) "
                "VALUES "
                "('lower', CURRENT_TIMESTAMP, 'test', 'restart', '{}', 'normal', 'pending', "
                "CURRENT_TIMESTAMP, 0), "
                "('upper', CURRENT_TIMESTAMP, 'test', 'restart', '{}', 'CRITICAL', 'APPROVED', "
                "CURRENT_TIMESTAMP, 0)"
            )
        )
        await session.commit()

    repo = ApprovalRepository(session_maker)
    lower = await repo.get("lower")
    upper = await repo.get("upper")
    assert lower is not None
    assert lower.severity == ApprovalSeverity.NORMAL
    assert lower.status == ApprovalStatus.PENDING
    assert upper is not None
    assert upper.severity == ApprovalSeverity.CRITICAL
    assert upper.status == ApprovalStatus.APPROVED

    await engine.dispose()


async def test_approval_repository_expire_overdue(tmp_path) -> None:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'state.db'}")
    await create_db_schema(engine)
    session_maker = create_sessionmaker(engine)
    now = datetime.now(UTC)

    repo = ApprovalRepository(session_maker)
    await repo.create(
        Approval(
            id="expired",
            requested_at=now - timedelta(minutes=10),
            case_use="test",
            action_type="old",
            action_payload={},
            expires_at=now - timedelta(seconds=1),
        )
    )
    await repo.create(
        Approval(
            id="fresh",
            requested_at=now,
            case_use="test",
            action_type="new",
            action_payload={},
            expires_at=now + timedelta(minutes=1),
        )
    )
    assert await repo.expire_overdue(now) == 1
    expired = await repo.get("expired")
    fresh = await repo.get("fresh")
    assert expired is not None and expired.status == ApprovalStatus.EXPIRED
    assert fresh is not None and fresh.status == ApprovalStatus.PENDING

    await engine.dispose()
