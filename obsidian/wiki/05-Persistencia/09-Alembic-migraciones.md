---
title: Alembic — migraciones
tags: [persistencia, alembic, migraciones, esquema]
---

# 🧱 Alembic · Migraciones

> [!abstract] El esquema crece versionado
> Carpeta: `alembic/versions/`. Cada fase del proyecto añadió tablas o columnas. Aunque `SQLModel.metadata.create_all` se ejecuta al arrancar para crear todo desde cero, las migraciones existen para **bases existentes** que ya tenían datos en una versión anterior.

## 📋 Historia de migraciones

| Revisión | Archivo | Qué añade |
|---|---|---|
| 0001 | `0001_initial.py` | Tablas iniciales (`decisions`, `actions` legacy) |
| 0002 | `0002_add_tools_called_to_decisions.py` | Columna `tools_called` en `decisions` |
| 0003 | `0003_approvals_and_agent_state.py` | Tablas `approvals` y `agent_state` (Fase 4) |
| 0004 | `0004_normalize_enum_values.py` | Normaliza valores enum legacy (`ApprovalStatus.APPROVED` → `approved`) |
| 0005 | `0005_conversation_turns.py` | Tabla `conversation_turns` |
| 0006 | `0006_tool_requests.py` | Tabla `tool_requests` |
| 0007 | `0007_actions.py` | Esquema completo de `actions` (con FK a decisions/approvals) |

## ⚙️ Configuración

`alembic.ini` en la raíz. La URL se inyecta dinámicamente en `alembic/env.py` desde `Settings.database.url`.

## 🚀 Aplicar migraciones

> [!example] En arranque normal
> ```bash
> uv run lobster db migrate
> # Database schema is up to date.
> ```
>
> O directamente:
> ```bash
> uv run alembic upgrade head
> ```

> [!warning] El `lifespan` también lo hace
> En `main.py`:
> ```python
> await create_db_schema(engine)
> ```
> Esto es `SQLModel.metadata.create_all` — **no aplica migraciones Alembic**, solo CREATE TABLE IF NOT EXISTS. En la práctica:
> - Para una base **nueva** → ambos caminos convergen.
> - Para una base **existente** que requiere ALTER → necesitas `alembic upgrade`.

## 🔄 Generar una nueva migración

```bash
# Después de modificar models.py:
uv run alembic revision --autogenerate -m "add foo to bar"
# Revisa el archivo generado en alembic/versions/
uv run alembic upgrade head
```

> [!tip] Revisar el autogenerate
> Alembic puede inferir CREATE COLUMN bien, pero suele equivocarse con renames y constraints. Revisa siempre antes de aplicar.

## 🧪 Tests

`tests/test_alembic.py` valida que `alembic upgrade head` desde cero produce un esquema equivalente al de `SQLModel.metadata.create_all`.

## 🔙 Downgrade

```bash
uv run alembic downgrade -1
```

> [!danger] En producción NO se baja
> Si una migración borra columnas, downgrade pierde datos. En la práctica, una vez aplicada una migración a la base de SaaSphere, no se rueda atrás — se hace una migración nueva para corregir.
