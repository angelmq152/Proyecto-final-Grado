---
title: K8s Watcher — streaming de eventos
tags: [scheduler, watcher, k8s, lightkube, streaming]
---

# 👁️ K8s Watcher

> [!abstract] Reacción en tiempo real
> Archivo: `lobster_agent/k8s_watcher.py`. Mantiene un `lightkube.AsyncClient.watch(Event)` abierto. Cuando un Event Warning con razón crítica aparece, lanza un análisis inmediato sin esperar al próximo `health_loop`.

## 🎯 Eventos críticos

```python
_CRITICAL_REASONS = {"BackOff", "OOMKilling", "Failed", "Killing", "Evicted"}
_WARNING_TYPE = "Warning"

def _is_critical_event(event):
    if event.type != "Warning": return False
    reason = event.reason or ""
    return any(r in reason for r in _CRITICAL_REASONS) or "CrashLoop" in reason
```

> [!info] Tres familias
> - **BackOff / CrashLoopBackOff** → el pod no arranca.
> - **OOMKilling** → memoria agotada.
> - **Failed / Killing / Evicted** → eviction o crash.

## 🧪 Prompt para el analyze

```python
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
```

## 🚏 Loop con reconexión exponencial

```python
async def _watch_loop(self):
    delay = self._config.k8s_watcher_reconnect_delay_seconds       # 5 s
    max_delay = self._config.k8s_watcher_max_reconnect_delay_seconds  # 120 s
    while self._running:
        try:
            await self._watch_events()
            delay = self._config.k8s_watcher_reconnect_delay_seconds
        except Exception:
            lobster_errors_total.labels(component="k8s_watcher", severity="warning").inc()
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)
```

> [!tip] Backoff exponencial
> El `watch` HTTP se cae cuando K8s reinicia el apiserver o cuando hay un timeout long-polling. El loop reconecta tras 5 s, 10 s, 20 s, …, hasta 120 s. Si reconecta exitosamente, reset.

## 👁️ Apertura del watch

```python
async def _watch_events(self):
    config = KubeConfig.from_file(self._kubeconfig_path)
    client = AsyncClient(config=config)
    async for event_type, event in client.watch(Event):
        if not self._running: break
        if event_type not in ("ADDED", "MODIFIED"): continue
        if _is_critical_event(event):
            asyncio.create_task(self._handle_event(event))
```

> [!warning] No procesa DELETE
> Solo ADDED y MODIFIED. Los eventos eliminados no aportan información nueva.

## 🚨 Handle event

```python
async def _handle_event(self, event):
    namespace = _event_namespace(event)
    name = _event_name(event)
    reason = _event_reason(event)
    message = _event_message(event)
    log.warning("lobster.k8s_watcher.critical_event", namespace=ns, name=name, ...)

    prompt = _WATCHER_ANALYZE_PROMPT_TEMPLATE.format(...)
    result = await self._agent.run(CaseUse.HEALTH_LOOP_ANALYZE, prompt)
    if result.data:
        await self._notifier.send_to_admin(f"👁️ Lobster [watcher/{reason}]\n\n{body}")
```

> [!tip] Re-usa `HEALTH_LOOP_ANALYZE`
> No es un CaseUse propio. El watcher reusa el modo analyze del health_loop, lo que aprovecha los mismos tools y system prompt sin código duplicado.

## ⚙️ Configuración

```python
class SchedulerConfig(BaseModel):
    k8s_watcher_enabled: bool = True
    k8s_watcher_reconnect_delay_seconds: float = 5.0
    k8s_watcher_max_reconnect_delay_seconds: float = 120.0
```

Deshabilitable si causa ruido (tormentas de eventos durante un rolling update grande, por ejemplo).

## 📈 Métricas

- `lobster_errors_total{component="k8s_watcher", severity="warning"}` → desconexiones.
- `lobster_errors_total{component="k8s_watcher", severity="error"}` → fallos al manejar evento.
- `lobster_scheduler_runs_total{case_use="health_loop_analyze", outcome=...}` → resultados del analyze.

## 🆚 Diferencia con health_loop

| Aspecto | health_loop | k8s_watcher |
|---|---|---|
| Cadencia | 5 min | Real time |
| Disparador | APScheduler | Stream K8s |
| Latencia de detección | hasta 5 min | < 1 s |
| Coste de inferencia | predecible | bursty |
| Cobertura | todo (incluye matrix bajo presión, pin/unpin) | solo eventos críticos K8s |

> [!info] Complementarios, no redundantes
> El watcher detecta antes; el health_loop cubre cosas que K8s no marca como Event (saturación de nodo, deployments sin alarma directa).
