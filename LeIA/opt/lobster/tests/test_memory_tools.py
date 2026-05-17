from lobster_agent.agent.tools.memory import (
    get_pending_approvals,
    get_recent_decisions,
    get_recent_errors,
    search_history,
)
from lobster_agent.persistence.models import Decision


class FakeDecisionRepository:
    def __init__(self, decisions: list[Decision]) -> None:
        self.decisions = decisions
        self.list_recent_limits: list[int] = []

    async def list_recent(self, limit: int = 10) -> list[Decision]:
        self.list_recent_limits.append(limit)
        return self.decisions[:limit]


async def test_get_recent_decisions_calls_list_recent() -> None:
    decision = Decision(
        case_use="conversation",
        model_used="qwen3:32b",
        think_mode=True,
        prompt_summary="hola",
        conclusion="ok",
    )
    repo = FakeDecisionRepository([decision])

    result = await get_recent_decisions(repo, limit=1)

    assert result == [decision]
    assert repo.list_recent_limits == [1]


async def test_search_history_filters_prompt_summary_and_conclusion() -> None:
    matching_prompt = Decision(
        case_use="diagnose",
        model_used="qwen3:32b",
        think_mode=True,
        prompt_summary="error en wordpress",
        conclusion="revisar logs",
    )
    matching_conclusion = Decision(
        case_use="summary",
        model_used="qwen3:8b",
        think_mode=False,
        prompt_summary="estado",
        conclusion="wordpress estable",
    )
    non_matching = Decision(
        case_use="summary",
        model_used="qwen3:8b",
        think_mode=False,
        prompt_summary="estado",
        conclusion="todo bien",
    )
    repo = FakeDecisionRepository([matching_prompt, matching_conclusion, non_matching])

    result = await search_history(repo, "WORDPRESS", limit=10)

    assert result == [matching_prompt, matching_conclusion]
    assert repo.list_recent_limits == [50]


async def test_get_pending_approvals_returns_empty_list() -> None:
    assert await get_pending_approvals() == []


async def test_get_recent_errors_returns_empty_list() -> None:
    assert await get_recent_errors() == []
