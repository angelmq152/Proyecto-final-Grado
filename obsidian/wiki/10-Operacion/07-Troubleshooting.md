---
title: Operación — Troubleshooting
tags: [operacion, troubleshooting, errores, debug]
---

# 🩹 Troubleshooting

> [!abstract] Síntomas → diagnóstico → remedio
> Tabla práctica de los problemas más frecuentes. Documenta el síntoma observable (en métricas, logs o Telegram) y el camino para resolverlo.

## 🚨 Síntomas y diagnóstico

### "Lobster no responde a Telegram"

| Causa | Comprobación | Remedio |
|---|---|---|
| Bot desactivado | `cat /etc/lobster/.env | grep TELEGRAM` | Set `LOBSTER_TELEGRAM__ENABLED=true` |
| Token inválido | logs `lobster.telegram.polling_failed` | Regenerar token con @BotFather |
| Usuario no whitelisted | logs `lobster.telegram.unauthorized` | Añadir ID a `allowed_user_ids` |
| Servicio caído | `systemctl status lobster` | `systemctl restart lobster` |

### "Daily summary no apareció"

| Causa | Comprobación | Remedio |
|---|---|---|
| Timeout | `lobster_scheduler_runs_total{case_use="daily_summary",outcome="timeout"}` | Aumentar `job_timeout` o investigar Ollama lentitud |
| Ollama caído | `curl localhost:11434/api/ps` | `systemctl restart ollama` |
| Modelo no descargado | `ollama list | grep 32b` | `ollama pull qwen3:32b` |
| Permisos vault | `ls -la /opt/lobster/obsidian/` | `chown -R lobster:lobster obsidian/` |

### "Las aprobaciones expiran sin que las haya visto"

| Causa | Comprobación | Remedio |
|---|---|---|
| Cuenta wrong en allowed_user_ids | logs `lobster.telegram.approval_stubbed` | Verificar el primer ID en la lista (es a quien se mandan las aprobaciones) |
| Bot muteado en Telegram | abre el chat con el bot | Re-activar notificaciones |
| Internet en LeIA | `ping api.telegram.org` | Revisar conectividad |

### "Latencia LLM alta"

| Causa | Comprobación | Remedio |
|---|---|---|
| GPU saturada | `nvidia-smi` en LeIA | Esperar; o bajar workload |
| Modelos compitiendo | `curl localhost:11434/api/ps` | Asegurar que la cola Fase 9 está activa |
| Swap activo | `free -h` | Ajustar `OLLAMA_MAX_LOADED_MODELS=1` |
| Disk pressure | `df -h /var/lib/ollama` | Limpiar otros modelos no usados |

### "Errores intermitentes en mutaciones"

| Causa | Comprobación | Remedio |
|---|---|---|
| K8s API no alcanzable | `kubectl --kubeconfig=/etc/lobster/kubeconfig get nodes` | Revisar VPN/red |
| RBAC insuficiente | logs `K8sClientError: ... 403 forbidden` | Re-aplicar `deploy/k8s/lobster-rbac.yaml` |
| Recurso no existe | logs `Failed to get Kubernetes resource ...` | El LLM se inventó nombre — refinar prompt |
| Pod sin owner | mensaje "standalone pod no se recreará" | Verificar si se quería ese comportamiento |

### "Alertas no llegan a Telegram (sólo al webhook de Lobster)"

| Causa | Comprobación | Remedio |
|---|---|---|
| Subroute `lobster` sin matchers captura todo | `docker logs alertmanager \| grep -c 'receiver=telegram'` → 0 | Hacer `telegram` también subroute con `continue: true` |
| Token o `chat_id` mal en `telegram_configs` | Disparar test: `curl -X POST localhost:9093/api/v2/alerts ...` y mirar logs | Verificar token con @BotFather; el bot debe haber recibido `/start` |
| Bot bloqueado o chat archivado | Abrir el chat con el bot | Desarchivar y desbloquear |
| Alertmanager no recargó tras editar yml | `docker logs alertmanager \| tail` (buscar `Completed loading`) | `curl -X POST localhost:9093/-/reload` o reiniciar contenedor |

→ Incidente completo documentado en `obsidian/monitoring/2026-05-17_alertmanager_routing_fix.md`.

### "Lobster consume mucha memoria"

| Causa | Comprobación | Remedio |
|---|---|---|
| Loki queue creciendo | `lobster_loki_queue_size` > 500 | Loki caído — revisar Sauron |
| SQLite WAL no checkpointing | `du -h /var/lib/lobster/state.db*` | `sqlite3 state.db "PRAGMA wal_checkpoint(TRUNCATE);"` |
| Modelo de Ollama cargado | nada que ver con Lobster process | Ollama se gestiona separado |

## 🔍 Comandos diagnóstico rápidos

```bash
# Estado general
sudo systemctl status lobster
curl localhost:8080/health

# Última actividad
uv run lobster decisions list --limit 5

# Errores recientes
uv run lobster actions list --status failed --limit 10

# Aprobaciones colgadas
uv run lobster approvals list --status pending

# Estado del modo
uv run lobster state get

# Inspección de SQLite directa
sqlite3 /var/lib/lobster/state.db ".schema decisions"
sqlite3 /var/lib/lobster/state.db "SELECT COUNT(*) FROM actions GROUP BY status;"

# Logs en vivo
sudo journalctl -u lobster -f
sudo journalctl -u lobster --since "10 minutes ago"
```

## 📊 Métricas que ayudan

```promql
# Lobster vivo?
lobster_uptime_seconds

# Último ciclo de health_loop hace cuánto?
time() - lobster_last_cycle_timestamp{case_use="health_loop_read"}

# Tasa de fallos
sum(rate(lobster_decisions_total{outcome="failed"}[10m]))
/ sum(rate(lobster_decisions_total[10m]))

# Latencia LLM p95 por modelo
histogram_quantile(0.95,
  sum(rate(lobster_llm_latency_seconds_bucket[10m])) by (le, model))

# Errores por componente
sum(rate(lobster_errors_total[5m])) by (component, severity)

# Loki queue creciendo?
lobster_loki_queue_size

# Aprobaciones acumulándose?
lobster_approvals_pending
```

## 🔁 Recuperación tras incidencia

> [!example] Procedimiento típico
> 1. `uv run lobster state set paused --reason "investigando X"` — para que no actúe.
> 2. Investigar logs y métricas.
> 3. Aplicar fix (en código, infra o Ollama).
> 4. Reiniciar: `systemctl restart lobster`.
> 5. Volver a `normal`: `uv run lobster state set normal`.
> 6. Verificar `decisions list` y `actions list` tras varios minutos.

→ Ver también `obsidian/TFG_Fase7_Lobster.md` para casos prácticos documentados.
