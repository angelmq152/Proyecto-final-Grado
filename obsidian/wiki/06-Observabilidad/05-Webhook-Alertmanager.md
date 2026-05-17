---
title: Observabilidad — Webhook Alertmanager
tags: [observabilidad, webhook, alertmanager, alert-reactive]
---

# 📬 Webhook · `POST /webhook/alert`

> [!abstract] Alertmanager llama a Lobster
> Cuando una regla Prometheus dispara, Alertmanager envía un POST a `http://leia:8080/webhook/alert`. Lobster ack inmediato con 202 y lanza una task de fondo que ejecuta el `CaseUse.ALERT_REACTIVE`.

## 🛣️ Handler

```python
@app.post("/webhook/alert")
async def alert_webhook(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    status = str(payload.get("status", "unknown"))
    lobster_webhook_alerts_total.labels(status=status).inc()
    log.info("lobster.webhook.alert_received", status=status)

    scheduler = request.app.state.lobster_scheduler
    if scheduler is not None:
        asyncio.create_task(scheduler.trigger_alert_reactive(payload))
    return JSONResponse({"status": "accepted"}, status_code=202)
```

> [!tip] 202 inmediato + task fire-and-forget
> Alertmanager espera respuesta rápida; el trabajo del LLM (que puede tardar minutos) se hace en background. Eso evita reintentos de Alertmanager por timeout.

## 📦 Payload de Alertmanager

```json
{
  "version": "4",
  "status": "firing",
  "alerts": [
    {
      "status": "firing",
      "labels": {"alertname":"LobsterDecisionesFallidas","severity":"warning"},
      "annotations": {"summary":"...","description":"...","runbook":"..."},
      "startsAt":"2026-05-16T14:00:00Z",
      "endsAt":"0001-01-01T00:00:00Z",
      "fingerprint":"abc123"
    }
  ],
  "commonLabels": {...},
  "commonAnnotations": {...},
  "externalURL": "https://alertmanager.saasphere.local"
}
```

## 🎬 `trigger_alert_reactive(payload)`

→ Detalle en [[../07-Scheduler-Watcher/05-Alert-reactive]].

```python
prompt = (
    f"Alertmanager ha disparado un webhook. Estado: {status}.\n"
    f"Etiquetas comunes: {labels}\n"
    f"Anotaciones: {annotations}\n"
    f"Número de alertas: {alert_count}.\n\n"
    "IMPORTANTE: usa SIEMPRE las herramientas para obtener datos reales antes de decidir nada..."
)
await self._run_scheduled_job(CaseUse.ALERT_REACTIVE, prompt, notify=True)
```

## ⚙️ Configuración en Alertmanager

> [!example] `alertmanager.yml` — routing dual (Telegram + Lobster)
> ```yaml
> route:
>   group_by: ['alertname', 'instance']
>   group_wait: 30s
>   group_interval: 5m
>   repeat_interval: 12h
>   receiver: telegram
>   routes:
>     - receiver: telegram
>       continue: true
>     - receiver: lobster
>       continue: true
>
> receivers:
>   - name: telegram
>     telegram_configs:
>       - bot_token: '<redacted>'
>         chat_id: 5857999164
>         parse_mode: Markdown
>         message: |
>           🚨 *{{ .Status | toUpper }}* — {{ .CommonLabels.alertname }}
>           📍 *Nodo:* {{ .CommonLabels.instance }}
>           📝 {{ .CommonAnnotations.summary }}
>           {{ if eq .Status "resolved" }}✅ Recuperado{{ end }}
>
>   - name: lobster
>     webhook_configs:
>       - url: http://192.168.1.200:8080/webhook/alert
>         send_resolved: true
> ```

> [!warning] Cuidado con un único `route` con `receiver: lobster`
> Si dejas la subroute `lobster` sin matchers como única hija, **captura todas las alertas** y el `receiver` raíz nunca se invoca — Telegram queda silenciado. Solución: hacer también de `telegram` una subroute con `continue: true`. Incidente documentado en [[../../monitoring/2026-05-17_alertmanager_routing_fix]].

## 🧪 Test manual

```bash
curl -X POST http://localhost:8080/webhook/alert \
  -H "Content-Type: application/json" \
  -d '{"status":"firing","alerts":[{"labels":{"alertname":"Test","severity":"info"}}]}'
# {"status":"accepted"}
```

## 🛡️ Sin autenticación

> [!danger] El endpoint es público en la LAN
> No hay token. Lobster confía en que Alertmanager es el único que sabe la URL en la red privada. Si quieres exponerlo a internet, añade un reverse proxy con auth (no contemplado en el TFG).

## 📈 Métrica

```python
lobster_webhook_alerts_total = Counter(
    "lobster_webhook_alerts_total",
    "Total Alertmanager webhook alerts received",
    ["status"],
)
```

Incremento por status del payload. Útil para detectar tormentas.
