from __future__ import annotations

import json

import structlog
from pydantic_ai import RunContext

from lobster_agent.agent.deps import AgentDeps
from lobster_agent.persistence.models import ToolRequest
from lobster_agent.telegram.formatting import bold, code, esc

log = structlog.get_logger()


async def request_new_tool(
    ctx: RunContext[AgentDeps],
    tool_name_suggested: str,
    description: str,
    suggested_inputs: list[str],
    user_query: str = "",
) -> str:
    """Register a gap in the agent's toolset and notify the operator."""
    deps = ctx.deps
    if deps.tool_request_repo_factory is None or deps.notifier is None:
        return "Tool request capability not available."

    repo = await deps.tool_request_repo_factory()
    tool_request = ToolRequest(
        case_use=deps.current_case_use,
        user_query=user_query[:500],
        tool_name_suggested=tool_name_suggested,
        description=description,
        suggested_inputs=json.dumps(suggested_inputs),
    )
    tool_request = await repo.create(tool_request)

    await deps.notifier.send_to_admin(
        f"🔧 {bold('Nueva solicitud de herramienta:')} {code(tool_name_suggested)}"
        f"\n{esc(description)}"
    )
    log.info(
        "lobster.tool_request.created",
        id=tool_request.id,
        tool_name=tool_name_suggested,
    )
    return f"Solicitud registrada (id={tool_request.id}). El operador será notificado."
