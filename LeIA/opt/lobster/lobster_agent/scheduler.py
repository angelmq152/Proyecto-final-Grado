import asyncio
import pathlib
import re
import time
from contextlib import suppress
from datetime import datetime

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from lobster_agent.agent.orchestrator import LobsterAgent
from lobster_agent.agent.routing import CaseUse
from lobster_agent.config import SchedulerConfig
from lobster_agent.observability.metrics import (
    lobster_errors_total,
    lobster_last_cycle_timestamp,
    lobster_scheduler_runs_total,
)
from lobster_agent.telegram.formatting import bold, md_to_mdv2
from lobster_agent.telegram.notifier import TelegramNotifier

log = structlog.get_logger()

_JOB_EMOJI: dict[str, str] = {
    "health_loop_read": "🩺",
    "health_loop_analyze": "🔍",
    "global_state": "🌐",
    "summary": "📊",
    "daily_summary": "📅",
    "backup": "💾",
    "optimization": "⚡",
    "alert_reactive": "🚨",
}

# Keywords that are unambiguously K8s failure states. Deliberately narrow to avoid
# false positives from healthy status descriptions that mention "no errors" or "no pending".
_ANOMALY_KEYWORDS = (
    "crashloopbackoff",
    "oomkill",
    "oomkilled",
    "evicted",
    "imagepullbackoff",
    "errimagepull",
    "backoff",
    "unhealthy",
    "[anomalía]",
)

_HEALTH_LOOP_READ_PROMPT_TEMPLATE = (
    "Ejecuta un health check rápido usando las herramientas disponibles.\n"
    "(A) Pods: lista pods en todos los namespaces de tenant y comprueba su "
    "estado real. Si hay algún pod en CrashLoopBackOff, OOMKilled, "
    "ImagePullBackOff o con más de 5 reinicios, marca el problema con "
    "'[ANOMALÍA]'.\n"
    "(B) Presión de matrix: llama a get_node_health('matrix'). Si matrix está "
    "NotReady o supera el umbral PIN (CPU > {pin_cpu_pct}% o memoria > "
    "{pin_mem_pct}%), marca con '[ANOMALÍA]' y empieza la descripción con "
    "'matrix bajo presión'.\n"
    "(C) Workloads pinados pendientes de devolver: lista deployments en "
    "namespaces de tenant. Si alguno tiene nodeSelector "
    "kubernetes.io/hostname=fallback Y matrix está Ready con CPU < "
    "{unpin_cpu_pct}% y memoria < {unpin_mem_pct}%, marca con '[ANOMALÍA]' y "
    "empieza la descripción con 'workloads pinados a fallback con matrix "
    "recuperado'.\n"
    "(D) Matrix vivo: llama a is_node_alive('matrix'). Si devuelve alive=false, "
    "marca con '[ANOMALÍA]' y empieza la descripción con 'matrix caído'. Esta "
    "comprobación es prioritaria sobre la (B): si matrix no está vivo, no "
    "tiene sentido hablar de presión.\n"
    "REGLAS de marcado: tu respuesta debe empezar EXACTAMENTE con '[ANOMALÍA]' "
    "si detectaste cualquiera de A/B/C/D, o con '[OK]' si todo está sano. "
    "Describe los recursos por su nombre real obtenido con las herramientas "
    "(nunca uses ejemplos ficticios). Sé breve. "
    "No uses '[ANOMALÍA]' para describir lo que NO está pasando: si dudas, es '[OK]'."
)

_HEALTH_LOOP_ANALYZE_PROMPT = (
    "Se ha detectado una anomalía real en el health check anterior. "
    "IMPORTANTE: usa SIEMPRE las herramientas disponibles para obtener datos "
    "reales antes de hacer cualquier recomendación. Nunca uses nombres de pod "
    "o deployment de ejemplo — obtén el nombre exacto con list_pods o "
    "list_deployments.\n"
    "Si la anomalía es un POD en mal estado:\n"
    "1. list_pods (sin namespace) para enumerar todos los pods reales.\n"
    "2. Si la lectura previa menciona un pod, COMPRUEBA primero que aparece "
    "en list_pods. Si no aparece, NO inventes: responde 'Pod referenciado no "
    "existe en list_pods, abortando análisis' y termina sin actuar.\n"
    "3. Con el pod confirmado, get_pod_logs para ver el error exacto.\n"
    "4. Decide la acción. Si el pod está en CrashLoopBackOff confirmado por "
    "las herramientas, reinícialo de forma autónoma con restart_pod. "
    "Para cualquier otra acción destructiva, solicita aprobación.\n"
    "Si la anomalía es 'matrix bajo presión': (1) verifica con "
    "get_node_health('matrix') que sigue por encima del umbral. (2) "
    "get_node_health('fallback') — si fallback también está saturado, "
    "notifica y NO actúes. (3) list_deployments en namespaces de tenant para "
    "identificar candidatos que aún corren en matrix sin pinar. (4) "
    "pin_deployment_to_node(namespace, deployment, node='fallback') para los "
    "candidatos prioritarios (mayor consumo primero). Requiere aprobación.\n"
    "Si la anomalía es 'matrix caído': (1) confirma con "
    "is_node_alive('matrix') que sigue alive=false. (2) confirma con "
    "is_node_alive('fallback') que fallback sí está vivo — si fallback también "
    "está caído, notifica y NO actúes. (3) list_deployments en namespaces de "
    "tenant para identificar candidatos. (4) pin_deployment_to_node(namespace, "
    "deployment, node='fallback') para cada candidato. Requiere aprobación "
    "por el riesgo de mover datos a un nodo distinto.\n"
    "Si la anomalía es 'workloads pinados a fallback con matrix recuperado': "
    "(1) confirma con query_prometheus_range que matrix ha estado por debajo "
    "del umbral UNPIN durante los últimos 15 minutos. (2) list_deployments y "
    "filtra los que tienen nodeSelector kubernetes.io/hostname=fallback. (3) "
    "unpin_deployment_from_node(namespace, deployment) para cada uno. "
    "Autónomo, sin aprobación."
)

_GLOBAL_STATE_PROMPT = (
    "Resume el estado global de SaaSphere: uso de CPU, memoria y disco por nodo, "
    "tenants activos e inactivos, alertas activas. Detecta tendencias preocupantes "
    "y registra un snapshot del estado."
)

_HOURLY_SUMMARY_PROMPT = (
    "Genera un resumen operativo de la última hora: decisiones tomadas, "
    "alertas recibidas, acciones ejecutadas, errores detectados. Sé breve."
)

_DAILY_SUMMARY_PROMPT = """\
Genera el informe operativo diario de SaaSphere. Debes llamar a las herramientas \
disponibles y usar sus resultados reales. Nunca escribas "???" ni texto placeholder. \
Si una herramienta falla, anota el error y continúa con la siguiente. \
No pidas confirmación al usuario.

Llama a estas herramientas (sin pasar namespace para obtener todos los namespaces):
- get_node_health
- list_namespaces
- list_pods
- list_deployments
- list_ingresses
- list_active_alerts
- get_recent_errors (hours=24)
- search_decisions (limit=20)
- list_recent_events

Con los datos obtenidos, genera un informe en Markdown con estas secciones:

# Resumen diario

## 🖥️ Nodos
(tabla con CPU %, memoria % y estado de cada nodo)

## 🏢 Tenants y pods
(estado por namespace: pods Running/total, deployments OK/total)

## ⚠️ Pods problemáticos
(pods que no estén en Running o Completed; si ninguno: "Ninguno")

## 🚨 Alertas activas
(alertas de Alertmanager; si ninguna: "Ninguna")

## 🪵 Errores en logs (últimas 24 h)
(errores más frecuentes de Loki)

## 📋 Decisiones del día
(acciones tomadas por el agente)

## ✅ Conclusión
(estado general y recomendaciones)
"""

_BACKUP_PROMPT = (
    "Verifica el estado de los backups: comprueba qué tenants tienen backups "
    "pendientes según su tier (free=semanal, basic/premium=diario). "
    "Reporta el estado de cada tenant y cualquier backup fallido."
)

_OPTIMIZATION_PROMPT = (
    "Identifica tenants del tier 'free' sin actividad reciente (sin requests "
    "en Ingress en las últimas 2 horas). Para cada candidato a scale-to-zero, "
    "comprueba el historial de decisiones: si ya fue aprobado antes, ejecuta "
    "el scale-to-zero de forma autónoma. Si es la primera vez, solicita aprobación."
)


class SchedulerRunner:
    def __init__(
        self,
        config: SchedulerConfig,
        agent: LobsterAgent,
        notifier: TelegramNotifier,
    ) -> None:
        self._config = config
        self._agent = agent
        self._notifier = notifier
        self._scheduler = AsyncIOScheduler(timezone=config.timezone)

    def start(self) -> None:
        self._scheduler.add_job(
            self._health_loop_job,
            IntervalTrigger(minutes=self._config.health_loop_interval_minutes),
            id="health_loop",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.add_job(
            self._global_state_job,
            IntervalTrigger(minutes=self._config.global_state_interval_minutes),
            id="global_state",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        if self._config.hourly_summary_enabled:
            self._scheduler.add_job(
                self._hourly_summary_job,
                CronTrigger(minute=0),
                id="hourly_summary",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        self._scheduler.add_job(
            self._daily_summary_job,
            CronTrigger(
                hour=self._config.daily_summary_hour,
                minute=self._config.daily_summary_minute,
            ),
            id="daily_summary",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.add_job(
            self._backup_job,
            CronTrigger(
                hour=self._config.backup_hour,
                minute=self._config.backup_minute,
            ),
            id="backup",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.add_job(
            self._optimization_job,
            CronTrigger(
                hour=self._config.optimization_hour,
                minute=self._config.optimization_minute,
            ),
            id="optimization",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()
        log.info(
            "lobster.scheduler.started",
            jobs=len(self._scheduler.get_jobs()),
            timezone=self._config.timezone,
        )

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            log.info("lobster.scheduler.stopped")

    def trigger_job_now(self, job_id: str) -> bool:
        job = self._scheduler.get_job(job_id)
        if job is None:
            return False
        job.modify(
            next_run_time=datetime.now(tz=job.next_run_time.tzinfo if job.next_run_time else None)
        )  # noqa: E501
        return True

    def list_jobs(self) -> list[dict[str, str]]:
        return [{"id": j.id, "next_run": str(j.next_run_time)} for j in self._scheduler.get_jobs()]

    async def _health_loop_job(self) -> None:
        prompt = _HEALTH_LOOP_READ_PROMPT_TEMPLATE.format(
            pin_cpu_pct=self._config.node_pressure_cpu_threshold_pct,
            pin_mem_pct=self._config.node_pressure_memory_threshold_pct,
            unpin_cpu_pct=self._config.node_pressure_unpin_cpu_threshold_pct,
            unpin_mem_pct=self._config.node_pressure_unpin_memory_threshold_pct,
        )
        await self._run_scheduled_job(
            CaseUse.HEALTH_LOOP_READ,
            prompt,
            notify=False,
            follow_up_on_anomaly=True,
            job_timeout=300,
        )

    async def _global_state_job(self) -> None:
        await self._run_scheduled_job(
            CaseUse.GLOBAL_STATE,
            _GLOBAL_STATE_PROMPT,
            notify=False,
            job_timeout=600,
        )

    async def _hourly_summary_job(self) -> None:
        await self._run_scheduled_job(
            CaseUse.SUMMARY,
            _HOURLY_SUMMARY_PROMPT,
            notify=True,
            job_timeout=600,
        )

    async def _daily_summary_job(self) -> None:
        # 1800s = 30 min: qwen3:32b sin think hace ~10 tool calls y cada uno
        # puede tardar varios minutos. 1200s antes cancelaba el job a mitad
        # de generación y se perdía la notificación a Telegram + Obsidian.
        await self._run_scheduled_job(
            CaseUse.DAILY_SUMMARY,
            _DAILY_SUMMARY_PROMPT,
            notify=True,
            save_obsidian=True,
            job_timeout=1800,
        )

    async def _backup_job(self) -> None:
        await self._run_scheduled_job(
            CaseUse.BACKUP,
            _BACKUP_PROMPT,
            notify=True,
            job_timeout=300,
        )

    async def _optimization_job(self) -> None:
        await self._run_scheduled_job(
            CaseUse.OPTIMIZATION,
            _OPTIMIZATION_PROMPT,
            notify=False,
            job_timeout=600,
        )

    async def _run_scheduled_job(
        self,
        case_use: CaseUse,
        prompt: str,
        *,
        notify: bool,
        follow_up_on_anomaly: bool = False,
        save_obsidian: bool = False,
        job_timeout: float = 600,
    ) -> None:
        log.info("lobster.scheduler.job.start", case_use=case_use.value)
        try:
            result = await asyncio.wait_for(
                self._agent.run(case_use, prompt),
                timeout=job_timeout,
            )
            lobster_last_cycle_timestamp.labels(case_use=case_use.value).set(time.time())
            lobster_scheduler_runs_total.labels(
                case_use=case_use.value, outcome=result.outcome
            ).inc()

            if result.outcome == "success" and result.data:
                if notify:
                    emoji = _JOB_EMOJI.get(case_use.value, "🤖")
                    header = bold(f"{emoji} Lobster [{case_use.value}]")
                    body = md_to_mdv2(result.data[:3000])
                    await self._notifier.send_to_admin(f"{header}\n\n{body}")

                if save_obsidian:
                    try:
                        await asyncio.to_thread(
                            _save_obsidian_note,
                            self._config.obsidian_path,
                            case_use,
                            result.data,
                        )
                    except OSError as obs_exc:
                        # No queremos que un fallo de E/S en la nota de Obsidian
                        # marque el job entero como exception (ya notificó por
                        # Telegram y guardó la decisión).
                        lobster_errors_total.labels(component="scheduler", severity="warning").inc()
                        log.warning(
                            "lobster.scheduler.obsidian_note_failed",
                            case_use=case_use.value,
                            error=str(obs_exc),
                        )

                if follow_up_on_anomaly and _has_anomaly(result.data):
                    log.info(
                        "lobster.scheduler.anomaly_detected",
                        case_use=case_use.value,
                    )
                    await self._run_analyze_phase(result.data)
            elif result.outcome == "failed":
                log.warning(
                    "lobster.scheduler.job.failed",
                    case_use=case_use.value,
                    error=result.error,
                )
        except TimeoutError:
            lobster_scheduler_runs_total.labels(case_use=case_use.value, outcome="timeout").inc()
            lobster_errors_total.labels(component="scheduler", severity="warning").inc()
            log.warning(
                "lobster.scheduler.job.timeout",
                case_use=case_use.value,
                timeout_seconds=job_timeout,
            )
        except Exception as exc:
            lobster_scheduler_runs_total.labels(case_use=case_use.value, outcome="exception").inc()
            lobster_errors_total.labels(component="scheduler", severity="error").inc()
            log.exception(
                "lobster.scheduler.job.exception",
                case_use=case_use.value,
                error=str(exc),
            )

    async def _run_analyze_phase(self, read_output: str) -> None:
        prompt = (
            f"{_HEALTH_LOOP_ANALYZE_PROMPT}\n\nResumen de la lectura previa:\n{read_output[:2000]}"
        )
        try:
            result = await asyncio.wait_for(
                self._agent.run(CaseUse.HEALTH_LOOP_ANALYZE, prompt),
                timeout=900,
            )
            lobster_last_cycle_timestamp.labels(case_use=CaseUse.HEALTH_LOOP_ANALYZE.value).set(
                time.time()
            )
            lobster_scheduler_runs_total.labels(
                case_use=CaseUse.HEALTH_LOOP_ANALYZE.value, outcome=result.outcome
            ).inc()
            if result.data:
                header = bold("🔍 Lobster [health_loop_analyze]")
                body = md_to_mdv2(result.data[:3000])
                await self._notifier.send_to_admin(f"{header}\n\n{body}")
        except TimeoutError:
            lobster_scheduler_runs_total.labels(
                case_use=CaseUse.HEALTH_LOOP_ANALYZE.value, outcome="timeout"
            ).inc()
            lobster_errors_total.labels(component="scheduler", severity="warning").inc()
            log.warning("lobster.scheduler.analyze_phase.timeout")
        except Exception as exc:
            lobster_errors_total.labels(component="scheduler", severity="error").inc()
            log.exception("lobster.scheduler.analyze_phase.exception", error=str(exc))

    async def trigger_alert_reactive(self, alert_payload: dict[str, object]) -> None:
        alerts = alert_payload.get("alerts", [])
        status = str(alert_payload.get("status", "unknown"))
        labels = alert_payload.get("commonLabels", {})
        annotations = alert_payload.get("commonAnnotations", {})
        alert_count = len(alerts) if isinstance(alerts, list) else "desconocido"

        prompt = (
            f"Alertmanager ha disparado un webhook. Estado: {status}.\n"
            f"Etiquetas comunes: {labels}\n"
            f"Anotaciones: {annotations}\n"
            f"Número de alertas: {alert_count}.\n\n"
            "IMPORTANTE: usa SIEMPRE las herramientas para obtener datos reales antes "
            "de decidir nada. Nunca inventes nombres de pod, namespace o deployment. "
            "Nunca asumas que un recurso vive en el namespace 'default'.\n\n"
            "Flujo obligatorio:\n"
            "1. Lee las etiquetas de la alerta para identificar el recurso afectado "
            "(namespace, pod, deployment, nodo).\n"
            "2. Si la alerta menciona un pod o deployment pero no su namespace, "
            "ejecuta list_pods (sin namespace) para localizarlo por nombre real.\n"
            "3. Con el nombre y namespace reales, llama a get_pod o list_deployments "
            "para confirmar el estado. Si necesitas logs, llama a get_pod_logs.\n"
            "4. Decide la acción:\n"
            "   - Si el pod está confirmado en CrashLoopBackOff: invoca restart_pod "
            "directamente (es autónoma).\n"
            "   - Si confirmas que un Deployment está fallando: invoca "
            "restart_deployment (pedirá aprobación si no es autónoma).\n"
            "   - Si la alerta ya está 'resolved' y las métricas son normales: "
            "confirma y termina sin acción.\n"
            "5. NUNCA escribas tool calls como texto en la respuesta "
            "(p.ej. <tools>{...}</tools>). Llama a la herramienta de verdad usando el "
            "mecanismo de tool use del modelo. Si no la llamas como tool, no se ejecuta."
        )
        await self._run_scheduled_job(
            CaseUse.ALERT_REACTIVE,
            prompt,
            notify=True,
        )


# El prompt de health_loop_read obliga a empezar la respuesta por '[OK]' o por
# '[ANOMALÍA]'. Cualquier intento de leer keywords del cuerpo del texto produce
# falsos positivos (p.ej. "no presentan errores como CrashLoopBackOff" disparaba
# un health_loop_analyze caro e inventaba un pod inexistente). Confiamos solo
# en el prefijo estructural.
_ANOMALY_PREFIX_RE = re.compile(r"\s*\[\s*anomal", re.IGNORECASE)


def _has_anomaly(text: str) -> bool:
    return bool(_ANOMALY_PREFIX_RE.match(text or ""))


def _save_obsidian_note(base_path: str, case_use: CaseUse, content: str) -> None:
    now = datetime.now()
    month_dir = pathlib.Path(base_path) / now.strftime("%Y-%m")
    month_dir.mkdir(parents=True, exist_ok=True)
    note_path = month_dir / f"{now.strftime('%Y-%m-%d')}_{case_use.value}.md"
    frontmatter = (
        f"---\n"
        f"date: {now.strftime('%Y-%m-%d')}\n"
        f"time: {now.strftime('%H:%M')}\n"
        f"type: {case_use.value}\n"
        f"tags: [lobster, {case_use.value}]\n"
        f"---\n\n"
        f"# {now.strftime('%Y-%m-%d')} — {case_use.value.replace('_', ' ').title()}\n\n"
        f"*Generado automáticamente por Lobster a las {now.strftime('%H:%M')}*\n\n"
    )
    mode = "a" if note_path.exists() else "w"
    with note_path.open(mode, encoding="utf-8") as f:
        if mode == "w":
            f.write(frontmatter)
        else:
            f.write(f"\n---\n\n*Actualización a las {now.strftime('%H:%M')}*\n\n")
        f.write(content)
        f.write("\n")
    log.info("lobster.scheduler.obsidian_note_saved", path=str(note_path))


def _safe_cancel(task: asyncio.Task[object]) -> None:
    if not task.done():
        task.cancel()
        asyncio.ensure_future(_await_cancelled(task))


async def _await_cancelled(task: asyncio.Task[object]) -> None:
    with suppress(asyncio.CancelledError):
        await task
