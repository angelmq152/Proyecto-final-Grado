import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any, cast

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from lobster_agent.agent.approvals import AgentStateRepoFactory
from lobster_agent.agent.orchestrator import LobsterAgent
from lobster_agent.agent.routing import CaseUse
from lobster_agent.config import Settings
from lobster_agent.persistence.models import AgentMode, Approval, ApprovalStatus
from lobster_agent.persistence.repositories import ApprovalRepository, ToolRequestRepository
from lobster_agent.telegram.formatting import code, esc, md_to_mdv2
from lobster_agent.telegram.guards import is_allowed
from lobster_agent.telegram.memory import ConversationMemory
from lobster_agent.telegram.messages import (
    format_approval_request,
    format_approval_resolved,
    format_pending_line,
)
from lobster_agent.telegram.notifier import TelegramNotifier

ApprovalRepoFactory = Callable[[], Awaitable[ApprovalRepository]]
ToolRequestRepoFactory = Callable[[], Awaitable[ToolRequestRepository]]

_MDV2 = ParseMode.MARKDOWN_V2

_MODE_EMOJI = {
    AgentMode.NORMAL.value: "🟢",
    AgentMode.DRY_RUN.value: "🟡",
    AgentMode.PAUSED.value: "🔴",
}


def build_router() -> Router:
    router = Router()
    router.message.register(handle_start, Command("start"))
    router.message.register(handle_help, Command("help"))
    router.message.register(handle_status, Command("status"))
    router.message.register(handle_pending, Command("pending"))
    router.message.register(handle_show, Command("show"))
    router.message.register(handle_pause, Command("pause"))
    router.message.register(handle_resume, Command("resume"))
    router.message.register(handle_kill, Command("kill"))
    router.message.register(handle_think, Command("think"))
    router.message.register(handle_forget, Command("forget"))
    router.message.register(handle_toolrequests, Command("toolrequests"))
    router.callback_query.register(handle_approve_callback, lambda c: c.data.startswith("approve:"))
    router.callback_query.register(handle_reject_callback, lambda c: c.data.startswith("reject:"))
    router.callback_query.register(handle_pause_all_callback, lambda c: c.data == "pause_all")
    router.message.register(handle_free_text, F.text)
    return router


async def handle_start(message: Message, settings: Settings, **_: object) -> None:
    if not is_allowed(message, settings):
        return
    await message.answer(
        esc("🤖 Lobster activo. Usa /status, /pending, /pause, /resume o /kill."),
        parse_mode=_MDV2,
    )


async def handle_help(message: Message, settings: Settings, **_: object) -> None:
    if not is_allowed(message, settings):
        return
    await message.answer(
        "📖 *Comandos disponibles:*\n\n"
        "/status — estado del agente\n"
        "/pending — aprobaciones pendientes\n"
        "/show \\<id\\> — detalle de una aprobación\n"
        "/pause \\[razón\\] — modo dry\\_run\n"
        "/resume — volver a modo normal\n"
        "/kill \\[razón\\] — pausar completamente\n"
        "/think \\<pregunta\\> — razonamiento profundo\n"
        "/forget — borrar historial del chat\n"
        "/toolrequests — solicitudes de herramientas",
        parse_mode=_MDV2,
    )


async def handle_status(
    message: Message,
    settings: Settings,
    approval_repo_factory: ApprovalRepoFactory,
    agent_state_repo_factory: AgentStateRepoFactory,
    **_: object,
) -> None:
    if not is_allowed(message, settings):
        return
    approval_repo = await approval_repo_factory()
    state_repo = await agent_state_repo_factory()
    state = await state_repo.get()
    pending = await approval_repo.count_pending()
    recent = await approval_repo.list_recent(1)
    last = recent[0].status.value if recent else "none"
    mode_emoji = _MODE_EMOJI.get(state.mode.value, "⚪")
    await message.answer(
        f"{mode_emoji} Modo: {esc(state.mode.value)}\n"
        f"📊 Pendientes: {esc(str(pending))}\n"
        f"🔍 Última decisión: {esc(last)}",
        parse_mode=_MDV2,
    )


async def handle_pending(
    message: Message,
    settings: Settings,
    approval_repo_factory: ApprovalRepoFactory,
    **_: object,
) -> None:
    if not is_allowed(message, settings):
        return
    repo = await approval_repo_factory()
    approvals = await repo.list_pending()
    if not approvals:
        await message.answer(esc("✅ No hay aprobaciones pendientes."), parse_mode=_MDV2)
        return
    await message.answer(
        "\n".join(format_pending_line(approval) for approval in approvals),
        parse_mode=_MDV2,
    )


async def handle_show(
    message: Message,
    settings: Settings,
    approval_repo_factory: ApprovalRepoFactory,
    **_: object,
) -> None:
    if not is_allowed(message, settings):
        return
    approval_id = _command_arg(getattr(message, "text", ""))
    repo = await approval_repo_factory()
    approval = await _find_approval(repo, approval_id)
    if approval is None:
        await message.answer(esc("❌ Aprobación no encontrada."), parse_mode=_MDV2)
        return
    await message.answer(format_approval_request(approval), parse_mode=_MDV2)


async def handle_pause(
    message: Message,
    settings: Settings,
    agent_state_repo_factory: AgentStateRepoFactory,
    notifier: TelegramNotifier,
    **_: object,
) -> None:
    if not is_allowed(message, settings):
        return
    reason = _command_arg(getattr(message, "text", "")) or "telegram_pause"
    repo = await agent_state_repo_factory()
    user = getattr(message, "from_user", None)
    await repo.set_mode(AgentMode.PAUSED, reason, getattr(user, "id", None))
    await message.answer(esc("🔴 Modo cambiado a paused."), parse_mode=_MDV2)
    await notifier.send_alert("🔴 Modo cambiado a paused")


async def handle_resume(
    message: Message,
    settings: Settings,
    agent_state_repo_factory: AgentStateRepoFactory,
    notifier: TelegramNotifier,
    **_: object,
) -> None:
    if not is_allowed(message, settings):
        return
    repo = await agent_state_repo_factory()
    user = getattr(message, "from_user", None)
    await repo.set_mode(AgentMode.NORMAL, None, getattr(user, "id", None))
    await message.answer(esc("🟢 Modo cambiado a normal."), parse_mode=_MDV2)
    await notifier.send_alert("🟢 Modo cambiado a normal")


async def handle_kill(
    message: Message,
    settings: Settings,
    agent_state_repo_factory: AgentStateRepoFactory,
    notifier: TelegramNotifier,
    **_: object,
) -> None:
    if not is_allowed(message, settings):
        return
    reason = _command_arg(getattr(message, "text", "")) or "telegram_kill"
    repo = await agent_state_repo_factory()
    user = getattr(message, "from_user", None)
    await repo.set_mode(AgentMode.PAUSED, reason, getattr(user, "id", None))
    await message.answer(esc("🔴 Modo cambiado a paused."), parse_mode=_MDV2)
    await notifier.send_alert("🔴 Modo cambiado a paused")


async def handle_approve_callback(
    callback: CallbackQuery,
    settings: Settings,
    approval_repo_factory: ApprovalRepoFactory,
    **_: object,
) -> None:
    if not is_allowed(callback, settings):
        return
    approval_id = str(callback.data).split(":", 1)[1]
    repo = await approval_repo_factory()
    approval = await _find_approval(repo, approval_id)
    if approval is None:
        await callback.answer("Aprobación no encontrada", show_alert=False)
        return
    if approval.status != ApprovalStatus.PENDING:
        await callback.answer("Esta aprobación ya estaba resuelta", show_alert=False)
        return
    user = getattr(callback, "from_user", None)
    approval = await repo.update_status(
        approval.id,
        ApprovalStatus.APPROVED,
        getattr(user, "id", None),
        None,
    )
    if approval is not None and callback.message is not None:
        message = cast(Any, callback.message)
        await message.edit_text(
            format_approval_resolved(approval, getattr(user, "username", None)),
            parse_mode=_MDV2,
        )
    await callback.answer("Aprobada", show_alert=False)


async def handle_reject_callback(
    callback: CallbackQuery,
    settings: Settings,
    approval_repo_factory: ApprovalRepoFactory,
    **_: object,
) -> None:
    if not is_allowed(callback, settings):
        return
    approval_id = str(callback.data).split(":", 1)[1]
    repo = await approval_repo_factory()
    approval = await _find_approval(repo, approval_id)
    if approval is None:
        await callback.answer("Aprobación no encontrada", show_alert=False)
        return
    if approval.status != ApprovalStatus.PENDING:
        await callback.answer("Esta aprobación ya estaba resuelta", show_alert=False)
        return
    user = getattr(callback, "from_user", None)
    approval = await repo.update_status(
        approval.id,
        ApprovalStatus.REJECTED,
        getattr(user, "id", None),
        "rejected_from_telegram",
    )
    if approval is not None and callback.message is not None:
        message = cast(Any, callback.message)
        await message.edit_text(
            format_approval_resolved(approval, getattr(user, "username", None)),
            parse_mode=_MDV2,
        )
    await callback.answer("Rechazada", show_alert=False)


async def handle_pause_all_callback(
    callback: CallbackQuery,
    settings: Settings,
    agent_state_repo_factory: AgentStateRepoFactory,
    notifier: TelegramNotifier,
    **_: object,
) -> None:
    if not is_allowed(callback, settings):
        return
    user = getattr(callback, "from_user", None)
    repo = await agent_state_repo_factory()
    await repo.set_mode(AgentMode.DRY_RUN, "telegram_pause_all", getattr(user, "id", None))
    await notifier.send_alert("🟡 Modo cambiado a dry_run")
    await callback.answer("Modo dry_run activo", show_alert=False)


async def handle_think(
    message: Message,
    settings: Settings,
    agent: LobsterAgent,
    memory: ConversationMemory,
    **_: object,
) -> None:
    if not is_allowed(message, settings):
        return
    text = _command_arg(getattr(message, "text", ""))
    if not text:
        await message.answer(esc("Uso: /think <pregunta>"), parse_mode=_MDV2)
        return
    chat_id = _chat_id(message)
    await memory.warm_up(chat_id)
    history = memory.get_history(chat_id)
    placeholder = await message.answer("🧠 Pensando con razonamiento profundo…")
    started = time.monotonic()
    tick_task = asyncio.create_task(_tick_placeholder(placeholder, started))
    result = None
    reply: str
    try:
        result = await agent.run(case_use=CaseUse.THINK, user_input=text, message_history=history)
        reply = md_to_mdv2(result.data or "Sin respuesta\\.")
    except Exception as exc:
        reply = esc(f"⚠️ Error: {exc}")
    finally:
        tick_task.cancel()
        with suppress(asyncio.CancelledError):
            await tick_task
    await placeholder.edit_text(reply, parse_mode=_MDV2)
    if result is not None:
        await memory.append(chat_id, "user", text, CaseUse.THINK.value)
        await memory.append(chat_id, "assistant", result.data or "", CaseUse.THINK.value)


async def handle_free_text(
    message: Message,
    settings: Settings,
    agent: LobsterAgent,
    memory: ConversationMemory,
    **_: object,
) -> None:
    if not is_allowed(message, settings):
        return
    text = getattr(message, "text", "") or ""
    if text.startswith("/"):
        return
    chat_id = _chat_id(message)
    await memory.warm_up(chat_id)
    history = memory.get_history(chat_id)
    placeholder = await message.answer("🤔 Pensando…")
    result = None
    reply: str
    try:
        result = await agent.run(case_use=CaseUse.CHAT, user_input=text, message_history=history)
        reply = md_to_mdv2(result.data or "Sin respuesta\\.")
    except Exception as exc:
        reply = esc(f"⚠️ Error: {exc}")
    await placeholder.edit_text(reply, parse_mode=_MDV2)
    if result is not None:
        await memory.append(chat_id, "user", text, CaseUse.CHAT.value)
        await memory.append(chat_id, "assistant", result.data or "", CaseUse.CHAT.value)


async def handle_toolrequests(
    message: Message,
    settings: Settings,
    tool_request_repo_factory: ToolRequestRepoFactory,
    **_: object,
) -> None:
    if not is_allowed(message, settings):
        return
    repo = await tool_request_repo_factory()
    requests = await repo.list_recent(limit=10, status="pending")
    if not requests:
        await message.answer(
            esc("✅ No hay solicitudes de herramientas pendientes."), parse_mode=_MDV2
        )
        return
    lines = [
        f"🔧 {code(str(req.id))} {esc(req.tool_name_suggested)} — {esc(req.description[:60])}"
        for req in requests
    ]
    await message.answer("\n".join(lines), parse_mode=_MDV2)


async def handle_forget(
    message: Message,
    settings: Settings,
    memory: ConversationMemory,
    **_: object,
) -> None:
    if not is_allowed(message, settings):
        return
    await memory.clear(_chat_id(message))
    await message.answer(esc("🗑️ Memoria borrada."), parse_mode=_MDV2)


async def _tick_placeholder(placeholder: Message, started: float) -> None:
    while True:
        await asyncio.sleep(60)
        elapsed_min = int((time.monotonic() - started) / 60)
        with suppress(Exception):
            await placeholder.edit_text(f"🧠 Pensando… ({elapsed_min} min)")


def _chat_id(message: Message) -> int:
    return message.chat.id


async def _find_approval(repo: ApprovalRepository, approval_id: str | None) -> Approval | None:
    if not approval_id:
        return None
    approval = await repo.get(approval_id)
    if approval is not None:
        return approval
    for candidate in await repo.list_recent(100):
        if candidate.id.startswith(approval_id):
            return candidate
    return None


def _command_arg(text: str) -> str | None:
    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        return None
    return parts[1].strip() or None
