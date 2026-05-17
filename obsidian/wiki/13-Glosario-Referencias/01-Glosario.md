---
title: Glosario
tags: [glosario, referencias, terminos]
---

# 📖 Glosario

> [!abstract] Términos del proyecto
> Definiciones rápidas. Cuando un término tenga una nota propia, se enlaza.

## A

**Action** · Fila en la tabla `actions`. Cada mutación que el agente intenta deja una. → [[../05-Persistencia/03-Actions-ledger]]

**AgentDeps** · Dataclass con las dependencias inyectadas a las tools (clients HTTP, repos, manager). → [[../02-Agente/01-LobsterAgent-orchestrator#diagrama]]

**AgentMode** · Enum `normal | dry_run | paused`. Modo global del agente. → [[../02-Agente/07-Agent-state-modos]]

**aiogram v3** · Librería Telegram async usada para el bot. → [[../04-Telegram/01-Bot-runner]]

**Alembic** · Migraciones SQL versionadas. → [[../05-Persistencia/09-Alembic-migraciones]]

**Alertmanager** · Pieza de Prometheus que enruta alertas. En SaaSphere corre en Sauron. → [[../06-Observabilidad/05-Webhook-Alertmanager]]

**Approval** · Fila en `approvals`. Una petición de aprobación humana. → [[../05-Persistencia/04-Approvals]]

**ApprovalManager** · Coordina create + wait + notify de approvals. → [[../02-Agente/06-Approval-manager]]

**ApprovalMaintenanceLoop** · Task de fondo que expira approvals y emite recordatorios CRITICAL.

**APScheduler** · Scheduler async usado para los 7 jobs periódicos. → [[../07-Scheduler-Watcher/01-APScheduler-jobs]]

**AUTONOMOUS** · Severidad que no requiere aprobación. → [[../03-Tools/00-MOC-Tools#Tabla rápida]]

## B

**Bot runner** · `TelegramBotRunner` — gestiona arranque y polling del bot. → [[../04-Telegram/01-Bot-runner]]

## C

**CaseUse** · StrEnum con los 14 modos de operación del agente. → [[../02-Agente/02-CaseUse-y-routing]]

**CHAT** · `CaseUse` usado en texto libre Telegram. qwen3:8b sin think.

**ClusterRole** · Tipo K8s prohibido en `apply_manifest`. → [[../09-Tenants/06-Politica-namespaces]]

**ConversationMemory** · Memoria conversacional de dos capas (RAM + SQLite). → [[../04-Telegram/04-Conversation-memory]]

**CrashLoopBackOff** · Estado K8s donde un pod arranca, crashea, reinicia, en bucle. → [[../03-Tools/06-Mutations-K8s#restart_pod]]

**CRITICAL** · Severidad alta, requiere aprobación con timeout 1h + recordatorios. → [[../02-Agente/06-Approval-manager]]

## D

**daily_summary** · Job diario a las 08:00 que genera informe en `obsidian/`. → [[../07-Scheduler-Watcher/03-Global-state-Summary-Daily#daily_summary]]

**Decision** · Fila en `decisions`. Una ejecución del agente. → [[../05-Persistencia/02-Decisions]]

**DRY_RUN** · Modo del agente donde mutaciones se simulan. → [[../10-Operacion/04-Modos-normal-dryrun-paused]]

## E

**Event** · Tabla auxiliar `events` o evento de K8s (`Event` resource). → [[../05-Persistencia/08-Events-Tenant-state-Snapshots]]

## F

**fallback** · Nodo K3s con taint `saasphere/role=fallback:NoSchedule`. Cold standby. → [[../08-Infraestructura/02-Nodos-matrix-fallback]]

**Fase N** · Etapa del TFG. Fases 1-9. → [[../01-Arquitectura/05-Modelo-evolutivo-por-fases]]

**FREE / BASIC / PREMIUM** · Tiers de tenant. → [[../09-Tenants/02-Tiers]]

## G

**Grafana** · Dashboards en Sauron. → [[../06-Observabilidad/03-Dashboard-Grafana]]

## H

**Heimdall** · Edge / reverse proxy de SaaSphere. No es nodo K3s. → [[../08-Infraestructura/03-Hosts-LeIA-Sauron-Heimdall]]

**health_loop** · Job cada 5 min. read + chain analyze. → [[../07-Scheduler-Watcher/02-Health-loop]]

## J

**JobQueue** · Cola FIFO de la Fase 9. → [[../07-Scheduler-Watcher/07-Job-queue-fase9]]

## K

**K3s** · Distro K8s liviana usada en SaaSphere. → [[../08-Infraestructura/01-SaaSphere-cluster-K3s]]

**K8sClient** · Cliente lightkube wrapper de Lobster. → [[../03-Tools/03-Reading-K8s]]

**K8sWatcher** · Streaming de eventos K8s. → [[../07-Scheduler-Watcher/06-K8s-Watcher]]

## L

**LeIA** · Host (192.168.1.200) donde corre Lobster + Ollama. → [[../08-Infraestructura/03-Hosts-LeIA-Sauron-Heimdall#LeIA]]

**lightkube** · Cliente K8s async puro Python. → [[../03-Tools/03-Reading-K8s]]

**Loki** · Almacén de logs en Sauron. → [[../06-Observabilidad/01-Logs-structlog-Loki]]

## M

**matrix** · Nodo K3s principal (control plane + workloads). → [[../08-Infraestructura/02-Nodos-matrix-fallback]]

**MOC** · "Map Of Content". Nota índice. Todas las `00-MOC-*.md` lo son.

**MutationContext** · Sandwich de seguridad: policy → severity → approval → executor. → [[../02-Agente/05-Mutation-context]]

## N

**Namespace** · Espacio K8s. Cada tenant tiene su namespace marcado con `saasphere.io/tenant=true`.

**NORMAL** · Severidad media, requiere aprobación con timeout 10 min. → [[../02-Agente/06-Approval-manager]]

## O

**Obsidian** · Editor de notas que usa el operador. El vault está en `/opt/lobster/obsidian/`. → [[../10-Operacion/06-Daily-summary-Obsidian]]

**Ollama** · Inferenciador local que corre Qwen3 en LeIA. → [[../08-Infraestructura/04-Ollama-GPU]]

**LobsterAgent** · Clase principal del agente. → [[../02-Agente/01-LobsterAgent-orchestrator]]

## P

**PAUSED** · Modo del agente donde LLM no se ejecuta. → [[../10-Operacion/04-Modos-normal-dryrun-paused]]

**pin / unpin** · Mover deployment a un nodo específico / liberar. → [[../03-Tools/08-Mutations-Nodes]]

**policy.validate()** · Función pura que valida una mutación contra reglas estáticas. → [[../09-Tenants/06-Politica-namespaces]]

**Prometheus** · Almacén de métricas en Sauron. → [[../06-Observabilidad/02-Metricas-Prometheus]]

**Pydantic-AI** · Framework agéntico LLM usado. → [[../11-Modelos-IA/04-Pydantic-AI]]

## Q

**Qwen3** · Familia de LLMs (Alibaba) usados. → [[../11-Modelos-IA/01-Qwen3-overview]]

## R

**RBAC** · Control de acceso K8s del kubeconfig de Lobster. → [[../08-Infraestructura/05-RBAC-Kubeconfig]]

**ResourceQuota** · Cuota K8s por namespace. Generada automáticamente en `deploy_tenant`.

## S

**SaaSphere** · El homelab. Clúster + observabilidad + edge + agente. → [[../08-Infraestructura/00-MOC-Infraestructura]]

**Sauron** · Host (192.168.1.201) con Prom/Loki/Alertmanager/Grafana. → [[../08-Infraestructura/03-Hosts-LeIA-Sauron-Heimdall#Sauron]]

**SchedulerRunner** · Wrapper de APScheduler. → [[../07-Scheduler-Watcher/01-APScheduler-jobs]]

**search_decisions** · Tool de lectura para el "recuerdo" del agente. → [[../03-Tools/05-Reading-Memory]]

**static_site** · Tipo de tenant (HTML + nginx + PVC). → [[../09-Tenants/03-Tipos]]

**structlog** · Librería de logging estructurado. → [[../06-Observabilidad/01-Logs-structlog-Loki]]

**SQLModel** · ORM (= SQLAlchemy + Pydantic). → [[../05-Persistencia/01-SQLite-esquema]]

## T

**taint** · Restricción de scheduling K8s. `fallback` lleva `saasphere/role=fallback:NoSchedule`.

**tenant** · Cliente con su namespace. → [[../09-Tenants/01-Modelo-multi-tenant]]

**TelegramNotifier** · Helper para enviar mensajes desde código no-handler. → [[../04-Telegram/06-Notifier]]

**think mode** · Extensión `/think` de Qwen3 que añade razonamiento explícito. → [[../11-Modelos-IA/03-Think-mode]]

**tool** · Función Python registrada con Pydantic-AI que el LLM puede llamar.

**tool_calls** · JSON estructurado en respuesta del LLM para invocar funciones.

**toleration** · Permite a un pod planificarse en nodo con taint. Lobster las genera automáticamente al pinar.

**ToolRequest** · Fila en `tool_requests` cuando el agente pide una nueva herramienta. → [[../05-Persistencia/05-Tool-requests]]

## U

**unpin** · Soltar el pin de un deployment. AUTONOMOUS. → [[../03-Tools/08-Mutations-Nodes]]

## W

**WAL** · "Write Ahead Log" de SQLite. → [[../05-Persistencia/01-SQLite-esquema]]

**Watcher** · → [[../07-Scheduler-Watcher/06-K8s-Watcher]]

**webhook** · POST a `/webhook/alert`. → [[../06-Observabilidad/05-Webhook-Alertmanager]]

**wordpress** · Tipo de tenant (WP + MariaDB). → [[../09-Tenants/03-Tipos]]
