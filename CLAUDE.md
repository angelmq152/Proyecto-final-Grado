# CLAUDE.md

Guía para Claude Code (claude.ai/code) sobre este repo.

## Qué es este repo

`Proyecto-final-Grado` es el repo paraguas del TFG SaaSphere. Está organizado **por nodos del homelab**, donde cada nodo replica el filesystem real (`opt/`, `etc/`) de su máquina.

## Estructura

- `LeIA/` — Máquina donde corre el agente IA. **`LeIA/opt/lobster/`** contiene el código completo del agente Lobster (FastAPI + aiogram + Qwen3 vía Ollama). Para detalles de arquitectura, prompts, mutations, etc., consulta `LeIA/opt/lobster/CLAUDE.md` — es el CLAUDE.md específico del agente, con toda la información que tenía el repo original.
- `Matrix/` — K3s + registry Docker (manifests YAML, docker-compose).
- `Sauron/` — Prometheus, Grafana, Loki, Alertmanager (docker-compose).
- `Heimdall/` — Gateway / VPN (placeholder, WireGuard pendiente).
- `docs/` — Memoria TFG, plantilla, glosario, revisiones, versiones anteriores.
- `obsidian/` — Vault Obsidian: `wiki/` (estructura técnica del proyecto), `TFG_Fase*.md` (capítulos por fase), `legacy-TFG/` (notas antiguas importadas).
- `prompts-chat/` — Prompts y contexto para sesiones IA.

## Trabajar con el agente Lobster

Todos los comandos `uv` se ejecutan desde `LeIA/opt/lobster/`:

```bash
cd LeIA/opt/lobster
uv sync                          # install
uv run pytest                    # tests
uv run pytest tests/test_foo.py  # un test concreto
uv run ruff check .              # lint
uv run ruff format .             # format
uv run mypy lobster_agent/       # type check
uv run lobster                   # servidor (necesita /etc/lobster/config.toml)
```

CLI:
```bash
uv run lobster ask "prompt"
uv run lobster decisions list
uv run lobster actions list
uv run lobster approvals list
uv run lobster state set normal|dry_run|paused
```

## Runtime actual

El servicio Lobster sigue ejecutándose desde **`/opt/openclaw/`** (no desde este repo). La migración del runtime (`systemd` unit, `/etc/lobster/config.toml`, `.venv`) se hará en una sesión aparte. Mientras tanto, este repo es la fuente para edición y commits; `/opt/openclaw/` se mantiene como working directory del servicio en vivo.

## Convenciones

- Operador y prompts: **español**.
- Los namespaces de tenant en K3s siguen `tenant-<nombre>` con label `saasphere.io/tenant=true`.
- Las mutaciones del agente sobre `kube-system` y similares están hard-blocked en `LeIA/opt/lobster/lobster_agent/domain/policy.py`.
