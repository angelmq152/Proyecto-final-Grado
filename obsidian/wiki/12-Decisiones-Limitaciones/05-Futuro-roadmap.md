---
title: Futuro — roadmap
tags: [decisiones, roadmap, futuro, tfg]
---

# 🔮 Roadmap

> [!abstract] Lo que viene
> Ideas para futuras fases (post-TFG) o mejoras incrementales. Ordenadas por valor estimado.

## 🥇 Alta prioridad

### Wake-on-request

Detectar HTTP request a un tenant scaled-to-zero y dispararlo. Posibles caminos:
- KEDA con scaler HTTP.
- Middleware Traefik custom que llame `resume_tenant`.
- Sidecar listener que escuche SYN packets a los ports del Service.

> Beneficio: tenants free pueden hibernarse sin pérdida de UX.

### `change_tenant_tier`

Tool que solo patchea `resources.limits` y `ResourceQuota` sin destruir el tenant. Para subir/bajar de tier.

### Backup automático de SQLite

Cron diario:
```bash
sqlite3 state.db ".backup /backups/lobster-$(date +%F).db"
```
Y/o `litestream` para replicación continua a S3-compatible.

### Triaje de tool_requests

CLI `lobster tool-requests close <id> --status implemented` para gestionar el backlog del propio agente.

### Auth en `/admin/*`

Header `X-Lobster-Token` validado contra valor en config. Permite exponer `/admin/trigger` a otros sistemas (CI, CronJobs, …).

## 🥈 Media prioridad

### Cola con prioridades

Si en el futuro se demuestra que `alert_reactive` espera detrás de `daily_summary`, implementar `PriorityJobQueue`. Hoy no es problema.

### NetworkPolicies en plantillas

Añadir `default-deny` en cada plantilla Jinja2:
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
  namespace: {{ name }}
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
```

### Detección de tool calls como texto

Post-procesar la respuesta del LLM. Si detecta `<tools>...</tools>` patrón, reintenta o avisa al operador.

### `change_tenant_image`

Tool para actualizar la imagen Docker de un Deployment sin rehacer todo el tenant. Hoy se hace con `apply_manifest`.

### Histórico de `agent_state`

Tabla `agent_state_log` que registra cambios. Hoy solo hay la fila actual.

## 🥉 Baja prioridad

### CLI `lobster queue`

Ya planteado en Fase 9 pero aún no entregado:
```bash
lobster queue list
lobster queue drop <id>
```

### Dashboard nativo en Telegram

Comando `/dashboard` que envía screenshot del Grafana embebido o un resumen ASCII de las métricas clave.

### Multi-clúster

Soporte para varios `KubeConfig` selecionables por `CaseUse`. Requiere repensar policy y RBAC.

### OpenTelemetry tracing

Reemplazar structlog por OTel y enviar traces a Tempo. Visualización en Grafana de "decision → tools → mutation" como spans.

### Búsqueda vectorial en decisiones

Embeddings de `conclusion` + `prompt_summary` en `decisions`. Tool `search_decisions_semantic(query)` que use ANN.

### Cache de prompts caché-friendly

Estructurar los prompts para aprovechar el prompt caching de Ollama (si lo soportan en el futuro). Reducir latencia de health_loop.

## ❄️ Ideas que probablemente NO

> [!info] Out of scope para TFG
> - HA con leader election (Raft) → demasiado complejo, no aporta al TFG.
> - Multi-tenancy real con RBAC por operador → solo hay un operador.
> - SaaS comercial → no es el objetivo.
> - Migración a Postgres → SQLite es suficiente.

## 📝 Política de cambios

> [!warning] Trabajar en ramas dedicadas
> Cada feature mediana va en su propia rama. Tests deben pasar. Cambios al esquema SQL requieren migración Alembic. Cambios al system prompt requieren probar con tests de integración (al menos test_orchestrator).

## 🎯 Para el TFG (entregable)

> [!tip] Cierre esperado
> - Fases 1-9 documentadas y funcionales. ✅
> - Wiki completa (esta carpeta). ✅
> - Vídeo demo con casos reales. (Pendiente)
> - Memoria escrita TFG basada en estas fases + wiki. (Pendiente)

→ Cierra en [[06-Mapa-al-TFG]].
