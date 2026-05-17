---
title: Mejoras técnicas (infra, IA, código)
tags: [mejoras, tecnicas, roadmap]
---

# 🔧 Mejoras técnicas

> [!abstract] Lo que el código y la infra podrían hacer mejor
> Propuestas concretas agrupadas por dominio. Algunas vienen del PDF (explícitamente mencionadas), otras emergen al cruzar el PDF con el código actual.

## 🛡️ Resiliencia y alta disponibilidad

### T-01 — Fallback LLM externo cuando Ollama local cae

> [!danger] Crítica (mencionada en PDF página 18)
> *"La limitación es la capacidad del hardware, por lo que se contempla el uso de APIs externas como alternativa de respaldo para casos que superen las capacidades locales."*
>
> Hoy, si Ollama cae o la GPU falla, Lobster queda muerto.

**Propuesta**:
- Añadir `CloudLLMConfig` con providers: `anthropic` (Claude Sonnet 4.6 / Haiku 4.5) y `openai` (GPT-5.4 mini).
- Probe periódico a `localhost:11434/api/ps`. Si falla 3 veces consecutivas → activar fallback cloud.
- Métrica `lobster_llm_provider{provider="ollama|anthropic|openai"}`.
- Costes asumidos en el PDF: ~100€/mes API en producción.

→ Permite cumplir el requisito R-04 del PDF.

### T-02 — Backup automático del estado SQLite a S3

> [!warning] Importante
> Hoy `state.db` solo vive en LeIA. Si LeIA pierde disco → adiós a todo el ledger.
>
> El PDF (página 13) menciona *"Almacenamiento backups (Hetzner S3) ~5€/mes"*.

**Propuesta**:
- Script systemd timer diario: `sqlite3 state.db ".backup …" && rclone copy …`.
- Hetzner Object Storage o R2 de Cloudflare.
- Retención 30 días.

### T-03 — Promoción automática de Fallback a control-plane

> [!warning] Importante
> Hoy si **Matrix cae completa** (no solo bajo presión), `fallback` queda huérfano sin control-plane. K3s no le permite tomar el relevo automáticamente.
>
> El PDF habla de "funcionamiento degradado" pero no detalla el procedimiento.

**Propuesta**:
- Documentar procedimiento manual hoy.
- Largo plazo: usar K3s HA con embedded etcd o kine + Postgres remoto.

### T-04 — Watcher de Ollama (auto-restart)

> [!info] Deseable
> El K8sWatcher mira eventos K8s. Falta un watcher análogo que detecte si Ollama cae y haga `systemctl restart ollama` antes de pasar a fallback cloud.

### T-05 — Healthcheck activo de la VPN

PDF página 21 prioriza WireGuard como **prioridad 1** en recuperación. Hoy no hay tool ni alerta que detecte si la VPN se cae. **Crear** una alerta Prometheus + un blackbox exporter probe `udp://heimdall:51820`.

## 🔒 Seguridad y hardening

### T-06 — Cifrar `state.db` en disco

Hoy SQLite escribe en claro. Aprobaciones contienen `action_payload` con datos del cliente. Usar `SQLCipher` o LUKS-on-LeIA.

### T-07 — Rotación de tokens Telegram

Hoy el token vive en `.env` sin caducidad. **Documentar y automatizar** rotación trimestral con `@BotFather`.

### T-08 — Auth Bearer en `/admin/*` y `/webhook/alert`

PDF página 23 menciona `fail2ban` y `ufw`. Falta capa app: hoy cualquier máquina en la LAN puede llamar `/admin/trigger/daily_summary`. **Añadir** header `X-Lobster-Token` validado contra secret en config.

### T-09 — TLS en el registry Matrix:5000

PDF página 38 admite *"se ha creado la confianza con el registro privado sin TLS"*. **Migrar** a HTTPS con cert auto-firmado o cert-manager interno.

### T-10 — Política de NetworkPolicy por tenant

Las plantillas Jinja2 (wordpress / static_site / web_app) **no incluyen NetworkPolicy**. Un tenant puede llegar a otro por ClusterIP. **Añadir** `default-deny` ingress/egress en cada plantilla.

→ Ya listado en [[../12-Decisiones-Limitaciones/05-Futuro-roadmap]] pero ahora con prioridad reforzada por contexto comercial del PDF.

### T-11 — Secrets de tenants en gestor dedicado

Hoy `db_password` de WordPress se guarda como Secret K8s en claro. **Migrar** a Sealed Secrets o External Secrets Operator con backend Bitwarden/Vault.

## 🤖 IA y modelos

### T-12 — Soporte multi-modelo runtime

PDF página 13 lista 6 modelos cloud (GPT-5.5, Claude Opus 4.7, Sonnet 4.6, Haiku 4.5, GPT-5.4, GPT-5.4 mini) con sus precios. **Implementar** `select_model()` extendido que pueda enrutar a cualquiera según `CaseUse` + disponibilidad.

### T-13 — Estimación de coste por decisión

PDF tabula coste $/1M tokens. **Añadir** métrica `lobster_llm_cost_eur_total` calculada a partir de tokens × precio del modelo. Visible en Grafana.

### T-14 — Caché de respuestas LLM por hash de prompt

Para health_loop_read repetitivos (mismo contenido del clúster cada 5 min → casi mismo prompt) podríamos cachear y ahorrar inferencias completas. **Reservado**: solo si la caché es invalidada con cualquier evento K8s.

### T-15 — Streaming de respuestas LLM a Telegram

Hoy `/think` muestra "Pensando..." durante minutos. Mejor **stream** tokens al usuario en cuanto Ollama los emite.

### T-16 — Embeddings + búsqueda semántica en `decisions`

Ya en roadmap [[../12-Decisiones-Limitaciones/05-Futuro-roadmap#Búsqueda vectorial]]. Refuerzo: con cloud LLM también hay endpoints de embeddings baratos (text-embedding-3-small ~0.02 $/1M tokens).

### T-17 — Detección de tool-calls como texto (post-procesado)

Documentado como problema en [[../11-Modelos-IA/03-Think-mode]]. **Implementar** regex de detección `r'<tools>\{.*\}</tools>'` y, si encuentra, registrar `Decision` con outcome=`tool_call_as_text` para análisis.

### T-18 — Modelos cuantizados más pequeños

PDF página 41 dice "qwen3:8b Q4_K_M". **Probar** Q3_K_M o int4 si LeIA queda corta de VRAM con la pila multi-modelo.

## 📦 Tenants y producto

### T-19 — Plantilla "Web con gestión de usuarios"

PDF página 12 define **3 productos**:
- Landing Page → ≈ `static_site` (✅ existe).
- Web Corporativa → ≈ `static_site` con CMS o `web_app` (parcial).
- **Web con gestión de usuarios** → registro/login, área privada, CRM. **No existe plantilla**.

**Propuesta**: crear `lobster_agent/manifests/user_app.yaml.j2` con Postgres + app + sesiones.

### T-20 — `change_tenant_tier` sin destruir

Ya en roadmap. PDF refuerza: los planes comerciales (Basic/Standard/Premium) se cambian al alza/baja vía contrato. **Necesario** para no perder datos del cliente.

### T-21 — Wake-on-request para tenants scale-to-zero

Ya en roadmap. **Imprescindible** si los planes Basic permiten hibernación: el cliente espera que su web responda siempre, aunque sea con 5 s de cold start.

### T-22 — Domain provisioning automatizado

Hoy el cliente pone su DNS manualmente. **Propuesta**: integrar con APIs de registradores (Cloudflare, Hetzner DNS) para que `deploy_tenant` cree el A record automáticamente.

### T-23 — Backup automatizado por tier

PDF prompt de `backup` ya menciona *"free=semanal, basic/premium=diario"*. Pero **no hay ejecutor real**. Implementar con Velero o `pg_dump` + S3.

## 📊 Observabilidad

### T-24 — Trazas OpenTelemetry

Ya en roadmap. PDF página 60 muestra que el operador navega entre Grafana, logs y eventos para reconstruir flujos. OTel resolvería esto.

### T-25 — Dashboard ejecutivo (negocio)

Aparte del dashboard técnico, **crear** un Grafana dashboard con:
- € MRR (Monthly Recurring Revenue) por tier.
- Margen bruto.
- Coste LLM mensual.
- Churn / nuevos tenants.

### T-26 — Endpoint `/metrics/business`

Métricas Prometheus específicas: `lobster_tenants_total{tier}`, `lobster_revenue_eur_monthly`, `lobster_cost_llm_eur_monthly`.

### T-27 — SLO definidos por nivel de soporte

PDF página 12 dice "Standard: 4h en horario laboral; Premium: respuesta 24/7". **Definir SLOs**: `lobster_incident_response_seconds`, alertar si > umbral del tier del tenant afectado.

## 🧰 Operación y CLI

### T-28 — `lobster queue` (anunciado, no entregado)

PDF página 58 menciona la cola Fase 9. CLI `lobster queue list|drop` está en roadmap.

### T-29 — `lobster tenants` con filtro por tier

`lobster tenants list --tier=premium` para inspecciones rápidas.

### T-30 — `lobster cost` para informes

Imprime: tokens consumidos, coste estimado, top 5 jobs más caros.

### T-31 — `lobster doctor`

Comando que ejecuta todos los probes (Ollama, K3s, Prom, Loki, Alertmanager, Telegram) y reporta verde/rojo. Útil tras incidencias.

### T-32 — Mejor `tool-requests`

Ya en roadmap. Ampliar: `lobster tool-requests close <id> --reason "ya implementado en commit X"`.

## 📐 Código y arquitectura

### T-33 — Reducir el catch-all `Exception` del watcher

`k8s_watcher.py` captura `Exception` genérica al reconectar. **Refinar**: cazar `aiohttp.ClientError`, `httpx.HTTPError`, `RuntimeError` explícitamente y dejar pasar `KeyboardInterrupt`.

### T-34 — Tests de integración E2E

`tests/` tiene unit tests buenos. Falta **E2E** que arranque Lobster real, dispare webhook, espere reacción, valide Action en DB. Usar `pytest-asyncio` + `respx` + minikube/kind.

### T-35 — Modo `replay` para depurar incidencias

Dado un `decision_id`, reproduce el agente con el mismo prompt y model_settings y compara outputs. Permite ver si un cambio reciente rompió el comportamiento.

### T-36 — Migración a `aiogram v4` cuando esté estable

Hoy v3 funciona. La v4 cambia APIs. **Mantener atención** al changelog.

→ Roadmap priorizado en [[05-Roadmap-priorizado]].
