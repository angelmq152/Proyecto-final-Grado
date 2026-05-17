# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                         # install dependencies
uv run pytest                   # run all tests
uv run pytest tests/test_foo.py # run a single test file
uv run pytest -k test_name      # run a specific test
uv run ruff check .             # lint
uv run ruff format .            # format
uv run mypy lobster_agent/           # type check
uv run lobster                 # start the server (requires /etc/lobster/config.toml)
uv run lobster ask "prompt"    # one-shot CLI query
uv run lobster decisions list  # inspect recent agent decisions
uv run lobster actions list    # inspect the mutation ledger
uv run lobster approvals list  # inspect pending approvals
uv run lobster state set normal|dry_run|paused  # change agent mode
```

## Architecture

Lobster is an AI infrastructure orchestration agent for the SaaSphere homelab. It monitors K3s tenant namespaces and autonomously manages container lifecycle using Qwen3 running on a local Ollama instance.

### Entry point and server

`lobster_agent/main.py` creates a FastAPI app with a `lifespan` that wires all dependencies together. `lobster_agent/cli.py` exposes the same core functionality as a Typer CLI. The HTTP server exposes `/health` and `/metrics` only.

### Agent layer (`lobster_agent/agent/`)

- **`orchestrator.py` — `LobsterAgent`**: The main agent class. Receives a `CaseUse` (mode) and routes to the appropriate Qwen3 model variant (`qwen3:8b` for fast/read tasks, `qwen3:32b` for analysis/mutations). Think mode (Qwen3's `/think` extension, streamed via Ollama's OpenAI-compatible API) is enabled for most mutation and deep analysis case uses. Agent instances are cached by `(case_use, model_name, think)`.
- **`routing.py` — `CaseUse`**: StrEnum of all agent operating modes. `select_model()` and `use_think_mode()` define per-mode model routing.
- **`mutations/context.py` — `MutationContext`**: Common execution envelope for all mutation tools. Flow: policy validation → severity assignment → optional approval gate → optional dry-run → action ledger recording → executor call.
- **`approvals.py` — `ApprovalManager`**: Sends Telegram notifications for mutations requiring human sign-off and blocks via `wait_for_decision()` until the user approves or rejects via inline keyboard callback.
- **`tools/`**: Split into `reading.py` (Prometheus/Loki/K8s/Alertmanager queries), `mutations/k8s.py` (pod/deployment mutations), `mutations/tenant.py` (deploy/delete/pause/resume tenants from Jinja2 manifests), `memory.py` (search past decisions), `meta.py` (request_new_tool), and `dummy.py` (debug tools for smoke tests).
- **`prompts/system.py`**: Builds the system prompt per `CaseUse`. Missions are written in Spanish (the operator language).

### Tool dispatch

`_build_tools_for_case()` in `orchestrator.py` selects which tools are registered for each `CaseUse`. `SMOKE_TEST` and `enable_dummy_tools=True` both fall back to dummy tools only.

### Policy (`lobster_agent/domain/policy.py`)

`validate()` is called before every mutation. Key rules:
- System namespaces (`kube-system`, etc.) are always hard-blocked.
- Mutations are only allowed in namespaces labeled `saasphere.io/tenant=true`.
- `FORBIDDEN_MANIFEST_KINDS` (Secret, ServiceAccount, Role/Binding, Pod) are blocked.
- Manifests must declare cpu+memory resource limits unless `enforce_resource_limits=False`.
- `ACTION_SEVERITIES` maps action types to `AUTONOMOUS | NORMAL | CRITICAL`. AUTONOMOUS bypasses approval, NORMAL and CRITICAL require Telegram approval (CRITICAL has a longer timeout and periodic reminders).

### Persistence (`lobster_agent/persistence/`)

SQLite via SQLModel + aiosqlite. Schema auto-created on startup; migrations in `alembic/versions/`. Tables: `decisions`, `actions`, `approvals`, `agent_state`, `conversation_turns`, `tool_requests`, `events`, `tenant_state`, `metrics_snapshots`.

`AgentMode` (normal / dry_run / paused) is stored in `agent_state` (single-row table, id=1). When `paused`, `LobsterAgent.run()` returns immediately without calling the LLM.

### Telegram (`lobster_agent/telegram/`)

aiogram v3 bot. `bot.py` manages lifecycle. `handlers.py` routes commands (`/status`, `/pending`, `/pause`, `/resume`, `/kill`, `/think`, `/forget`, `/toolrequests`) and free-text (dispatched as `CaseUse.CHAT` or `CaseUse.THINK`). Approval callbacks are handled by inline keyboard buttons (`approve:<id>` / `reject:<id>`). `memory.py` — `ConversationMemory` maintains a two-layer per-chat sliding window of turns stored in `conversation_turns`.

### Configuration

`Settings` in `lobster_agent/config.py` loads from (highest priority first): env vars with `LOBSTER_` prefix and `__` as nested delimiter, `/etc/lobster/.env`, `/etc/lobster/config.toml`, then pydantic defaults.

### Tenant manifests

Jinja2 templates in `lobster_agent/manifests/` (`web_app.yaml.j2`, `wordpress.yaml.j2`, `static_site.yaml.j2`). `ManifestRenderer` in `lobster_agent/agent/mutations/manifests.py` renders and applies them via `K8sClient`. Tenant namespaces follow the `tenant-<name>` convention and must carry the `saasphere.io/tenant=true` label for policy to allow mutations.
