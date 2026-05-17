---
title: Flujo de datos y control
tags: [arquitectura, flujo, secuencia, agente]
---

# 🔄 Flujo de datos y control

> [!abstract] El bucle completo
> Esta nota documenta los tres caminos por los que Lobster entra en acción y cómo termina cada uno.

## 🛣️ Tres disparadores

```mermaid
flowchart LR
    A[APScheduler\n7 jobs] --> Run
    B[K8s Watcher\nevent stream] --> Run
    C[Webhook\nAlertmanager] --> Run
    D[Telegram\noperador] --> Run
    Run[LobsterAgent.run]
```

## 🎬 Secuencia detallada (con mutación que requiere aprobación)

```mermaid
sequenceDiagram
  autonumber
  participant Trig as Trigger
  participant Orch as LobsterAgent.run
  participant Pol as Policy
  participant LLM as Pydantic-AI + Qwen3
  participant Tool as Tool (mutación)
  participant MC as MutationContext
  participant Pol2 as policy.validate
  participant AR as ActionRepository
  participant AM as ApprovalManager
  participant Bot as TelegramBot
  participant Op as Operador
  participant K8s as K3s

  Trig->>Orch: run(CaseUse, prompt)
  Orch->>Orch: select_model + use_think_mode
  Orch->>Orch: build_system_prompt
  Orch->>LLM: Agent.run(prompt, deps)
  LLM->>Tool: llamada a restart_deployment
  Tool->>MC: execute(action_type, ns, target, payload, executor)
  MC->>Pol2: validate(...)
  Pol2-->>MC: allowed=true severity=NORMAL
  MC->>AR: Action(status=PENDING)
  AR-->>MC: action.id
  MC->>AR: update_status(AWAITING_APPROVAL)
  MC->>AM: request_approval(ApprovalRequest)
  AM->>Bot: post_approval_request(Approval)
  Bot->>Op: 🔔 mensaje + botones inline
  Op->>Bot: tap "Aprobar"
  Bot->>AM: update_status(APPROVED)
  AM-->>MC: wait_for_decision retorna APPROVED
  MC->>AR: update_status(APPROVED)
  MC->>K8s: executor() → patch Deployment
  K8s-->>MC: dict resultado
  MC->>AR: update_status(COMPLETED, result)
  MC-->>Tool: ActionResult(COMPLETED)
  Tool-->>LLM: mensaje "completed"
  LLM-->>Orch: respuesta final
  Orch->>Orch: Decision en DB + métricas
  Orch-->>Trig: AgentResult(success, data)
```

## ⚡ Variante: acción AUTONOMOUS

Cuando el agente decide `restart_pod` y el pod está confirmado en `CrashLoopBackOff` **en un namespace tenant**, la severidad se convierte a `AUTONOMOUS` (lo decide `tools/mutations/k8s.py:restart_pod`). Eso salta los pasos 9-15:

```mermaid
sequenceDiagram
  participant LLM
  participant Tool as restart_pod
  participant MC as MutationContext
  participant K8s
  LLM->>Tool: restart_pod
  Tool->>MC: severity_override=AUTONOMOUS
  MC->>MC: validate + crear Action
  MC->>K8s: executor()
  MC->>MC: COMPLETED
  MC-->>Tool: ActionResult
```

## 📨 Variante: webhook reactivo

```mermaid
sequenceDiagram
  participant AM as Alertmanager
  participant API as FastAPI /webhook/alert
  participant SCH as SchedulerRunner.trigger_alert_reactive
  participant Orch as LobsterAgent
  AM->>API: POST alertas
  API->>SCH: create_task(trigger_alert_reactive)
  API-->>AM: 202 accepted
  SCH->>Orch: run(CaseUse.ALERT_REACTIVE, prompt)
  Orch-->>SCH: notify a Telegram con header 🚨
```

## 👀 Variante: K8s Watcher

```mermaid
sequenceDiagram
  participant Watch as lightkube AsyncClient.watch(Event)
  participant K8s
  participant Filter
  participant Orch as LobsterAgent
  K8s-->>Watch: Event {type:Warning, reason:CrashLoopBackOff}
  Watch->>Filter: _is_critical_event
  Filter-->>Watch: true
  Watch->>Orch: run(CaseUse.HEALTH_LOOP_ANALYZE, prompt formateado)
  Orch-->>Telegram: 👁️ Lobster [watcher/CrashLoopBackOff]
```

## 🧬 Persistencia transversal

> [!info] Todo queda escrito
> En cualquiera de las variantes:
> - `decisions` ← una fila por `run()` con tokens, modelo, latencia, tools llamadas.
> - `actions` ← una fila por mutación, con su máquina de estados.
> - `approvals` ← una fila por petición de aprobación (si la había).
> - `tool_requests` ← una fila si el agente llamó `request_new_tool` por no encontrar herramienta.
> - Métricas Prom ← incrementadas (decisions_total, llm_latency, errors_total…).
> - Logs structlog ← evento JSON enviado a Loki en background.

→ Continúa en [[../05-Persistencia/01-SQLite-esquema]].
