---
title: Stack tecnológico
tags: [arquitectura, stack, dependencies, python313]
---

# 🧱 Stack tecnológico

> [!abstract] Stack completo en una tabla
> Python 3.13 puro, gestionado con `uv`. Sin frameworks pesados — cada librería se eligió por ser **mínima, async-native y bien tipada**.

## 📦 Dependencias de runtime

| Dependencia | Versión | Para qué |
|---|---|---|
| `python` | ≥ 3.13 | Lenguaje base |
| `uv` | latest | Gestor de paquetes, lockfile y venv |
| `fastapi` | ≥ 0.136.1 | Servidor HTTP (`/health`, `/metrics`, `/webhook`) |
| `uvicorn[standard]` | ≥ 0.46 | ASGI runner |
| `pydantic-ai-slim[openai]` | ≥ 1.93 | Framework agéntico LLM |
| `httpx` | ≥ 0.28 | Cliente HTTP async (Prom, Loki, AM, Ollama) |
| `structlog` | ≥ 25.5 | Logging estructurado JSON |
| `prometheus-client` | ≥ 0.25 | Exposición de métricas |
| `pydantic-settings` | ≥ 2.14 | Configuración con env + TOML |
| `sqlmodel` | ≥ 0.0.38 | ORM (SQLAlchemy + Pydantic) |
| `aiosqlite` | ≥ 0.22 | Driver SQLite async |
| `alembic` | ≥ 1.18 | Migraciones de esquema |
| `typer` | ≥ 0.25 | CLI (`uv run lobster …`) |
| `lightkube` | ≥ 0.19 | Cliente K8s async puro Python |
| `lightkube-models` | ≥ 1.35.0.8 | Tipados de recursos K8s |
| `cryptography` | ≥ 48 | TLS interno y SSL en httpx |
| `aiogram` | ≥ 3.13 | Bot Telegram async (v3) |
| `pyyaml` | ≥ 6.0 | Parse de manifests |
| `jinja2` | ≥ 3.1 | Templating de manifests de tenants |
| `apscheduler` | ≥ 3.10 | Scheduler con cron y intervals |
| `pytz` | ≥ 2024.1 | Timezones para APScheduler |

## 🔧 Dependencias de desarrollo

| Dep | Para qué |
|---|---|
| `pytest`, `pytest-asyncio`, `pytest-cov` | Test runner async |
| `ruff` | Lint y format (line-length 100, target py313) |
| `mypy` | Type check estricto (`strict = true`) |
| `respx` | Mock de httpx en tests |

## 🚦 Estilo y calidad

> [!tip] Reglas internas
> - `mypy --strict` debe pasar siempre (`ignore_missing_imports = true`).
> - `ruff` con `select = ["E", "F", "I", "UP"]` — errores, warnings, imports ordenados, upgrades Py.
> - `pytest` con `asyncio_mode = "auto"` — todos los tests son async sin decoradores.
> - **40+ archivos de tests** cubren agente, repos, policy, tools, telegram, scheduler, watcher.

## 🎯 Por qué este stack y no otro

→ Ver [[../12-Decisiones-Limitaciones/01-Decisiones-arquitectura#Stack]] para el "por qué".

Pinceladas:

- **FastAPI sobre Flask** → async nativo, Pydantic-friendly, OpenAPI gratis.
- **lightkube sobre `kubernetes`** → la oficial es sync, lightkube es async puro Python y mucho más liviana.
- **SQLite sobre Postgres** → un homelab no necesita un RDBMS de red; WAL + foreign_keys cubren el caso.
- **structlog sobre stdlib logging** → JSON estructurado por defecto, perfecto para Loki.
- **APScheduler sobre cron del SO** → cron no puede llamar funciones Python in-process con timeouts y métricas.
- **Pydantic-AI sobre LangChain** → mucho más simple, deps mínimas, tipado de extremo a extremo.
