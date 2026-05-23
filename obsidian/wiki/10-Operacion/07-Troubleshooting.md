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

### "Static site nuevo devuelve 403 Nginx"

| Causa | Comprobación | Remedio |
|---|---|---|
| Sin `index.html` aún subido | `ls /srv/k3s-pvs/lobster-static/<name>/html/` | `scp ./index.html angel@leia:/srv/k3s-pvs/lobster-static/<name>/html/` |
| Pod ve directorio vacío | `kubectl exec -n <name> deploy/<name> -- ls /usr/share/nginx/html/` | Si está vacío y el host SÍ tiene archivos, mira el siguiente caso |
| PVC sin bind | `kubectl get pvc -n <name>` | Debe estar `Bound` con `STORAGECLASS=smb-lobster-static` |
| PVC ligada a StorageClass antigua | `kubectl get pvc -o yaml ...` | Migrar siguiendo el postmortem |
| Pod programado en LeIA | `kubectl get pod -n <name> -o wide` | Falta nodeAffinity `saasphere.io/workload=true` — revisa la plantilla |

> Ver postmortem completo en [[../09-Tenants/07-Postmortem-Static-Site-SMB]].

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

### Problemas con K3s en los nodos

#### Puerto 6444 retenido (proceso zombie)

| Causa | Comprobación | Remedio |
|---|---|---|
| `k3s.service` standalone dejó `kube-apiserver` como zombie | `sudo ss -tlnp \| grep 6444` | `sudo fuser -k 6444/tcp` y luego arrancar el servicio correcto |
| k3s-agent no arranca en matrix | `sudo journalctl -u k3s-agent -n 50` | Verificar que `k3s.service` está parado y deshabilitado; `sudo systemctl disable --now k3s` |

```bash
# Diagnóstico de puertos ocupados en matrix (ejecutar como root en 192.168.1.202)
sudo ss -tlnp | grep -E "6443|6444"
sudo systemctl status k3s k3s-agent
```

#### TLS mismatch tras restart de k3s

| Causa | Comprobación | Remedio |
|---|---|---|
| k3s regeneró certificados al reiniciar | `kubectl get nodes` → `x509: certificate signed by unknown authority` | El kubeconfig de Lobster apunta a `https://192.168.1.200:6443` (leia); si leia no se reinició, el certificado no cambia |
| Kubeconfig con IP incorrecta | `grep server /etc/lobster/kubeconfig` | Debe ser `https://192.168.1.200:6443` — si es `.202`, corregir con `sed -i` |

```bash
# Verificar la IP en el kubeconfig de Lobster
grep server /etc/lobster/kubeconfig
# Respuesta esperada: server: https://192.168.1.200:6443

# Verificar que la API responde
curl -k https://192.168.1.200:6443/healthz
# → ok
```

#### Kubeconfig apuntando al nodo equivocado

> [!danger] Si /etc/lobster/kubeconfig apunta a matrix (192.168.1.202:6443) en lugar de a leia (192.168.1.200:6443), Lobster pierde toda conectividad K8s cuando matrix cae — exactamente el escenario en el que más falta hace el agente.

```bash
# Síntoma: Lobster no puede ver nodos cuando matrix está apagado
kubectl --kubeconfig=/etc/lobster/kubeconfig get nodes
# → connection refused / no route to host

# Corrección:
sudo sed -i 's|https://192.168.1.202:6443|https://192.168.1.200:6443|g' \
  /etc/lobster/kubeconfig

# Verificación:
kubectl --kubeconfig=/etc/lobster/kubeconfig get nodes
# → leia (control-plane), matrix, fallback todos Ready
```

> Ver postmortem completo en [[09-Postmortem-Failover-Kubeconfig-2026-05-23]].

#### Conflicto k3s-server vs k3s-agent en el mismo nodo

| Causa | Comprobación | Remedio |
|---|---|---|
| Nodo worker tiene tanto `k3s.service` como `k3s-agent.service` activos | `sudo systemctl is-active k3s k3s-agent` | Parar y deshabilitar `k3s.service`; solo debe correr `k3s-agent` en workers |

```bash
# En matrix (192.168.1.202) — solo debe correr k3s-agent:
sudo systemctl stop k3s
sudo systemctl disable k3s
sudo systemctl status k3s-agent
```

### "Lobster detecta nodo como inoperable pero el nodo está encendido"

| Causa | Comprobación | Remedio |
|---|---|---|
| `is_node_alive` devuelve `api_available=False` | `grep api_available` en los logs | El nodo está encendido pero la API K8s no responde — revisar k3s en leia |
| LLM dice "fallback inoperable" | Ver respuesta en Telegram | Bug de prompt resuelto — actualizar a versión ≥ 2026-05-23 |

```bash
# Verificar que el API server de k3s está corriendo en LeIA
sudo systemctl status k3s
curl -k https://192.168.1.200:6443/healthz
# → ok

# Ver el último ciclo de health_loop y su diagnóstico de nodos
uv run lobster decisions list --limit 5
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
