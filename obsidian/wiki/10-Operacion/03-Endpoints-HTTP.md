---
title: Operación — Endpoints HTTP
tags: [operacion, http, fastapi, admin]
---

# 🌐 HTTP · `:8080` endpoints

> [!abstract] Solo 5 endpoints
> Lobster es un agente, no un servicio web público. Su HTTP es **mínimo**: salud, métricas, webhook reactivo y dos admin.

## 📋 Tabla

| Path | Método | Auth | Función |
|---|---|---|---|
| `/health` | GET | none | Estado + uptime |
| `/metrics` | GET | none | Métricas Prometheus |
| `/webhook/alert` | POST | none | Recibe alerts de Alertmanager |
| `/admin/jobs` | GET | none* | Lista jobs del scheduler |
| `/admin/trigger/{job_id}` | POST | none* | Fuerza ejecución |

> [!danger] none*
> Hoy los `/admin/*` no tienen autenticación. Confían en que el endpoint solo es alcanzable desde la LAN privada. **No exponer fuera.**

## 🩺 `/health`

```bash
curl http://localhost:8080/health
# {"status":"ok","version":"0.1.0","uptime_seconds":3245.12}
```

> [!info] Para healthchecks
> Usado por systemd indirectamente (`Restart=on-failure` no chequea, pero un sidecar healthcheck sí podría) y para validar arranque tras un `restart`.

## 📊 `/metrics`

```bash
curl http://localhost:8080/metrics
# # HELP lobster_info Lobster version info
# # TYPE lobster_info gauge
# lobster_info{version="0.1.0"} 1.0
# # HELP lobster_uptime_seconds Uptime in seconds
# # TYPE lobster_uptime_seconds gauge
# lobster_uptime_seconds 3245.12
# ...
```

Prometheus en Sauron scrapea esto cada 15 s.

## 🚨 `/webhook/alert`

```bash
curl -X POST http://localhost:8080/webhook/alert \
  -H "Content-Type: application/json" \
  -d '{"status":"firing","alerts":[{"labels":{"alertname":"Test"}}]}'
# {"status":"accepted"}      # status 202
```

Async. Devuelve 202 inmediato y lanza task en background con `CaseUse.ALERT_REACTIVE`.

→ Detalle en [[../06-Observabilidad/05-Webhook-Alertmanager]].

## 🛠️ `/admin/jobs`

```bash
curl http://localhost:8080/admin/jobs
# {
#   "jobs": [
#     {"id": "health_loop",      "next_run": "2026-05-16 17:35:00+02:00"},
#     {"id": "global_state",     "next_run": "2026-05-16 17:48:00+02:00"},
#     {"id": "hourly_summary",   "next_run": "2026-05-16 18:00:00+02:00"},
#     {"id": "daily_summary",    "next_run": "2026-05-17 08:00:00+02:00"},
#     {"id": "backup",           "next_run": "2026-05-17 02:00:00+02:00"},
#     {"id": "optimization",     "next_run": "2026-05-17 03:00:00+02:00"}
#   ]
# }
```

## ⚡ `/admin/trigger/{job_id}`

```bash
curl -X POST http://localhost:8080/admin/trigger/health_loop
# {"status":"triggered","job_id":"health_loop"}

curl -X POST http://localhost:8080/admin/trigger/daily_summary
# {"status":"triggered","job_id":"daily_summary"}     # OJO: dispara qwen3:32b
```

> [!warning] No es asíncrono "fire and forget"
> Mueve la `next_run_time` del job a `now()`. APScheduler lo recoge en el siguiente tick. Si el job está corriendo todavía, `max_instances=1` lo descarta.

## 🛡️ Middleware de métricas

```python
@app.middleware("http")
async def metrics_middleware(request, call_next):
    response = await call_next(request)
    lobster_http_requests_total.labels(
        endpoint=request.url.path,
        status=str(response.status_code),
    ).inc()
    return response
```

Cuenta cada request. Útil para detectar tormentas de webhooks o lo contrario.

## 🚫 Lo que NO existe

> [!warning] Sin `/api/*`
> Lobster no expone una API pública para "cambiar modo" ni "lanzar mutación". Eso se hace solo por CLI y Telegram. Decisión deliberada: limitar la superficie.

→ Para CLI ver [[01-Comandos-CLI]]. Para Telegram ver [[02-Comandos-Telegram]].
