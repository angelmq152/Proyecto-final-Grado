import json
from datetime import datetime

from lobster_agent.persistence.models import Approval, ApprovalSeverity, ApprovalStatus
from lobster_agent.telegram.formatting import bold, code, esc, italic, pre
from lobster_agent.utils.dt import ensure_aware_utc, utc_now

PAYLOAD_LIMIT = 1500

_SEVERITY_EMOJI = {
    ApprovalSeverity.NORMAL.value: "⚠️",
    ApprovalSeverity.CRITICAL.value: "🚨",
}

_STATUS_EMOJI = {
    ApprovalStatus.APPROVED: "✅",
    ApprovalStatus.REJECTED: "❌",
    ApprovalStatus.EXPIRED: "⌛",
    ApprovalStatus.CANCELLED: "🚫",
    ApprovalStatus.PENDING: "⏳",
}

_STATUS_LABELS = {
    ApprovalStatus.APPROVED: "Aprobada",
    ApprovalStatus.REJECTED: "Rechazada",
    ApprovalStatus.EXPIRED: "Expirada",
    ApprovalStatus.CANCELLED: "Cancelada",
    ApprovalStatus.PENDING: "Pendiente",
}


def _fmt_expires(expires_at: datetime | None) -> tuple[str, str]:
    """Return (human-readable expiry, minutes-remaining string).

    Handles naive datetimes from SQLite by treating them as UTC.
    Returns ("sin caducidad", "∞") when expires_at is None.
    minutes is clamped to 0 — never negative.
    """
    if expires_at is None:
        return ("sin caducidad", "∞")
    aware = ensure_aware_utc(expires_at)
    minutes = max(0, int((aware - utc_now()).total_seconds() // 60))
    return (aware.isoformat(), str(minutes))


def format_approval_request(approval: Approval) -> str:
    payload = json.dumps(approval.action_payload, ensure_ascii=False, indent=2, sort_keys=True)
    payload = _truncate(payload, PAYLOAD_LIMIT)
    expires_human, minutes_str = _fmt_expires(approval.expires_at)
    tenant = approval.tenant_namespace or "—"
    sev_emoji = _SEVERITY_EMOJI.get(approval.severity.value, "⚠️")

    return (
        f"🔔 {bold('Solicitud de aprobación')} {sev_emoji}\n\n"
        f"⚡ {bold('Acción:')} {esc(approval.action_type)}\n"
        f"🏷️ {bold('Caso de uso:')} {esc(approval.case_use)}\n"
        f"🏠 {bold('Tenant:')} {esc(tenant)}\n\n"
        f"📋 {bold('Detalle:')}\n{pre(payload)}\n\n"
        f"⏰ {italic(f'Caduca: {expires_human} ({minutes_str} min)')}\n"
        f"🆔 {code(short_id(approval.id))}"
    )


def format_approval_resolved(approval: Approval, username: str | None = None) -> str:
    emoji = _STATUS_EMOJI[approval.status]
    label = _STATUS_LABELS[approval.status]
    actor = f"@{username}" if username else str(approval.decided_by_user_id or "lobster")
    decided_at = approval.decided_at.isoformat() if approval.decided_at else "—"
    reason = (
        f"\n🗒️ {bold('Motivo:')} {esc(approval.decision_reason)}" if approval.decision_reason else ""
    )
    return (
        f"{emoji} {bold(label)} · {esc(approval.action_type)}\n"
        f"👤 {bold('Por:')} {esc(actor)}\n"
        f"🕐 {bold('A las:')} {esc(decided_at)}"
        f"{reason}"
    )


def format_pending_line(approval: Approval, now: datetime | None = None) -> str:
    _now = now if now is not None else utc_now()
    age_seconds = max(0, int((_now - ensure_aware_utc(approval.requested_at)).total_seconds()))
    sev_emoji = _SEVERITY_EMOJI.get(approval.severity.value, "⚠️")
    return (
        f"{sev_emoji} {code(short_id(approval.id))} "
        f"{esc(approval.action_type)} "
        f"{italic(approval.severity.value)} "
        f"{esc(f'age={age_seconds}s')}"
    )


def short_id(approval_id: str) -> str:
    return approval_id[:8]


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "…"
