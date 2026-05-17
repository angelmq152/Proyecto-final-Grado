from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from lobster_agent.agent.routing import CaseUse
from lobster_agent.config import SchedulerConfig
from lobster_agent.scheduler import SchedulerRunner, _has_anomaly

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_result(outcome: str = "success", data: str = "todo ok"):
    from lobster_agent.agent.orchestrator import AgentResult

    return AgentResult(decision_id=uuid4(), outcome=outcome, data=data)


def _make_failed_result():
    from lobster_agent.agent.orchestrator import AgentResult

    return AgentResult(decision_id=uuid4(), outcome="failed", data=None, error="ollama down")


def _make_scheduler(agent_result=None):
    config = SchedulerConfig(
        timezone="UTC",
        health_loop_interval_minutes=5,
        global_state_interval_minutes=30,
        k8s_watcher_enabled=False,
    )
    agent = MagicMock()
    agent.run = AsyncMock(return_value=agent_result or _make_result())
    notifier = MagicMock()
    notifier.send_to_admin = AsyncMock()
    runner = SchedulerRunner(config, agent, notifier)
    return runner, agent, notifier


# ── _has_anomaly ──────────────────────────────────────────────────────────────
# El detector confía únicamente en el prefijo estructural '[ANOMALÍA]' que el
# prompt obliga a poner. Heurísticas léxicas previas generaban falsos positivos
# cuando el modelo describía lo que NO estaba pasando.


def test_has_anomaly_strict_prefix_anomalia():
    assert _has_anomaly("[ANOMALÍA] pod-xyz está en CrashLoopBackOff") is True


def test_has_anomaly_strict_prefix_anomalia_sin_tilde():
    assert _has_anomaly("[ANOMALIA] pod-xyz problemas") is True


def test_has_anomaly_lower_case_prefix():
    assert _has_anomaly("[anomalia] algo mal") is True


def test_has_anomaly_ok_prefix():
    assert _has_anomaly("[OK] Todos los pods Running") is False


def test_has_anomaly_ok_with_negated_keywords_in_body():
    # Caso que rompía la heurística: "no presentan errores como CrashLoopBackOff"
    text = (
        "[OK] Todos los pods están Running. No presentan errores críticos como "
        "CrashLoopBackOff, OOMKilled o ImagePullBackOff."
    )
    assert _has_anomaly(text) is False


def test_has_anomaly_keyword_without_prefix():
    # Mencionar CrashLoopBackOff en el cuerpo SIN [ANOMALÍA] al inicio no
    # cuenta como anomalía. El prompt obliga al prefijo; si falta, no actuamos.
    assert _has_anomaly("Pod en CrashLoopBackOff en tenant-foo") is False


def test_has_anomaly_empty_or_none():
    assert _has_anomaly("") is False
    assert _has_anomaly("Texto cualquiera sin prefijo") is False


# ── health loop ───────────────────────────────────────────────────────────────


async def test_health_loop_runs_read_phase():
    runner, agent, notifier = _make_scheduler(_make_result(data="Todos los pods Running."))

    await runner._health_loop_job()

    agent.run.assert_called_once()
    call_args = agent.run.call_args
    assert call_args[0][0] == CaseUse.HEALTH_LOOP_READ


async def test_health_loop_triggers_analyze_on_anomaly():
    runner, agent, notifier = _make_scheduler(
        _make_result(data="[ANOMALÍA] Pod tenant-foo/web-1 en CrashLoopBackOff")
    )

    await runner._health_loop_job()

    assert agent.run.call_count == 2
    first_case = agent.run.call_args_list[0][0][0]
    second_case = agent.run.call_args_list[1][0][0]
    assert first_case == CaseUse.HEALTH_LOOP_READ
    assert second_case == CaseUse.HEALTH_LOOP_ANALYZE


async def test_health_loop_no_analyze_if_clean():
    runner, agent, notifier = _make_scheduler(_make_result(data="Todo correcto."))

    await runner._health_loop_job()

    assert agent.run.call_count == 1


async def test_health_loop_does_not_notify_on_clean():
    runner, agent, notifier = _make_scheduler(_make_result(data="Todo correcto."))

    await runner._health_loop_job()

    notifier.send_to_admin.assert_not_called()


# ── summary jobs ──────────────────────────────────────────────────────────────


async def test_hourly_summary_notifies():
    runner, agent, notifier = _make_scheduler(_make_result(data="Resumen horario OK."))

    await runner._hourly_summary_job()

    agent.run.assert_called_once()
    assert agent.run.call_args[0][0] == CaseUse.SUMMARY
    notifier.send_to_admin.assert_called_once()
    assert "SUMMARY" in notifier.send_to_admin.call_args[0][0].upper()


async def test_daily_summary_notifies():
    runner, agent, notifier = _make_scheduler(_make_result(data="Resumen diario OK."))

    await runner._daily_summary_job()

    notifier.send_to_admin.assert_called_once()


# ── backup + optimization ─────────────────────────────────────────────────────


async def test_backup_job_runs_backup_case_use():
    runner, agent, notifier = _make_scheduler()

    await runner._backup_job()

    assert agent.run.call_args[0][0] == CaseUse.BACKUP


async def test_optimization_job_runs_optimization_case_use():
    runner, agent, notifier = _make_scheduler()

    await runner._optimization_job()

    assert agent.run.call_args[0][0] == CaseUse.OPTIMIZATION


# ── error handling ────────────────────────────────────────────────────────────


async def test_job_does_not_raise_on_agent_failure():
    runner, agent, notifier = _make_scheduler(_make_failed_result())

    # Should not raise
    await runner._hourly_summary_job()

    agent.run.assert_called_once()
    notifier.send_to_admin.assert_not_called()


async def test_job_does_not_raise_on_exception():
    config = SchedulerConfig(timezone="UTC")
    agent = MagicMock()
    agent.run = AsyncMock(side_effect=RuntimeError("ollama down"))
    notifier = MagicMock()
    notifier.send_to_admin = AsyncMock()
    runner = SchedulerRunner(config, agent, notifier)

    # Should not raise
    await runner._hourly_summary_job()


# ── alert reactive ────────────────────────────────────────────────────────────


async def test_trigger_alert_reactive_calls_agent():
    runner, agent, notifier = _make_scheduler(_make_result(data="Alerta analizada."))

    payload = {
        "status": "firing",
        "commonLabels": {"alertname": "PodCrashing"},
        "commonAnnotations": {"summary": "Pod en crash"},
        "alerts": [{"status": "firing"}],
    }
    await runner.trigger_alert_reactive(payload)

    agent.run.assert_called_once()
    assert agent.run.call_args[0][0] == CaseUse.ALERT_REACTIVE
    prompt = agent.run.call_args[0][1]
    assert "firing" in prompt
    assert "PodCrashing" in prompt


async def test_trigger_alert_reactive_notifies():
    runner, agent, notifier = _make_scheduler(_make_result(data="Análisis de alerta."))

    payload = {"status": "firing", "commonLabels": {}, "commonAnnotations": {}, "alerts": []}
    await runner.trigger_alert_reactive(payload)

    notifier.send_to_admin.assert_called_once()


# ── scheduler start/stop (unit, no real APScheduler) ─────────────────────────


def test_scheduler_start_stop():
    runner, _, _ = _make_scheduler()

    with patch("lobster_agent.scheduler.AsyncIOScheduler") as mock_cls:
        mock_sched = MagicMock()
        mock_sched.running = True
        mock_sched.get_jobs.return_value = [1, 2, 3]
        mock_cls.return_value = mock_sched
        runner._scheduler = mock_sched

        runner.start()
        mock_sched.start.assert_called_once()

        runner.stop()
        mock_sched.shutdown.assert_called_once_with(wait=False)
