from collections.abc import Awaitable, Callable

from lobster_agent.persistence.repositories import ConversationRepository

ConversationRepoFactory = Callable[[], Awaitable[ConversationRepository]]


class ConversationMemory:
    MAX_TURNS = 20

    def __init__(self, repo_factory: ConversationRepoFactory, max_turns: int = MAX_TURNS) -> None:
        self._cache: dict[int, list[tuple[str, str]]] = {}
        self._repo_factory = repo_factory
        self._max_turns = max_turns

    async def warm_up(self, chat_id: int) -> None:
        """Load last N turns from SQLite into RAM on first access; no-op if already cached."""
        if chat_id in self._cache:
            return
        repo = await self._repo_factory()
        turns = await repo.load_recent(chat_id, self._max_turns)
        self._cache[chat_id] = [(t.role, t.content) for t in turns]

    async def append(self, chat_id: int, role: str, content: str, case_use: str) -> None:
        """Add turn to RAM and persist to SQLite. RAM is trimmed to max_turns; SQLite keeps all."""
        if chat_id not in self._cache:
            self._cache[chat_id] = []
        self._cache[chat_id].append((role, content))
        if len(self._cache[chat_id]) > self._max_turns:
            self._cache[chat_id] = self._cache[chat_id][-self._max_turns :]
        repo = await self._repo_factory()
        await repo.append(chat_id, role, content, case_use)

    def get_history(self, chat_id: int) -> list[tuple[str, str]]:
        """Return current RAM history for this chat (oldest first)."""
        return list(self._cache.get(chat_id, []))

    async def clear(self, chat_id: int) -> None:
        """Clear RAM and SQLite for this chat."""
        self._cache.pop(chat_id, None)
        repo = await self._repo_factory()
        await repo.clear(chat_id)
