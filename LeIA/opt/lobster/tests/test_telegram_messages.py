from datetime import UTC, datetime, timedelta

from lobster_agent.persistence.models import Approval, ApprovalSeverity
from lobster_agent.telegram.messages import format_approval_request


def _make_approval(**kwargs: object) -> Approval:
    defaults: dict[str, object] = dict(
        id="abcdef123456",
        requested_at=datetime.now(UTC),
        case_use="conversation",
        action_type="restart_pod",
        action_payload={"namespace": "tenant-x"},
        tenant_namespace="tenant-x",
        severity=ApprovalSeverity.NORMAL,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    defaults.update(kwargs)
    return Approval(**defaults)  # type: ignore[arg-type]


def test_telegram_message_contains_key_fields() -> None:
    approval = Approval(
        id="abcdef123456",
        requested_at=datetime.now(UTC),
        case_use="conversation",
        action_type="restart_pod",
        action_payload={"namespace": "tenant-x"},
        tenant_namespace="tenant-x",
        severity=ApprovalSeverity.CRITICAL,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )

    message = format_approval_request(approval)
    # Key content is present (MarkdownV2 format, not HTML)
    assert "restart" in message
    assert "abcdef12" in message
    # Short ID is wrapped in inline code (backticks)
    assert "`abcdef12`" in message
    # No HTML tags in output
    assert "<code>" not in message
    assert "<b>" not in message
    assert len(message) < 2200


def test_telegram_message_truncates_large_payload() -> None:
    approval = Approval(
        id="abcdef123456",
        requested_at=datetime.now(UTC),
        case_use="conversation",
        action_type="restart_pod",
        action_payload={"long": "x" * 2000},
        tenant_namespace="tenant-x",
        severity=ApprovalSeverity.NORMAL,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    message = format_approval_request(approval)
    assert len(message) < 2200
    assert "…" in message


def test_format_approval_request_naive_expires_at() -> None:
    """Naive datetime from SQLite must not raise TypeError."""
    naive_expires = datetime.utcnow() + timedelta(minutes=5)  # no tzinfo
    assert naive_expires.tzinfo is None
    approval = _make_approval(expires_at=naive_expires)

    msg = format_approval_request(approval)
    # _pod → \_pod in MarkdownV2, so check for the prefix
    assert "restart" in msg
    # minutes must be a non-negative integer in the output
    # parens are escaped in MarkdownV2 so match without them
    import re

    m = re.search(r"(\d+) min", msg)
    assert m is not None
    assert int(m.group(1)) >= 0


def test_format_approval_request_aware_expires_at() -> None:
    """Aware UTC datetime must produce the same non-negative minutes as the naive equivalent."""
    base = datetime.now(UTC) + timedelta(minutes=5)
    naive = base.replace(tzinfo=None)

    msg_aware = format_approval_request(_make_approval(expires_at=base))
    msg_naive = format_approval_request(_make_approval(expires_at=naive))

    import re

    # parens are escaped in MarkdownV2 so match without them
    minutes_aware = int(re.search(r"(\d+) min", msg_aware).group(1))  # type: ignore[union-attr]
    minutes_naive = int(re.search(r"(\d+) min", msg_naive).group(1))  # type: ignore[union-attr]
    # Both should give the same minute count (possibly off by 1 due to clock ticks, allow ±1)
    assert abs(minutes_aware - minutes_naive) <= 1
    assert minutes_aware >= 0


def test_format_approval_request_none_expires_at() -> None:
    """None expires_at must not raise and must include 'sin caducidad'."""
    approval = _make_approval(expires_at=None)  # type: ignore[arg-type]
    msg = format_approval_request(approval)
    assert "sin caducidad" in msg
    assert "∞" in msg


def test_format_approval_request_already_expired() -> None:
    """An already-expired approval must show 0 minutes, not a negative number."""
    past = datetime.now(UTC) - timedelta(hours=1)
    approval = _make_approval(expires_at=past)

    msg = format_approval_request(approval)

    import re

    # parens are escaped in MarkdownV2 so match without them
    m = re.search(r"(\d+) min", msg)
    assert m is not None
    assert int(m.group(1)) == 0
