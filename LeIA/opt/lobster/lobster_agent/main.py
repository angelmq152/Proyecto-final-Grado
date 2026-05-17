import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from lobster_agent import __version__
from lobster_agent.agent.approvals import ApprovalMaintenanceLoop, ApprovalManager
from lobster_agent.agent.deps import AgentDeps
from lobster_agent.agent.orchestrator import LobsterAgent
from lobster_agent.clients.alertmanager import AlertmanagerClient
from lobster_agent.clients.k8s import K8sClient
from lobster_agent.clients.loki import LokiClient
from lobster_agent.clients.prometheus import PrometheusClient
from lobster_agent.config import Settings
from lobster_agent.k8s_watcher import K8sWatcher
from lobster_agent.observability.logging import setup_logging, start_loki_flusher, stop_loki_flusher
from lobster_agent.observability.metrics import (
    START_TIME,
    get_metrics,
    init_metrics,
    lobster_http_requests_total,
    lobster_webhook_alerts_total,
    lobster_webhook_self_alerts_dropped_total,
)
from lobster_agent.persistence.db import create_db_engine, create_db_schema, create_sessionmaker
from lobster_agent.persistence.repositories import (
    ActionRepository,
    AgentStateRepository,
    ApprovalRepository,
    ConversationRepository,
    DecisionRepository,
    ToolRequestRepository,
)
from lobster_agent.scheduler import SchedulerRunner
from lobster_agent.telegram.bot import TelegramBotRunner
from lobster_agent.telegram.memory import ConversationMemory
from lobster_agent.telegram.notifier import TelegramNotifier

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = app.state.settings
    setup_logging(
        log_level=settings.log_level,
        loki_url=f"{settings.loki.url}{settings.loki.push_path}",
        flush_interval=settings.loki.flush_interval_seconds,
        batch_size=settings.loki.batch_size,
    )
    init_metrics(__version__)
    if settings.environment == "prod":
        await start_loki_flusher()
    engine = create_db_engine(settings.database.url)
    await create_db_schema(engine)
    session_maker = create_sessionmaker(engine)
    approval_repo = ApprovalRepository(session_maker)
    action_repo = ActionRepository(session_maker)
    state_repo = AgentStateRepository(session_maker)
    conv_repo = ConversationRepository(session_maker)
    tool_request_repo = ToolRequestRepository(session_maker)

    async def approval_repo_factory() -> ApprovalRepository:
        return approval_repo

    async def action_repo_factory() -> ActionRepository:
        return action_repo

    async def agent_state_repo_factory() -> AgentStateRepository:
        return state_repo

    async def conv_repo_factory() -> ConversationRepository:
        return conv_repo

    async def tool_request_repo_factory() -> ToolRequestRepository:
        return tool_request_repo

    notifier = TelegramNotifier(settings)
    approval_manager = ApprovalManager(
        approval_repo_factory,
        agent_state_repo_factory,
        notifier,
        settings.approval,
    )
    maintenance_loop = ApprovalMaintenanceLoop(
        approval_repo_factory,
        notifier,
        settings.approval,
    )
    prometheus = PrometheusClient(settings.prometheus.url, settings.prometheus.timeout_seconds)
    loki = LokiClient(settings.loki.url, settings.loki.timeout_seconds)
    k8s = K8sClient(settings.k8s.kubeconfig_path, settings.k8s.timeout_seconds)
    alertmanager = AlertmanagerClient(
        settings.alertmanager.url,
        settings.alertmanager.timeout_seconds,
    )
    deps = AgentDeps(
        prometheus=prometheus,
        loki=loki,
        k8s=k8s,
        alertmanager=alertmanager,
        decisions_repo=DecisionRepository(session_maker),
        approval_manager=approval_manager,
        action_repo_factory=action_repo_factory,
        agent_state_repo_factory=agent_state_repo_factory,
        tool_request_repo_factory=tool_request_repo_factory,
        notifier=notifier,
    )
    agent = LobsterAgent(settings, deps=deps)
    memory = ConversationMemory(conv_repo_factory, settings.agent.max_conversation_turns)
    bot_runner = TelegramBotRunner(
        settings,
        approval_repo_factory,
        agent_state_repo_factory,
        notifier,
        agent,
        memory,
        tool_request_repo_factory=tool_request_repo_factory,
    )
    scheduler = SchedulerRunner(settings.scheduler, agent, notifier)
    k8s_watcher = K8sWatcher(settings.k8s.kubeconfig_path, settings.scheduler, agent, notifier)

    app.state.lobster_agent = agent
    app.state.lobster_deps = deps
    app.state.lobster_engine = engine
    app.state.lobster_approval_manager = approval_manager
    app.state.lobster_telegram_bot = bot_runner
    app.state.lobster_scheduler = scheduler

    await bot_runner.start()
    await maintenance_loop.start()
    scheduler.start()
    await k8s_watcher.start()
    log.info("lobster.started", version=__version__, env=settings.environment)
    yield
    log.info("lobster.stopping")
    await k8s_watcher.stop()
    scheduler.stop()
    await maintenance_loop.stop()
    await bot_runner.stop()
    await app.state.lobster_agent.close()
    await alertmanager.close()
    await k8s.close()
    await loki.close()
    await prometheus.close()
    await engine.dispose()
    if settings.environment == "prod":
        await stop_loki_flusher()


_SELF_ALERT_PREFIX = "Lobster"


def _self_alertname(payload: dict[str, object]) -> str | None:
    common_labels = payload.get("commonLabels")
    if isinstance(common_labels, dict):
        name = common_labels.get("alertname")
        if isinstance(name, str) and name.startswith(_SELF_ALERT_PREFIX):
            return name

    alerts = payload.get("alerts")
    if not isinstance(alerts, list) or not alerts:
        return None

    names: list[str] = []
    for alert in alerts:
        if not isinstance(alert, dict):
            return None
        labels = alert.get("labels")
        if not isinstance(labels, dict):
            return None
        name = labels.get("alertname")
        if not isinstance(name, str) or not name.startswith(_SELF_ALERT_PREFIX):
            return None
        names.append(name)

    return names[0] if names else None


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Lobster", version=__version__, lifespan=lifespan)
    app.state.settings = settings

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        lobster_http_requests_total.labels(
            endpoint=request.url.path,
            status=str(response.status_code),
        ).inc()
        return response

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "version": __version__,
            "uptime_seconds": round(time.time() - START_TIME, 2),
        }

    @app.get("/metrics")
    async def metrics() -> PlainTextResponse:
        return PlainTextResponse(
            get_metrics().decode(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.post("/webhook/alert")
    async def alert_webhook(request: Request) -> JSONResponse:
        try:
            payload: dict[str, object] = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON"}, status_code=400)

        status = str(payload.get("status", "unknown"))
        lobster_webhook_alerts_total.labels(status=status).inc()
        log.info("lobster.webhook.alert_received", status=status)

        self_alertname = _self_alertname(payload)
        if self_alertname is not None:
            lobster_webhook_self_alerts_dropped_total.labels(alertname=self_alertname).inc()
            log.info(
                "lobster.webhook.self_alert_dropped",
                alertname=self_alertname,
                status=status,
            )
            return JSONResponse(
                {"status": "accepted", "dropped": "self_alert"},
                status_code=202,
            )

        scheduler: SchedulerRunner | None = getattr(request.app.state, "lobster_scheduler", None)
        if scheduler is not None:
            asyncio.create_task(
                scheduler.trigger_alert_reactive(payload),
                name="lobster-webhook-alert",
            )

        return JSONResponse({"status": "accepted"}, status_code=202)

    @app.get("/admin/jobs")
    async def list_jobs(request: Request) -> JSONResponse:
        scheduler: SchedulerRunner | None = getattr(request.app.state, "lobster_scheduler", None)
        if scheduler is None:
            return JSONResponse({"error": "scheduler not running"}, status_code=503)
        return JSONResponse({"jobs": scheduler.list_jobs()})

    @app.post("/admin/trigger/{job_id}")
    async def trigger_job(job_id: str, request: Request) -> JSONResponse:
        scheduler: SchedulerRunner | None = getattr(request.app.state, "lobster_scheduler", None)
        if scheduler is None:
            return JSONResponse({"error": "scheduler not running"}, status_code=503)
        if not scheduler.trigger_job_now(job_id):
            return JSONResponse({"error": f"job '{job_id}' not found"}, status_code=404)
        log.info("lobster.admin.job_triggered", job_id=job_id)
        return JSONResponse({"status": "triggered", "job_id": job_id})

    return app


async def main() -> None:
    settings = Settings()
    app = create_app(settings)
    config = uvicorn.Config(
        app,
        host=settings.http.host,
        port=settings.http.port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    await server.serve()
