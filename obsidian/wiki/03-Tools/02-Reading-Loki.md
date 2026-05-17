---
title: Reading — Loki tools
tags: [tools, reading, loki, logs]
---

# 🪵 Reading · Loki

> [!abstract] Ver logs sin SSH
> Dos tools envuelven el `LokiClient`. El agente puede pedir cualquier consulta LogQL en una ventana temporal y recibir hasta 1000 líneas truncadas.

## 🛠️ `query_loki_logs(logql, minutes=15, limit=100)`

> [!example] Petición típica
> ```text
> Tool: query_loki_logs
> Args:
>   logql: '{service="lobster"} |~ "(?i)error"'
>   minutes: 30
>   limit: 50
> ```
> - `minutes`: `[1, 360]` (validación Pydantic).
> - `limit`: `[1, 1000]`.
>
> Devuelve `LokiQueryResult { logql, minutes, lines: list[LogLine] }`. Cada `LogLine` lleva `timestamp`, `labels`, `line` (truncada a 500).

## 🛠️ `get_recent_errors(service, minutes=15)`

> [!example] Atajo para "qué errores ha tenido X"
> ```text
> Tool: get_recent_errors
> Args: { "service": "lobster", "minutes": 15 }
> ```
> Internamente ejecuta:
> ```logql
> {service="lobster"} |~ "(?i)error|exception|failed"
> ```
>
> Devuelve solo las `lines` (sin envoltorio). Pensada para que el LLM no malgaste tokens montando LogQL.

## 🧬 Modelos

```python
class LogLine(BaseModel):
    timestamp: datetime
    labels: dict[str, str]
    line: str

class LokiQueryResult(BaseModel):
    logql: str
    minutes: int
    lines: list[LogLine]
```

## 📥 Cliente HTTP

`LokiClient.query_range` → `GET /loki/api/v1/query_range?query=…&start=…&end=…&limit=…`. Convierte timestamps a nanos y parsea el response.

> [!info] Push de logs lo hace `observability/logging.py`
> El cliente Loki **solo lee**. Los logs de Lobster se envían a Loki por otro camino: `_loki_enqueue_processor` en structlog encola un dict y un `_flush_loop` los manda cada 5 s a `POST /loki/api/v1/push`.

→ Ver [[../06-Observabilidad/01-Logs-structlog-Loki]] para el lado emisor.

## 🧪 Errores

`LokiQueryError` se traduce a `ToolError(source="loki", message=...)`. El agente lo ve y puede preguntar al humano si Loki está caído.

## 🧭 Buenas LogQL en SaaSphere

> [!tip] LogQL útiles que el LLM aprende
> - `{service="lobster"} |= "approval"` → eventos de aprobación.
> - `{service="lobster"} | json | level="error"` → solo errores estructurados.
> - `{namespace="tenant-acme"}` → todos los logs de un tenant.
> - `{job="kubernetes-pods"} |~ "OOMKilled"` → tenants con OOM.
