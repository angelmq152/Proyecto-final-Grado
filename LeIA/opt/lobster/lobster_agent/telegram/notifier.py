from typing import Any

import structlog
from aiogram import Bot
from aiogram.enums import ParseMode

from lobster_agent.config import Settings
from lobster_agent.persistence.models import Approval
from lobster_agent.telegram.formatting import code, esc
from lobster_agent.telegram.keyboards import approval_keyboard
from lobster_agent.telegram.messages import (
    format_approval_request,
    format_approval_resolved,
    short_id,
)

log = structlog.get_logger()

_MDV2 = ParseMode.MARKDOWN_V2


class TelegramNotifier:
    def __init__(self, settings: Settings, bot: Bot | None = None) -> None:
        self.settings = settings
        self.bot = bot

    @property
    def enabled(self) -> bool:
        return self.settings.telegram.enabled and self.bot is not None

    async def post_approval_request(self, approval: Approval) -> tuple[int, int]:
        if not self.enabled or not self.settings.telegram.allowed_user_ids:
            log.info("lobster.telegram.approval_stubbed", approval_id=approval.id)
            return (0, 0)
        chat_id = self.settings.telegram.allowed_user_ids[0]
        message = await self.bot.send_message(  # type: ignore[union-attr]
            chat_id,
            format_approval_request(approval),
            parse_mode=_MDV2,
            reply_markup=approval_keyboard(approval.id),
        )
        return (int(message.chat.id), int(message.message_id))

    async def update_approval_message(self, approval: Approval) -> None:
        if not self.enabled or not approval.telegram_chat_id or not approval.telegram_message_id:
            log.info("lobster.telegram.update_stubbed", approval_id=approval.id)
            return
        await self.bot.edit_message_text(  # type: ignore[union-attr]
            format_approval_resolved(approval),
            chat_id=approval.telegram_chat_id,
            message_id=approval.telegram_message_id,
            parse_mode=_MDV2,
            reply_markup=None,
        )

    async def send_reminder(self, approval: Approval) -> None:
        await self.send_to_admin(
            f"⏰ Recordatorio: aprobación {code(short_id(approval.id))} sigue pendiente\\."
        )

    async def send_alert(self, text: str) -> None:
        if not self.enabled:
            log.info("lobster.telegram.alert_stubbed")
            return
        for user_id in self.settings.telegram.allowed_user_ids:
            await self.bot.send_message(user_id, esc(text), parse_mode=_MDV2)  # type: ignore[union-attr]

    async def send_to_admin(self, text: str) -> None:
        if not self.enabled or not self.settings.telegram.allowed_user_ids:
            log.info("lobster.telegram.admin_message_stubbed")
            return
        await self.bot.send_message(  # type: ignore[union-attr]
            self.settings.telegram.allowed_user_ids[0],
            text,
            parse_mode=_MDV2,
        )


class FakeTelegramNotifier(TelegramNotifier):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings, None)
        self.calls: list[tuple[str, Any]] = []

    async def post_approval_request(self, approval: Approval) -> tuple[int, int]:
        self.calls.append(("post_approval_request", approval.id))
        return (0, 0)

    async def update_approval_message(self, approval: Approval) -> None:
        self.calls.append(("update_approval_message", approval.id))

    async def send_reminder(self, approval: Approval) -> None:
        self.calls.append(("send_reminder", approval.id))

    async def send_alert(self, text: str) -> None:
        self.calls.append(("send_alert", text))

    async def send_to_admin(self, text: str) -> None:
        self.calls.append(("send_to_admin", text))
