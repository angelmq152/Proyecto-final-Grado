import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

import typer
from aiogram import Bot

from lobster_agent.agent.approvals import ApprovalManager, ApprovalRequest
from lobster_agent.agent.deps import AgentDeps
from lobster_agent.agent.orchestrator import LobsterAgent
from lobster_agent.agent.routing import CaseUse
from lobster_agent.agent.tools.mutations.tenant import (
    delete_tenant,
    deploy_tenant,
    pause_tenant,
    resume_tenant,
    verify_tenant_health,
)
from lobster_agent.clients.alertmanager import AlertmanagerClient
from lobster_agent.clients.k8s import K8sClient
from lobster_agent.clients.loki import LokiClient
from lobster_agent.clients.prometheus import PrometheusClient
from lobster_agent.config import Settings
from lobster_agent.persistence.db import create_db_engine, create_db_schema, create_sessionmaker
from lobster_agent.persistence.models import (
    ActionStatus,
    AgentMode,
    ApprovalSeverity,
    ApprovalStatus,
)
from lobster_agent.persistence.repositories import (
    ActionRepository,
    AgentStateRepository,
    ApprovalRepository,
    DecisionRepository,
    ToolRequestRepository,
)
from lobster_agent.telegram.notifier import TelegramNotifier

app = typer.Typer(help="Lobster manual operator CLI.")
decisions_app = typer.Typer(help="Inspect persisted agent decisions.")
db_app = typer.Typer(help="Database maintenance commands.")
approvals_app = typer.Typer(help="Inspect and create approval requests.")
actions_app = typer.Typer(help="Inspect mutation action ledger entries.")
state_app = typer.Typer(help="Inspect and change agent state.")
tool_requests_app = typer.Typer(help="Inspect agent tool gap requests.")
tenants_app = typer.Typer(help="Manage SaaSphere tenants.")
app.add_typer(decisions_app, name="decisions")
app.add_typer(db_app, name="db")
app.add_typer(approvals_app, name="approvals")
app.add_typer(actions_app, name="actions")
app.add_typer(state_app, name="state")
app.add_typer(tool_requests_app, name="tool-requests")
app.add_typer(tenants_app, name="tenants")


@app.command()
def ask(
    prompt: Annotated[str, typer.Argument(help="Prompt for Lobster.")],
    case: Annotated[
        CaseUse,
        typer.Option("--case", help="Lobster case use."),
    ] = CaseUse.CONVERSATION,
    no_tools: Annotated[
        bool,
        typer.Option("--no-tools", help="Register only dummy debugging tools."),
    ] = False,
) -> None:
    async def _run() -> None:
        settings = Settings()
        deps, cleanup = await _build_agent_deps(settings)
        agent = LobsterAgent(settings, deps=deps, no_tools=no_tools)
        try:
            result = await agent.run(case, prompt)
            if result.data:
                typer.echo(result.data)
            if result.error:
                raise typer.Exit(code=1)
        finally:
            await agent.close()
            await cleanup()

    asyncio.run(_run())


@decisions_app.command("list")
def list_decisions(
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 10,
    show_reasoning: Annotated[bool, typer.Option("--show-reasoning")] = False,
) -> None:
    async def _run() -> None:
        settings = Settings()
        engine = create_db_engine(settings.database.url)
        await create_db_schema(engine)
        session_maker = create_sessionmaker(engine)
        try:
            repo = DecisionRepository(session_maker)
            decisions = await repo.list_recent(limit)
            for decision in decisions:
                typer.echo(
                    f"{decision.timestamp.isoformat()} "
                    f"{decision.id} {decision.case_use} {decision.model_used} "
                    f"think={decision.think_mode} latency_ms={decision.latency_ms}"
                )
                typer.echo(f"  {decision.conclusion}")
                if show_reasoning and decision.reasoning:
                    typer.echo(f"  reasoning: {decision.reasoning}")
        finally:
            await engine.dispose()

    asyncio.run(_run())


@db_app.command("migrate")
def migrate() -> None:
    async def _run() -> None:
        engine = create_db_engine(Settings().database.url)
        try:
            await create_db_schema(engine)
            typer.echo("Database schema is up to date.")
        finally:
            await engine.dispose()

    asyncio.run(_run())


@approvals_app.command("list")
def list_approvals(
    status: Annotated[ApprovalStatus | None, typer.Option("--status")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 20,
) -> None:
    async def _run() -> None:
        settings = Settings()
        engine = create_db_engine(settings.database.url)
        await create_db_schema(engine)
        session_maker = create_sessionmaker(engine)
        try:
            repo = ApprovalRepository(session_maker)
            for approval in await repo.list_recent(limit=limit, status=status):
                typer.echo(
                    f"{approval.requested_at.isoformat()} {approval.id} "
                    f"{approval.status.value} {approval.severity.value} {approval.action_type}"
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


@approvals_app.command("show")
def show_approval(approval_id: str) -> None:
    async def _run() -> None:
        settings = Settings()
        engine = create_db_engine(settings.database.url)
        await create_db_schema(engine)
        session_maker = create_sessionmaker(engine)
        try:
            repo = ApprovalRepository(session_maker)
            approval = await repo.get(approval_id)
            if approval is None:
                typer.echo("Approval not found.", err=True)
                raise typer.Exit(code=1)
            typer.echo(json.dumps(approval.model_dump(mode="json"), indent=2, sort_keys=True))
        finally:
            await engine.dispose()

    asyncio.run(_run())


@approvals_app.command("create-test")
def create_test_approval(
    action_type: Annotated[str, typer.Option("--action-type")],
    severity: Annotated[ApprovalSeverity, typer.Option("--severity")] = ApprovalSeverity.NORMAL,
    payload: Annotated[str, typer.Option("--payload")] = "{}",
) -> None:
    async def _run() -> None:
        settings = Settings()
        engine = create_db_engine(settings.database.url)
        await create_db_schema(engine)
        session_maker = create_sessionmaker(engine)
        approval_repo = ApprovalRepository(session_maker)
        state_repo = AgentStateRepository(session_maker)
        bot = (
            Bot(settings.telegram.bot_token)
            if settings.telegram.enabled and settings.telegram.bot_token
            else None
        )

        async def approval_repo_factory() -> ApprovalRepository:
            return approval_repo

        async def agent_state_repo_factory() -> AgentStateRepository:
            return state_repo

        try:
            parsed_payload = json.loads(payload)
            if not isinstance(parsed_payload, dict):
                raise typer.BadParameter("payload must be a JSON object")
            manager = ApprovalManager(
                approval_repo_factory,
                agent_state_repo_factory,
                TelegramNotifier(settings, bot),
                settings.approval,
            )
            approval = await manager.request_approval(
                ApprovalRequest(
                    case_use="manual_test",
                    action_type=action_type,
                    action_payload=parsed_payload,
                    severity=severity,
                )
            )
            typer.echo(f"{approval.id} {approval.status.value}")
        finally:
            if bot is not None:
                await bot.session.close()
            await engine.dispose()

    asyncio.run(_run())


@actions_app.command("list")
def list_actions(
    status: Annotated[ActionStatus | None, typer.Option("--status")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 20,
) -> None:
    async def _run() -> None:
        settings = Settings()
        engine = create_db_engine(settings.database.url)
        await create_db_schema(engine)
        session_maker = create_sessionmaker(engine)
        try:
            repo = ActionRepository(session_maker)
            for action in await repo.list_recent(limit=limit, status=status):
                typer.echo(
                    f"{action.created_at.isoformat()} {action.id} "
                    f"{action.status} {action.severity} {action.action_type} "
                    f"{action.namespace}/{action.target}"
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


@actions_app.command("show")
def show_action(action_id: str) -> None:
    async def _run() -> None:
        settings = Settings()
        engine = create_db_engine(settings.database.url)
        await create_db_schema(engine)
        session_maker = create_sessionmaker(engine)
        try:
            repo = ActionRepository(session_maker)
            action = await repo.get(action_id)
            if action is None:
                typer.echo("Action not found.", err=True)
                raise typer.Exit(code=1)
            typer.echo(json.dumps(action.model_dump(mode="json"), indent=2, sort_keys=True))
        finally:
            await engine.dispose()

    asyncio.run(_run())


@actions_app.command("stats")
def action_stats() -> None:
    async def _run() -> None:
        settings = Settings()
        engine = create_db_engine(settings.database.url)
        await create_db_schema(engine)
        session_maker = create_sessionmaker(engine)
        try:
            repo = ActionRepository(session_maker)
            for status, count in sorted((await repo.count_by_status()).items()):
                typer.echo(f"{status}: {count}")
        finally:
            await engine.dispose()

    asyncio.run(_run())


@state_app.command("get")
def get_state() -> None:
    async def _run() -> None:
        settings = Settings()
        engine = create_db_engine(settings.database.url)
        await create_db_schema(engine)
        session_maker = create_sessionmaker(engine)
        try:
            state = await AgentStateRepository(session_maker).get()
            typer.echo(
                f"{state.mode.value} changed_at={state.changed_at.isoformat()} "
                f"reason={state.reason or '-'}"
            )
        finally:
            await engine.dispose()

    asyncio.run(_run())


@state_app.command("set")
def set_state(
    mode: AgentMode,
    reason: Annotated[str | None, typer.Option("--reason")] = None,
) -> None:
    async def _run() -> None:
        settings = Settings()
        engine = create_db_engine(settings.database.url)
        await create_db_schema(engine)
        session_maker = create_sessionmaker(engine)
        try:
            state = await AgentStateRepository(session_maker).set_mode(mode, reason, None)
            typer.echo(f"{state.mode.value}")
        finally:
            await engine.dispose()

    asyncio.run(_run())


@tool_requests_app.command("list")
def list_tool_requests(
    status: Annotated[str | None, typer.Option("--status")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 20,
) -> None:
    async def _run() -> None:
        settings = Settings()
        engine = create_db_engine(settings.database.url)
        await create_db_schema(engine)
        session_maker = create_sessionmaker(engine)
        try:
            repo = ToolRequestRepository(session_maker)
            for req in await repo.list_recent(limit=limit, status=status):
                typer.echo(
                    f"{req.requested_at.isoformat()} {req.tool_name_suggested} "
                    f"[{req.status}] — {req.description[:80]}"
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


@tenants_app.command("list")
def list_tenants() -> None:
    async def _run() -> None:
        settings = Settings()
        k8s = K8sClient(settings.k8s.kubeconfig_path, settings.k8s.timeout_seconds)
        try:
            namespaces = await k8s.list_namespaces_with_label("saasphere.io/tenant=true")
            for namespace in namespaces:
                metadata = getattr(namespace, "metadata", None)
                typer.echo(str(getattr(metadata, "name", "")))
        finally:
            await k8s.close()

    asyncio.run(_run())


@tenants_app.command("show")
def show_tenant(namespace: str) -> None:
    asyncio.run(_run_tenant_tool(lambda ctx: verify_tenant_health(ctx, namespace)))


@tenants_app.command("deploy")
def deploy_tenant_cmd(
    tenant_type: Annotated[str, typer.Option("--type")],
    name: Annotated[str, typer.Option("--name")],
    tier: Annotated[str, typer.Option("--tier")] = "free",
    hostname: Annotated[str | None, typer.Option("--hostname")] = None,
    image: Annotated[str | None, typer.Option("--image")] = None,
    admin_email: Annotated[str | None, typer.Option("--admin-email")] = None,
) -> None:
    async def _call(ctx: object) -> str:
        return await deploy_tenant(
            ctx,  # type: ignore[arg-type]
            tenant_type=tenant_type,
            name=name,
            tier=tier,
            hostname=hostname,
            image=image,
            admin_email=admin_email,
        )

    asyncio.run(_run_tenant_tool(_call))


@tenants_app.command("delete")
def delete_tenant_cmd(
    namespace: Annotated[str, typer.Option("--namespace")],
    confirm: Annotated[str, typer.Option("--confirm")],
) -> None:
    asyncio.run(_run_tenant_tool(lambda ctx: delete_tenant(ctx, namespace, confirm)))


@tenants_app.command("pause")
def pause_tenant_cmd(namespace: str) -> None:
    asyncio.run(_run_tenant_tool(lambda ctx: pause_tenant(ctx, namespace)))


@tenants_app.command("resume")
def resume_tenant_cmd(namespace: str) -> None:
    asyncio.run(_run_tenant_tool(lambda ctx: resume_tenant(ctx, namespace)))


@tenants_app.command("health")
def tenant_health_cmd(namespace: str) -> None:
    asyncio.run(_run_tenant_tool(lambda ctx: verify_tenant_health(ctx, namespace)))


def main() -> None:
    app()


async def _build_agent_deps(settings: Settings) -> tuple[AgentDeps, Callable[[], Awaitable[None]]]:
    engine = create_db_engine(settings.database.url)
    await create_db_schema(engine)
    session_maker = create_sessionmaker(engine)
    approval_repo = ApprovalRepository(session_maker)
    action_repo = ActionRepository(session_maker)
    state_repo = AgentStateRepository(session_maker)

    async def approval_repo_factory() -> ApprovalRepository:
        return approval_repo

    async def action_repo_factory() -> ActionRepository:
        return action_repo

    async def agent_state_repo_factory() -> AgentStateRepository:
        return state_repo

    approval_manager = ApprovalManager(
        approval_repo_factory,
        agent_state_repo_factory,
        TelegramNotifier(settings),
        settings.approval,
    )
    prometheus = PrometheusClient(settings.prometheus.url, settings.prometheus.timeout_seconds)
    loki = LokiClient(settings.loki.url, settings.loki.timeout_seconds)
    k8s = K8sClient(settings.k8s.kubeconfig_path, settings.k8s.timeout_seconds)
    alertmanager = AlertmanagerClient(
        settings.alertmanager.url,
        settings.alertmanager.timeout_seconds,
    )

    async def cleanup() -> None:
        await alertmanager.close()
        await k8s.close()
        await loki.close()
        await prometheus.close()
        await engine.dispose()

    return (
        AgentDeps(
            prometheus=prometheus,
            loki=loki,
            k8s=k8s,
            alertmanager=alertmanager,
            decisions_repo=DecisionRepository(session_maker),
            approval_manager=approval_manager,
            action_repo_factory=action_repo_factory,
            agent_state_repo_factory=agent_state_repo_factory,
        ),
        cleanup,
    )


async def _run_tenant_tool(
    func: Callable[[Any], Awaitable[str]],
) -> None:
    settings = Settings()
    deps, cleanup = await _build_agent_deps(settings)
    agent = LobsterAgent(settings, deps=deps, no_tools=True)
    try:
        # Construct the minimal shape pydantic-ai tools use: an object with .deps.
        result = await func(type("RunContextShim", (), {"deps": deps})())
        typer.echo(result)
    finally:
        await agent.close()
        await cleanup()


if __name__ == "__main__":
    main()
