---
title: Reading — Alertmanager tools
tags: [tools, reading, alertmanager, alerts]
---

# 🚨 Reading · Alertmanager

> [!abstract] Saber qué está roto sin abrir Grafana
> Dos tools envolviendo el `AlertmanagerClient`. El agente puede preguntar "qué alertas hay" y leer detalles de una en concreto por fingerprint.

## 🛠️ `list_active_alerts(severity=None)`

> [!example] Petición típica
> ```text
> Tool: list_active_alerts
> Args: { "severity": "critical" }
> ```
> - `severity` opcional. Tipos: `Literal["info", "warning", "critical"] | None`.
> - Devuelve `list[AlertSummary]`.

```python
class AlertSummary(BaseModel):
    fingerprint: str
    severity: str | None
    summary: str | None                       # de annotations.summary
    labels: dict[str, str]                    # solo: alertname, severity, namespace, pod, instance, job
    age_minutes: int
```

> [!info] Filtrado de labels
> Solo se exponen al LLM las labels relevantes para identificar la alerta. El resto (que Alertmanager puede tener por route) se descartan para no saturar el contexto.

## 🛠️ `get_alert_details(fingerprint)`

> [!example] Detalle completo
> ```text
> Tool: get_alert_details
> Args: { "fingerprint": "abc123…" }
> ```
> Devuelve `AlertDetail` (extends `AlertSummary`) con:
>
> ```python
> annotations: dict[str, str]   # truncados
> starts_at: datetime
> ends_at: datetime | None
> generator_url: str | None
> status: "active" | "suppressed" | "unprocessed"
> ```

## 🔌 Bajo el capó: `AlertmanagerClient`

```python
class AlertmanagerClient:
    async def list_active_alerts(label_filters=None) -> list[AlertmanagerAlert]
    async def get_alert_by_fingerprint(fingerprint) -> AlertmanagerAlert | None
    async def list_silences(active_only=True) -> list[AlertmanagerSilence]
    async def get_status() -> AlertmanagerStatus
```

Cliente HTTP async via httpx contra `http://192.168.1.201:9093/api/v2`. Filtra `active=true silenced=false inhibited=false` por defecto.

## 🧪 Errores

- `AlertmanagerTimeoutError` → tool retorna `ToolError(source="alertmanager", "timed out")`.
- `AlertmanagerHTTPError` → `ToolError("HTTP 5xx")`.
- Alerta no encontrada → `ToolError("alert <fp> not found")`.

## 🔗 Webhook recíproco

Alertmanager está configurado para **llamar de vuelta** a Lobster vía `POST /webhook/alert`. Esto dispara `CaseUse.ALERT_REACTIVE` que **muy probablemente** invocará `list_active_alerts` o `get_alert_details` para refrescar el contexto antes de actuar.

→ Ver [[../06-Observabilidad/05-Webhook-Alertmanager]] y [[../07-Scheduler-Watcher/05-Alert-reactive]].
