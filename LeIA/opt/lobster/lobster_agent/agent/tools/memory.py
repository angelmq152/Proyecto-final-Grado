from typing import Protocol, runtime_checkable

from lobster_agent.persistence.models import Decision
from lobster_agent.persistence.repositories import DecisionRepository


class DecisionReader(Protocol):
    async def list_recent(self, limit: int = 10) -> list[Decision]: ...


@runtime_checkable
class SearchableDecisionReader(DecisionReader, Protocol):
    async def search(self, query: str, limit: int = 10) -> list[Decision]: ...


async def get_recent_decisions(
    repo: DecisionRepository | DecisionReader,
    limit: int = 5,
) -> list[Decision]:
    return await repo.list_recent(limit)


async def search_history(
    repo: DecisionRepository | DecisionReader,
    query: str,
    limit: int = 10,
) -> list[Decision]:
    if isinstance(repo, SearchableDecisionReader):
        return await repo.search(query, limit)

    normalized_query = query.casefold()
    recent = await repo.list_recent(limit=50)
    matches = [
        decision
        for decision in recent
        if normalized_query in decision.prompt_summary.casefold()
        or normalized_query in decision.conclusion.casefold()
    ]
    return matches[:limit]


async def get_recent_errors() -> list[object]:
    # TODO: Wire this to EventRepository once Fase 6/7 event storage is stable.
    return []


async def get_pending_approvals() -> list[object]:
    # TODO: Wire this to approvals/actions repositories in Fase 4.
    return []
