import asyncio
import time
from contextlib import suppress
from typing import Any

import structlog
from lightkube import AsyncClient
from lightkube.config.kubeconfig import KubeConfig
from lightkube.resources.core_v1 import Event

from lobster_agent.agent.orchestrator import LobsterAgent
from lobster_agent.agent.routing import CaseUse
from lobster_agent.config import SchedulerConfig
from lobster_agent.observability.metrics import (
    lobster_errors_total,
    lobster_last_cycle_timestamp,
    lobster_scheduler_runs_total,
)
from lobster_agent.telegram.formatting import bold, esc, md_to_mdv2
from lobster_agent.telegram.notifier import TelegramNotifier

log = structlog.get_logger()

_CRITICAL_REASONS = {"BackOff", "OOMKilling", "Failed", "Killing", "Evicted"}
_WARNING_TYPE = "Warning"

_WATCHER_ANALYZE_PROMPT_TEMPLATE = (
    "El watcher de K8s ha detectado un evento crítico en tiempo real:\n"
    "- Namespace: {namespace}\n"
    "- Pod/recurso: {name}\n"
    "- Razón: {reason}\n"
    "- Mensaje: {message}\n\n"
    "Analiza la situación inmediatamente: consulta logs, métricas y estado del pod. "
    "Si el pod está en CrashLoopBackOff confirmado, reinícialo de forma autónoma. "
    "Para cualquier otra acción, solicita aprobación."
)


class K8sWatcher:
    def __init__(
        self,
        kubeconfig_path: str,
        config: SchedulerConfig,
        agent: LobsterAgent,
        notifier: TelegramNotifier,
    ) -> None:
        self._kubeconfig_path = kubeconfig_path
        self._config = config
        self._agent = agent
        self._notifier = notifier
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        if not self._config.k8s_watcher_enabled:
            log.info("lobster.k8s_watcher.disabled")
            return
        self._running = True
        self._task = asyncio.create_task(self._watch_loop(), name="lobster-k8s-watcher")
        self._task.add_done_callback(self._on_task_done)
        log.info("lobster.k8s_watcher.started")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        self._task = None
        log.info("lobster.k8s_watcher.stopped")

    def _on_task_done(self, task: asyncio.Task[None]) -> None:
        with suppress(asyncio.CancelledError):
            exc = task.exception()
            if exc is not None:
                log.error("lobster.k8s_watcher.task_crashed", error=str(exc))

    async def _watch_loop(self) -> None:
        delay = self._config.k8s_watcher_reconnect_delay_seconds
        max_delay = self._config.k8s_watcher_max_reconnect_delay_seconds

        while self._running:
            try:
                await self._watch_events()
                delay = self._config.k8s_watcher_reconnect_delay_seconds
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                lobster_errors_total.labels(component="k8s_watcher", severity="warning").inc()
                log.warning(
                    "lobster.k8s_watcher.disconnected",
                    error=str(exc),
                    reconnect_in=delay,
                )
                if self._running:
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, max_delay)

    async def _watch_events(self) -> None:
        config = KubeConfig.from_file(self._kubeconfig_path)
        client = AsyncClient(config=config)
        log.info("lobster.k8s_watcher.connected")

        try:
            async for event_type, event in client.watch(Event):
                if not self._running:
                    break
                if event_type not in ("ADDED", "MODIFIED"):
                    continue
                if _is_critical_event(event):
                    asyncio.create_task(
                        self._handle_event(event),
                        name="lobster-k8s-watcher-event",
                    )
        finally:
            await client.close()  # type: ignore[no-untyped-call]

    async def _handle_event(self, event: Any) -> None:
        namespace = _event_namespace(event)
        name = _event_name(event)
        reason = _event_reason(event)
        message = _event_message(event)

        log.warning(
            "lobster.k8s_watcher.critical_event",
            namespace=namespace,
            name=name,
            reason=reason,
            message=message,
        )

        prompt = _WATCHER_ANALYZE_PROMPT_TEMPLATE.format(
            namespace=namespace,
            name=name,
            reason=reason,
            message=message,
        )

        try:
            result = await self._agent.run(CaseUse.HEALTH_LOOP_ANALYZE, prompt)
            lobster_last_cycle_timestamp.labels(case_use=CaseUse.HEALTH_LOOP_ANALYZE.value).set(
                time.time()
            )
            lobster_scheduler_runs_total.labels(
                case_use=CaseUse.HEALTH_LOOP_ANALYZE.value,
                outcome=result.outcome,
            ).inc()
            if result.data:
                header = bold(f"👁️ Lobster [watcher/{reason}]")
                location = f"{esc(namespace)}/{esc(name)}"
                body = md_to_mdv2(result.data[:3000])
                await self._notifier.send_to_admin(f"{header} {location}\n\n{body}")
        except Exception as exc:
            lobster_errors_total.labels(component="k8s_watcher", severity="error").inc()
            log.exception("lobster.k8s_watcher.handle_event.exception", error=str(exc))


def _is_critical_event(event: Any) -> bool:
    event_type = getattr(event, "type", None)
    reason = getattr(event, "reason", None)
    if event_type != _WARNING_TYPE:
        return False
    if not isinstance(reason, str):
        return False
    return any(r in reason for r in _CRITICAL_REASONS) or "CrashLoop" in reason


def _event_namespace(event: Any) -> str:
    metadata = getattr(event, "metadata", None)
    namespace = getattr(metadata, "namespace", None)
    return str(namespace) if namespace else ""


def _event_name(event: Any) -> str:
    involved = getattr(event, "involvedObject", None)
    name = getattr(involved, "name", None)
    if name:
        return str(name)
    metadata = getattr(event, "metadata", None)
    name = getattr(metadata, "name", None)
    return str(name) if name else ""


def _event_reason(event: Any) -> str:
    reason = getattr(event, "reason", None)
    return str(reason) if reason else ""


def _event_message(event: Any) -> str:
    message = getattr(event, "message", None)
    return str(message)[:500] if message else ""
