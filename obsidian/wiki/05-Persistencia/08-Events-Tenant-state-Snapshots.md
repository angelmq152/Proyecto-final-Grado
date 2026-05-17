---
title: Tablas auxiliares — events, tenant_state, metrics_snapshots
tags: [persistencia, events, tenant-state, snapshots]
---

# 📦 Tablas auxiliares

> [!abstract] Espacios reservados con uso variable
> Tres tablas que se incluyeron en el esquema para futuras capacidades pero se usan poco hoy. Documentadas para que el lector entienda **por qué están ahí** y no las confunda con tablas core.

## 🌊 `events`

```python
class Event(SQLModel, table=True):
    id: UUID (PK)
    timestamp: datetime
    source: str            # "k8s_watcher" | "alertmanager_webhook" | ...
    severity: str
    target_namespace: str | None
    payload: dict (JSON)
    derived_decision_id: UUID | None (FK decisions.id)
```

> [!info] Para qué se diseñó
> Una bitácora de eventos externos que dispararon al agente, con link a la `Decision` resultante. Permitiría reconstruir "alerta X → decisión Y → acción Z".

> [!warning] No se llena hoy de forma consistente
> En la práctica el watcher y el webhook persisten información en `decisions` directamente. `events` queda como espacio para una refactorización futura — quizás cuando se añada métricas/eventos derivados de la cola FIFO de Fase 9.

## 🏢 `tenant_state`

```python
class TenantState(SQLModel, table=True):
    id: UUID (PK)
    timestamp: datetime
    namespace: str
    tier: str
    type: str
    pods_running: int
    cpu_avg_5m: float
    memory_avg_5m: float
    requests_last_hour: int
    errors_last_hour: int
    last_active: datetime | None
    is_scaled_to_zero: bool
```

> [!info] Idea
> Snapshots periódicos del estado de cada tenant para detectar tendencias (¿este tenant consume más cada semana?).

> [!warning] Hoy se reconstruye al vuelo
> El agente prefiere consultar Prometheus en tiempo real. Esta tabla queda como esqueleto para análisis offline / informes mensuales.

## 📊 `metrics_snapshots`

```python
class MetricsSnapshot(SQLModel, table=True):
    id: UUID (PK)
    timestamp: datetime
    node: str
    cpu_pct: float
    memory_pct: float
    disk_pct: float
    network_in_bps: int
    network_out_bps: int
    gpu_pct: float | None
    gpu_vram_pct: float | None
```

> [!info] Idea
> Snapshots de métricas del sistema almacenados localmente, independientes de Prometheus. Sería útil para reportes históricos en escenarios donde Sauron (Prom) cae.

> [!warning] No se rellena automáticamente
> Igual que `tenant_state`. Espacio reservado.

## 🧹 ¿Las quito o las mantengo?

> [!tip] Mejor mantenerlas
> Una migración Alembic para borrar tablas vacías introduciría riesgo en una BD productiva. Hoy ocupan 0 KB. Cuando se decida darles uso, ya están listas y migradas.

→ Ver [[09-Alembic-migraciones]] para el historial de cómo evolucionó este esquema.
