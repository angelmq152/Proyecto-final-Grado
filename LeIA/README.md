# LeIA

Nodo donde corre el **agente IA** del homelab SaaSphere.

## Servicios

- **Lobster** ([`opt/lobster/`](./opt/lobster)) — Agente orquestador. FastAPI (`/health`, `/metrics`, `/webhook/alert`) + bot de Telegram (aiogram v3) + SQLite. Toma decisiones autónomas/asistidas sobre el cluster K3s de Matrix (deploy/pause/resume de tenants, restart de pods, etc.).
- **Ollama** — Runtime de modelos locales. Sirve `qwen3:8b` (lectura/fast) y `qwen3:32b` (análisis/mutaciones) en `http://localhost:11434`. Configurado fuera de este repo de momento.

## Filesystem espejado

- `opt/lobster/` — Código del agente, manifests Jinja2 de tenants, migraciones Alembic, tests.
- `etc/` — Reservado para `lobster/config.toml` (no commiteado: contiene tokens de Telegram y Ollama).

## Quickstart

```bash
cd opt/lobster
uv sync
uv run lobster
```

El runtime de producción vive aún en `/opt/openclaw/` (mismo código, pendiente de migrar).
