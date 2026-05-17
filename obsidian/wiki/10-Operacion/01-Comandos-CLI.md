---
title: Operación — Comandos CLI
tags: [operacion, cli, typer]
---

# 💻 CLI · `uv run lobster …`

> [!abstract] Typer con subcomandos
> Archivo: `lobster_agent/cli.py`. `app = typer.Typer()` con varios `add_typer` para `decisions`, `db`, `approvals`, `actions`, `state`, `tool-requests`, `tenants`. Pensado para el operador en LeIA por SSH.

## 🎯 Comando principal

```bash
uv run lobster ask "qué pods están en CrashLoopBackOff?"
uv run lobster ask "explícame el último daily summary" --case conversation
uv run lobster ask "..." --no-tools                    # solo dummy tools
```

## 🗂️ Subcomando `decisions`

```bash
uv run lobster decisions list --limit 20 [--show-reasoning]
```

→ Lista las últimas N filas de `decisions` con timestamp, id, case_use, modelo, think y latencia.

## 🛢️ Subcomando `db`

```bash
uv run lobster db migrate
# Database schema is up to date.
```

> [!warning] No corre Alembic
> Solo ejecuta `SQLModel.metadata.create_all`. Para migraciones reales usa `uv run alembic upgrade head`.

## ✋ Subcomando `approvals`

```bash
uv run lobster approvals list [--status pending|approved|rejected|expired]
uv run lobster approvals show <id>          # JSON detallado
uv run lobster approvals create-test --action-type restart_pod --severity normal --payload '{}'
```

> [!tip] `create-test` para probar Telegram
> Útil para verificar el bot y el flujo aprobación sin tocar K8s. Crea una aprobación falsa que aparecerá en Telegram.

## 🧾 Subcomando `actions`

```bash
uv run lobster actions list [--status failed|completed|...]
uv run lobster actions show <id>            # JSON
uv run lobster actions stats                # conteo por estado
```

## 🎚️ Subcomando `state`

```bash
uv run lobster state get
# normal changed_at=2026-05-15T22:18:43+00:00 reason=-

uv run lobster state set normal
uv run lobster state set dry_run --reason "ensayo"
uv run lobster state set paused --reason "incidente"
```

## 🔧 Subcomando `tool-requests`

```bash
uv run lobster tool-requests list [--status pending|implemented|...] --limit 20
```

## 🏢 Subcomando `tenants`

```bash
uv run lobster tenants list
uv run lobster tenants show <namespace>           # alias de health
uv run lobster tenants deploy --type wordpress --name my-blog --tier free --hostname my-blog.saasphere.local --admin-email me@example.com
uv run lobster tenants delete --namespace my-blog --confirm my-blog
uv run lobster tenants pause my-blog
uv run lobster tenants resume my-blog
uv run lobster tenants health my-blog
```

## 🧠 Internamente

> [!info] Cada subcomando abre su propia sesión SQLite
> CLI no comparte la sesión con el servidor. Si el servidor está parado, el CLI **funciona** (lee/escribe SQLite directo). Esto es útil cuando Lobster está caído y quieres inspeccionar `decisions`.

## 🚦 Casos comunes

> [!example] Inspeccionar el último daily summary
> ```bash
> uv run lobster decisions list --limit 5 --show-reasoning
> # busca el de case_use=daily_summary y mira su conclusion
> ```

> [!example] Pausar todo de emergencia
> ```bash
> uv run lobster state set paused --reason "ollama caído"
> # confirma:
> uv run lobster state get
> ```

> [!example] Verificar BD tras restore
> ```bash
> uv run lobster actions stats
> # completed: 142
> # failed: 3
> # ...
> ```

→ Operación HTTP en [[03-Endpoints-HTTP]]. Operación Telegram en [[02-Comandos-Telegram]].
