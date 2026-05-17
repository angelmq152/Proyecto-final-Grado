---
title: SQLite — Esquema global
tags: [persistencia, sqlite, sqlmodel, esquema]
---

# 🗄️ SQLite · Esquema global

> [!abstract] Una base, 9 tablas
> Archivo: `lobster_agent/persistence/models.py`. SQLite local en `/var/lib/lobster/state.db`. ORM con SQLModel (= SQLAlchemy + Pydantic). Driver async = `aiosqlite`.

## 📐 Diagrama del esquema

```mermaid
erDiagram
    decisions ||--o{ actions : "decision_id"
    decisions ||--o{ events : "derived_decision_id"
    approvals ||--o| actions : "approval_id"
    decisions {
      UUID id PK
      datetime timestamp
      str case_use
      str model_used
      bool think_mode
      str prompt_summary
      str conclusion
      int tokens_input
      int tokens_output
      int latency_ms
      json tools_called
      json derived_actions
    }
    actions {
      string id PK
      datetime created_at
      datetime updated_at
      str action_type
      str namespace
      str target
      str severity
      str status
      str payload
      str result
      string decision_id FK
      string approval_id
      bool dry_run
    }
    approvals {
      string id PK
      datetime requested_at
      str case_use
      str action_type
      json action_payload
      str tenant_namespace
      str severity
      str status
      datetime expires_at
      datetime decided_at
      int decided_by_user_id
      str decision_reason
      int telegram_chat_id
      int telegram_message_id
      int reminder_count
    }
    tool_requests {
      int id PK
      datetime requested_at
      str case_use
      str user_query
      str tool_name_suggested
      str description
      str suggested_inputs
      str status
      str decision_id
    }
    conversation_turns {
      int id PK
      int chat_id
      str role
      str content
      str case_use
      datetime recorded_at
    }
    agent_state {
      int id PK
      str mode
      str reason
      datetime changed_at
      int changed_by_user_id
    }
    events {
      UUID id PK
      datetime timestamp
      str source
      str severity
      str target_namespace
      json payload
      UUID derived_decision_id FK
    }
    tenant_state {
      UUID id PK
      datetime timestamp
      str namespace
      str tier
      str type
      int pods_running
      float cpu_avg_5m
      float memory_avg_5m
      int requests_last_hour
      int errors_last_hour
      datetime last_active
      bool is_scaled_to_zero
    }
    metrics_snapshots {
      UUID id PK
      datetime timestamp
      str node
      float cpu_pct
      float memory_pct
      float disk_pct
      int network_in_bps
      int network_out_bps
      float gpu_pct
      float gpu_vram_pct
    }
```

## 🚀 Creación de la base

```python
async def create_db_schema(engine: AsyncEngine):
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
```

`SQLModel.metadata` ya conoce todas las tablas por el import lateral en `persistence/db.py`:

```python
from lobster_agent.persistence import models as _models  # noqa: F401
```

## ⚙️ PRAGMAs SQLite

```python
@event.listens_for(engine.sync_engine, "connect")
def enable_sqlite_pragmas(dbapi_connection, _):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
```

> [!info] Por qué WAL
> Permite lecturas concurrentes mientras se escribe. Esencial porque el scheduler + watcher + telegram + CLI pueden estar accediendo simultáneamente.

> [!warning] foreign_keys=ON
> SQLite **no aplica FK** por defecto. Esto las activa para que `actions.decision_id` y `events.derived_decision_id` se validen.

## 🧬 `StrEnumValueType` — el truco de enums

```python
class StrEnumValueType(TypeDecorator[str]):
    impl = String
    def process_bind_param(self, value, dialect):
        if isinstance(value, self.enum_type):
            return value.value
        ...
    def process_result_value(self, value, dialect):
        return _normalize_enum_string(self.enum_type, value)
```

> [!tip] Por qué este TypeDecorator existe
> Cuando SQLModel persiste un `StrEnum`, guarda el `.value` (string limpio) pero al leer lo reconvierte. Versiones antiguas guardaron `ApprovalStatus.APPROVED` literalmente como string "ApprovalStatus.APPROVED". Este decorator normaliza ambos casos.

## 📍 Configuración

```python
class DatabaseConfig(BaseModel):
    url: str = "sqlite+aiosqlite:////var/lib/lobster/state.db"
```

Cambiable en `[database].url` del TOML o `LOBSTER_DATABASE__URL` en env.

## 🛠️ Mantenimiento

### Backup manual
```bash
sqlite3 /var/lib/lobster/state.db ".backup '/tmp/lobster-backup-$(date +%F).db'"
```

### Vacuum
```bash
sqlite3 /var/lib/lobster/state.db "VACUUM;"
```

### Inspección rápida
```bash
sqlite3 /var/lib/lobster/state.db "SELECT case_use, COUNT(*) FROM decisions GROUP BY case_use ORDER BY 2 DESC;"
```

→ Detalle de cada tabla en notas siguientes.
