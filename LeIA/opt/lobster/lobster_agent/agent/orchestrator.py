from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import structlog
from pydantic_ai import Agent, Tool
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from lobster_agent.agent.deps import AgentDeps
from lobster_agent.agent.mutations import MutationContext
from lobster_agent.agent.prompts import build_system_prompt
from lobster_agent.agent.routing import CaseUse, select_model, use_think_mode
from lobster_agent.agent.tools import reading
from lobster_agent.agent.tools.dummy import echo, get_time, simple_calc
from lobster_agent.agent.tools.meta import request_new_tool
from lobster_agent.agent.tools.mutations import (
    apply_manifest,
    cordon_node,
    delete_pod_persistent,
    delete_tenant,
    deploy_tenant,
    pause_tenant,
    pin_deployment_to_node,
    restart_deployment,
    restart_pod,
    resume_tenant,
    scale_deployment,
    uncordon_node,
    unpin_deployment_from_node,
    update_configmap,
    verify_tenant_health,
)
from lobster_agent.config import Settings
from lobster_agent.domain import policy
from lobster_agent.observability.metrics import (
    lobster_decisions_total,
    lobster_errors_total,
    lobster_llm_latency_seconds,
    lobster_llm_tokens_total,
)
from lobster_agent.persistence.db import create_db_engine, create_db_schema, create_sessionmaker
from lobster_agent.persistence.models import AgentMode, Decision
from lobster_agent.persistence.repositories import DecisionRepository

log = structlog.get_logger()


@dataclass(frozen=True)
class AgentResult:
    decision_id: UUID
    outcome: str
    data: str | None = None
    error: str | None = None


class LobsterAgent:
    def __init__(
        self,
        settings: Settings,
        deps: AgentDeps | None = None,
        model_factory: Callable[[str, bool], Any] | None = None,
        no_tools: bool = False,
    ) -> None:
        self.settings = settings
        self.deps = deps
        self._model_factory = model_factory
        self._no_tools = no_tools
        self._agents: dict[tuple[str, str, bool], Agent[AgentDeps, str]] = {}
        self._engine = create_db_engine(settings.database.url)
        self._session_maker = create_sessionmaker(self._engine)
        if (
            self.deps is not None
            and self.deps.mutation_context is None
            and self.deps.action_repo_factory is not None
        ):
            self.deps.mutation_context = MutationContext(
                self.deps.action_repo_factory,
                self.deps.approval_manager,
                policy,
                self.deps.notifier,
                settings.agent.dry_run_default,
                settings.agent.enforce_resource_limits,
            )

    async def initialize(self) -> None:
        await create_db_schema(self._engine)

    async def close(self) -> None:
        await self._engine.dispose()

    def _build_model(self, model_name: str, think: bool) -> OpenAIChatModel:
        provider = OpenAIProvider(
            base_url=self.settings.ollama.base_url,
            api_key=self.settings.ollama.api_key,
        )
        # think=True (Qwen3 /think) can stream for 10+ minutes; no read timeout.
        # qwen3:32b sin think todavía tarda varios minutos por request (>180s).
        # Le damos margen para pensar (15 min) aunque no use think mode.
        # Modelos pequeños (8b) usan el timeout corto de config (~180s).
        timeout: float | httpx.Timeout
        if think:
            timeout = httpx.Timeout(None, connect=30.0)
        elif "32b" in model_name:
            timeout = max(self.settings.ollama.timeout_seconds, 900.0)
        else:
            timeout = self.settings.ollama.timeout_seconds
        settings = ModelSettings(
            timeout=timeout,
            extra_body={"think": think},
        )
        return OpenAIChatModel(model_name, provider=provider, settings=settings)

    def _get_agent(
        self,
        case_use: CaseUse,
        model_name: str,
        think: bool,
        system_prompt: str,
    ) -> Agent[AgentDeps, str]:
        cache_key = (case_use.value, model_name, think)
        if cache_key not in self._agents:
            model = (
                self._model_factory(model_name, think)
                if self._model_factory is not None
                else self._build_model(model_name, think)
            )
            self._agents[cache_key] = Agent(
                model,
                output_type=str,
                deps_type=AgentDeps,
                tools=_build_tools_for_case(
                    case_use,
                    self.deps,
                    enable_dummy_tools=self.settings.agent.enable_dummy_tools,
                    no_tools=self._no_tools,
                ),
                tool_retries=1,
                output_retries=1,
            )
        return self._agents[cache_key]

    async def run(
        self,
        case_use: CaseUse,
        user_input: str,
        context: dict[str, object] | None = None,
        message_history: list[tuple[str, str]] | None = None,
    ) -> AgentResult:
        await self.initialize()
        started_at = datetime.now(UTC)
        model_name = select_model(case_use)
        think = use_think_mode(case_use)
        if self.deps is not None and self.deps.agent_state_repo_factory is not None:
            state_repo = await self.deps.agent_state_repo_factory()
            state = await state_repo.get()
            if self.deps.mutation_context is not None:
                self.deps.mutation_context.set_dry_run(state.mode == AgentMode.DRY_RUN)
            context = {**(context or {}), "agent_mode": state.mode.value}

            if state.mode == AgentMode.PAUSED:
                decision = Decision(
                    timestamp=started_at,
                    case_use=case_use.value,
                    model_used=model_name,
                    think_mode=think,
                    prompt_summary=user_input[:500],
                    reasoning=None,
                    conclusion="Agent paused; LLM cycle skipped.",
                    tokens_input=0,
                    tokens_output=0,
                    tools_called=[],
                    latency_ms=0,
                )
                repo = DecisionRepository(self._session_maker)
                decision = await repo.save(decision)
                self._record_metrics(case_use, model_name, think, "skipped_paused", 0, 0, 0)
                return AgentResult(
                    decision_id=decision.id,
                    outcome="skipped_paused",
                    data=decision.conclusion,
                    error=None,
                )

        system_prompt = build_system_prompt(case_use, context)

        if self.deps is not None:
            self.deps.current_case_use = case_use.value

        outcome = "success"
        output: str | None = None
        error: str | None = None
        tokens_input = 0
        tokens_output = 0

        try:
            agent = self._get_agent(case_use, model_name, think, system_prompt)
            history: Sequence[ModelMessage] | None = (
                _build_message_history(message_history) if message_history is not None else None
            )
            if self.deps is None:
                result = await agent.run(
                    user_input, instructions=system_prompt, message_history=history
                )
            else:
                result = await agent.run(
                    user_input,
                    instructions=system_prompt,
                    deps=self.deps,
                    message_history=history,
                )
            output = str(result.output)
            usage = result.usage()
            tokens_input = usage.input_tokens or 0
            tokens_output = usage.output_tokens or 0
            tools_called = _tools_called_from_messages(result.all_messages())
        except Exception as exc:
            outcome = "failed"
            error = str(exc)
            output = error
            tools_called = []
            lobster_errors_total.labels(component="agent", severity="error").inc()

        latency_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)

        decision = Decision(
            timestamp=started_at,
            case_use=case_use.value,
            model_used=model_name,
            think_mode=think,
            prompt_summary=user_input[:500],
            reasoning=None,
            conclusion=output or "",
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            tools_called=tools_called,
            latency_ms=latency_ms,
        )
        repo = DecisionRepository(self._session_maker)
        decision = await repo.save(decision)

        self._record_metrics(
            case_use,
            model_name,
            think,
            outcome,
            tokens_input,
            tokens_output,
            latency_ms,
        )
        log.info(
            "lobster.decision.completed",
            decision_id=str(decision.id),
            case_use=case_use.value,
            model=model_name,
            think_mode=think,
            outcome=outcome,
            latency_ms=latency_ms,
            conclusion=output[:800] if output else None,
        )
        return AgentResult(decision_id=decision.id, outcome=outcome, data=output, error=error)

    def _record_metrics(
        self,
        case_use: CaseUse,
        model_name: str,
        think: bool,
        outcome: str,
        tokens_input: int,
        tokens_output: int,
        latency_ms: int,
    ) -> None:
        labels = {
            "case_use": case_use.value,
            "model": model_name,
        }
        lobster_decisions_total.labels(
            case_use=case_use.value,
            model=model_name,
            think=str(think).lower(),
            outcome=outcome,
        ).inc()
        lobster_llm_latency_seconds.labels(**labels).observe(latency_ms / 1000)
        lobster_llm_tokens_total.labels(**labels, direction="input").inc(tokens_input)
        lobster_llm_tokens_total.labels(**labels, direction="output").inc(tokens_output)


def result_to_dict(result: AgentResult) -> dict[str, Any]:
    return {
        "decision_id": str(result.decision_id),
        "outcome": result.outcome,
        "data": result.data,
        "error": result.error,
    }


def _build_tools_for_case(
    case_use: CaseUse,
    deps: AgentDeps | None,
    *,
    enable_dummy_tools: bool = False,
    no_tools: bool = False,
) -> list[Tool[AgentDeps] | Callable[..., Any]]:
    if no_tools or case_use == CaseUse.SMOKE_TEST or enable_dummy_tools or deps is None:
        return [get_time, echo, simple_calc]

    meta_tools: list[Tool[AgentDeps] | Callable[..., Any]] = [request_new_tool]
    memory_tools: list[Tool[AgentDeps] | Callable[..., Any]] = [
        reading.search_decisions,
        reading.get_decision,
    ]
    prometheus_tools: list[Tool[AgentDeps] | Callable[..., Any]] = [
        reading.query_prometheus_instant,
        reading.query_prometheus_range,
        reading.get_node_health,
    ]
    loki_tools: list[Tool[AgentDeps] | Callable[..., Any]] = [
        reading.query_loki_logs,
        reading.get_recent_errors,
    ]
    k8s_basic_tools: list[Tool[AgentDeps] | Callable[..., Any]] = [
        reading.list_pods,
        reading.get_pod,
        reading.list_deployments,
        reading.list_ingresses,
        reading.list_recent_events,
        reading.list_namespaces,
        reading.is_node_alive,
    ]
    alertmanager_tools: list[Tool[AgentDeps] | Callable[..., Any]] = [
        reading.list_active_alerts,
        reading.get_alert_details,
    ]
    mutation_tools: list[Tool[AgentDeps] | Callable[..., Any]] = [
        restart_pod,
        restart_deployment,
        scale_deployment,
        delete_pod_persistent,
        apply_manifest,
        update_configmap,
        deploy_tenant,
        delete_tenant,
        pause_tenant,
        resume_tenant,
        verify_tenant_health,
        pin_deployment_to_node,
        unpin_deployment_from_node,
        cordon_node,
        uncordon_node,
    ]
    all_tools = (
        meta_tools
        + memory_tools
        + prometheus_tools
        + loki_tools
        + k8s_basic_tools
        + alertmanager_tools
        + mutation_tools
    )

    return {
        CaseUse.SUMMARY: meta_tools + memory_tools + [reading.list_active_alerts],
        CaseUse.BACKUP: meta_tools + memory_tools + k8s_basic_tools,
        CaseUse.GLOBAL_STATE: meta_tools
        + prometheus_tools
        + alertmanager_tools
        + k8s_basic_tools
        + memory_tools,
        CaseUse.OPTIMIZATION: meta_tools
        + prometheus_tools
        + k8s_basic_tools
        + memory_tools
        + mutation_tools,
        CaseUse.HEALTH_LOOP_READ: meta_tools
        + prometheus_tools
        + alertmanager_tools
        + k8s_basic_tools
        + memory_tools,
        CaseUse.HEALTH_LOOP_ANALYZE: meta_tools
        + prometheus_tools
        + alertmanager_tools
        + k8s_basic_tools
        + loki_tools
        + memory_tools
        + mutation_tools,
        CaseUse.CONVERSATION: all_tools,
        CaseUse.CHAT: all_tools,
        CaseUse.THINK: all_tools,
        CaseUse.DIAGNOSE: all_tools,
        CaseUse.DAILY_SUMMARY: meta_tools
        + prometheus_tools
        + loki_tools
        + k8s_basic_tools
        + alertmanager_tools
        + memory_tools,
        CaseUse.ONBOARDING: meta_tools + k8s_basic_tools + memory_tools + mutation_tools,
        CaseUse.ALERT_REACTIVE: meta_tools
        + alertmanager_tools
        + prometheus_tools
        + loki_tools
        + k8s_basic_tools
        + memory_tools
        + mutation_tools,
    }.get(case_use, meta_tools + memory_tools)


def _build_message_history(turns: list[tuple[str, str]]) -> list[ModelMessage]:
    messages: list[ModelMessage] = []
    for role, content in turns:
        if role == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        else:
            messages.append(ModelResponse(parts=[TextPart(content=content)]))
    return messages


def _tools_called_from_messages(messages: Sequence[object]) -> list[str]:
    tools: list[str] = []
    for message in messages:
        parts = getattr(message, "parts", [])
        for part in parts:
            if isinstance(part, ToolCallPart) and part.tool_name not in tools:
                tools.append(part.tool_name)
    return tools
