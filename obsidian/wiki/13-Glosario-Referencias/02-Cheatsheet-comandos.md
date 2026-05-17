---
title: Cheatsheet de comandos
tags: [glosario, cheatsheet, comandos, operacion]
---

# 🎴 Cheatsheet de comandos

> [!abstract] Toda la operación en una hoja
> Comandos más usados, agrupados por superficie.

## 🐚 CLI

```bash
# Una sola pregunta al agente
uv run lobster ask "qué pods están en CrashLoopBackOff?"
uv run lobster ask "..." --case conversation        # qwen3:32b + think
uv run lobster ask "..." --no-tools                  # solo dummy tools

# Modos del agente
uv run lobster state get
uv run lobster state set normal
uv run lobster state set dry_run --reason "ensayo"
uv run lobster state set paused  --reason "incidente"

# Decisiones
uv run lobster decisions list --limit 20
uv run lobster decisions list --limit 5 --show-reasoning

# Acciones (mutaciones)
uv run lobster actions list --status failed
uv run lobster actions show <id>
uv run lobster actions stats

# Aprobaciones
uv run lobster approvals list --status pending
uv run lobster approvals show <id>
uv run lobster approvals create-test --action-type restart_pod --severity normal

# Tool requests
uv run lobster tool-requests list --status pending

# Tenants
uv run lobster tenants list
uv run lobster tenants show tenant-acme
uv run lobster tenants health tenant-acme
uv run lobster tenants pause tenant-acme
uv run lobster tenants resume tenant-acme
uv run lobster tenants delete --namespace tenant-acme --confirm tenant-acme
uv run lobster tenants deploy \
    --type wordpress --name my-blog --tier free \
    --hostname my-blog.saasphere.local --admin-email me@example.com

# DB
uv run lobster db migrate
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "..."

# Test & quality
uv run pytest
uv run pytest tests/test_orchestrator.py
uv run pytest -k test_restart_pod
uv run ruff check .
uv run ruff format .
uv run mypy lobster_agent/

# Servidor
uv run lobster                    # arranca FastAPI + scheduler + watcher
```

## 📱 Telegram

| Comando | Acción |
|---|---|
| `/start` | Bienvenida |
| `/help` | Lista de comandos |
| `/status` | Estado actual |
| `/pending` | Aprobaciones pendientes |
| `/show <id>` | Detalle de aprobación |
| `/pause [razón]` | Modo dry_run |
| `/resume` | Modo normal |
| `/kill [razón]` | Modo paused |
| `/think <pregunta>` | Razonamiento profundo |
| `/forget` | Limpiar historial chat |
| `/toolrequests` | Solicitudes de tools |
| Texto libre | CaseUse.CHAT |

## 🌐 HTTP

```bash
# Salud
curl http://localhost:8080/health

# Métricas Prom
curl http://localhost:8080/metrics

# Forzar webhook (test)
curl -X POST http://localhost:8080/webhook/alert \
  -H "Content-Type: application/json" \
  -d '{"status":"firing","alerts":[]}'

# Listar jobs del scheduler
curl http://localhost:8080/admin/jobs | jq

# Forzar un job ahora
curl -X POST http://localhost:8080/admin/trigger/health_loop
curl -X POST http://localhost:8080/admin/trigger/daily_summary
```

## 🗄️ SQLite

```bash
DB=/var/lib/lobster/state.db

# Esquema
sqlite3 $DB ".tables"
sqlite3 $DB ".schema decisions"

# Conteos
sqlite3 $DB "SELECT case_use, COUNT(*) FROM decisions GROUP BY case_use ORDER BY 2 DESC;"
sqlite3 $DB "SELECT status, COUNT(*) FROM actions GROUP BY status;"
sqlite3 $DB "SELECT mode, reason, changed_at FROM agent_state;"

# Aprobaciones pendientes
sqlite3 $DB "SELECT id, action_type, severity, expires_at FROM approvals WHERE status='pending';"

# Última conversación
sqlite3 $DB "SELECT recorded_at, role, content FROM conversation_turns ORDER BY id DESC LIMIT 20;"

# Backup
sqlite3 $DB ".backup /tmp/lobster-$(date +%F).db"

# Vacuum
sqlite3 $DB "VACUUM;"
sqlite3 $DB "PRAGMA wal_checkpoint(TRUNCATE);"
```

## ☸️ Kubectl con kubeconfig de Lobster

```bash
KC=/etc/lobster/kubeconfig

kubectl --kubeconfig=$KC get nodes
kubectl --kubeconfig=$KC get pods --all-namespaces
kubectl --kubeconfig=$KC get ns -l saasphere.io/tenant=true
kubectl --kubeconfig=$KC auth can-i delete pods -n kube-system     # no
kubectl --kubeconfig=$KC auth can-i patch deployments -n tenant-acme  # yes

# Taint en fallback (solo una vez al provisionar)
kubectl --kubeconfig=$KC taint nodes fallback saasphere/role=fallback:NoSchedule
```

## 🦙 Ollama

```bash
# Estado
curl -s http://localhost:11434/api/ps | jq

# Listar modelos
ollama list

# Descargar
ollama pull qwen3:8b
ollama pull qwen3:32b

# Eliminar
ollama rm qwen3:32b

# Health
curl -s http://localhost:11434/api/tags
```

## 🚀 Systemd

```bash
sudo systemctl status lobster
sudo systemctl restart lobster
sudo journalctl -u lobster -f
sudo journalctl -u lobster --since "30 min ago"

sudo systemctl status ollama
sudo systemctl restart ollama
```

## 📊 PromQL útiles

```promql
# Vivo?
lobster_uptime_seconds

# Sin actividad?
time() - max(lobster_last_cycle_timestamp)

# Tasa fallos
sum(rate(lobster_decisions_total{outcome="failed"}[10m]))
/ sum(rate(lobster_decisions_total[10m]))

# p95 LLM
histogram_quantile(0.95,
  sum(rate(lobster_llm_latency_seconds_bucket[10m])) by (le, model))

# Tokens/h
sum(rate(lobster_llm_tokens_total[1h])) * 3600

# Aprobaciones pendientes
lobster_approvals_pending

# Cola Loki
lobster_loki_queue_size
```

## 🪵 LogQL útiles

```logql
{service="lobster"}
{service="lobster"} | json | level="error"
{service="lobster"} | json | event="lobster.decision.completed"
{service="lobster"} | json | event="lobster.decision.completed" | case_use="daily_summary"
{service="lobster"} | json | latency_ms > 60000
```
