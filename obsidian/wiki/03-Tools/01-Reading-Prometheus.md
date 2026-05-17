---
title: Reading — Prometheus tools
tags: [tools, reading, prometheus, lectura, observabilidad]
---

# 📈 Reading · Prometheus

> [!abstract] Las "vistas" del agente sobre métricas
> Tres tools encapsulan el `PrometheusClient`. El agente nunca habla HTTP directamente: pasa por funciones tipadas con Pydantic, con resultados truncados para ahorrar tokens.

## 🛠️ `query_prometheus_instant(query)`

> [!example] Cómo se usa
> ```text
> Tool: query_prometheus_instant
> Args: { "query": "node_cpu_seconds_total{mode=\"idle\"}" }
> ```
> Devuelve un `PromInstantResult` con `series_count` y hasta N `PromSeriesValue`. Cada valor lleva el `metric` (etiquetas) y un `value` (float o string).
>
> Implementación: `tools/reading.py:query_prometheus_instant`. Internamente llama `PrometheusClient.instant_query(query)` que va a `GET /api/v1/query`.

## 🛠️ `query_prometheus_range(query, minutes)`

> [!example] Cómo se usa
> ```text
> Tool: query_prometheus_range
> Args: { "query": "rate(node_network_receive_bytes_total[1m])", "minutes": 30 }
> ```
> Devuelve un `PromRangeResult` con `minutes`, `series_count` y valores. El step interno es `30s`. `minutes` está restringido por Pydantic a `[1, 360]`.

## 🛠️ `get_node_health(node)`

> [!example] Atajo común
> ```text
> Tool: get_node_health
> Args: { "node": "matrix" }
> ```
> Devuelve un `NodeHealth(node, cpu_pct, memory_pct)`. Internamente ejecuta dos consultas instant y devuelve el primer valor de cada una. `node` está restringido a `Literal["leia", "matrix", "sauron", "heimdall", "fallback"]`.
>
> Implementa la fórmula clásica:
> - **CPU %** = `100 - avg by(instance) ( rate(node_cpu_seconds_total{mode="idle"}[5m]) ) * 100`
> - **Memory %** = `100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)`

## 🧩 Tipos de retorno

```python
class PromSeriesValue(BaseModel):
    metric: dict[str, str]
    value: float | str | None

class PromInstantResult(BaseModel):
    query: str
    series_count: int
    values: list[PromSeriesValue]

class PromRangeResult(BaseModel):
    query: str
    minutes: int
    series_count: int
    values: list[PromSeriesValue]

class NodeHealth(BaseModel):
    node: Literal[...]
    cpu_pct: float
    memory_pct: float
```

> [!info] Truncado defensivo
> Los strings se truncan a 500 caracteres (`_truncate` en reading.py) para evitar inflar la ventana del LLM con etiquetas Prometheus largas.

## 🧪 Errores

> [!warning] Ante un error de Prometheus, no excepción → ToolError
> Si `PrometheusQueryError` salta, la tool devuelve un `ToolError(source="prometheus", message=...)` en lugar de propagar la excepción. Esto permite que el LLM siga razonando ("Prometheus está caído, no puedo confirmar CPU"). El error se ve también en `lobster_errors_total`.

## 🔗 Conexión con el cliente HTTP

```python
class PrometheusClient:
    def __init__(self, base_url, timeout_seconds=5.0):
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout_seconds)
```

→ Ver [[../08-Infraestructura/03-Hosts-LeIA-Sauron-Heimdall#Prometheus en Sauron]] para la configuración del servicio.
