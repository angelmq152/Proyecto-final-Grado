import asyncio
from contextlib import suppress

import structlog
from aiogram import Bot, Dispatcher

from lobster_agent.agent.approvals import AgentStateRepoFactory
from lobster_agent.agent.orchestrator import LobsterAgent
from lobster_agent.config import Settings
from lobster_agent.telegram.handlers import (
    ApprovalRepoFactory,
    ToolRequestRepoFactory,
    build_router,
)
from lobster_agent.telegram.memory import ConversationMemory
from lobster_agent.telegram.notifier import TelegramNotifier

log = structlog.get_logger()


class TelegramBotRunner:
    def __init__(
        self,
        settings: Settings,
        approval_repo_factory: ApprovalRepoFactory,
        agent_state_repo_factory: AgentStateRepoFactory,
        notifier: TelegramNotifier,
        agent: LobsterAgent,
        memory: ConversationMemory,
        tool_request_repo_factory: ToolRequestRepoFactory | None = None,
    ) -> None:
        self.settings = settings
        self.approval_repo_factory = approval_repo_factory
        self.agent_state_repo_factory = agent_state_repo_factory
        self.notifier = notifier
        self.agent = agent
        self.memory = memory
        self.tool_request_repo_factory = tool_request_repo_factory
        self.bot: Bot | None = None
        self.dispatcher: Dispatcher | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if not self.settings.telegram.enabled:
            log.info("lobster.telegram.disabled")
            return
        if not self.settings.telegram.bot_token:
            log.warning("lobster.telegram.enabled_without_token")
            return
        self.bot = self.notifier.bot or Bot(self.settings.telegram.bot_token)
        self.notifier.bot = self.bot
        self.dispatcher = Dispatcher(
            settings=self.settings,
            approval_repo_factory=self.approval_repo_factory,
            agent_state_repo_factory=self.agent_state_repo_factory,
            notifier=self.notifier,
            agent=self.agent,
            memory=self.memory,
            tool_request_repo_factory=self.tool_request_repo_factory,
        )
        self.dispatcher.include_router(build_router())
        self._task = asyncio.create_task(self._poll(), name="lobster-telegram-polling")
        self._task.add_done_callback(self._log_polling_result)

    async def stop(self) -> None:
        if self.dispatcher is not None:
            with suppress(RuntimeError, TimeoutError):
                await asyncio.wait_for(self.dispatcher.stop_polling(), timeout=10)
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        if self._task is not None and self._task.done():
            with suppress(asyncio.CancelledError):
                self._task.result()
            self._task = None
        if self.bot is not None:
            await self.bot.session.close()

    async def _poll(self) -> None:
        if self.dispatcher is None or self.bot is None:
            return
        try:
            await self.dispatcher.start_polling(
                self.bot,
                polling_timeout=self.settings.telegram.polling_timeout_seconds,
                handle_signals=False,
                close_bot_session=False,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("lobster.telegram.polling_failed", error=str(exc))

    def _log_polling_result(self, task: asyncio.Task[None]) -> None:
        with suppress(asyncio.CancelledError):
            exc = task.exception()
            if exc is not None:
                log.warning("lobster.telegram.polling_task_failed", error=str(exc))
