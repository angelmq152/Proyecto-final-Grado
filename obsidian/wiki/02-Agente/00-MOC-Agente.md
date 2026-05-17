---
title: 02 · Agente — MOC
tags: [moc, agente, lobster, pydantic-ai, qwen3]
---

# 🤖 02 · Agente — MOC

> [!abstract] Núcleo de Lobster
> Toda la lógica de razonamiento vive aquí: cómo se construye el agente, cómo se eligen modelo y think mode según el caso de uso, cómo se ensambla el system prompt, cómo se intercepta una mutación para validarla, y cómo se bloquea el agente esperando una aprobación humana.

## Notas

- [[01-LobsterAgent-orchestrator]] — la clase principal, ciclo `run()`.
- [[02-CaseUse-y-routing]] — los 14 modos del agente.
- [[03-Modelos-Qwen3]] — selección 8b/32b y think mode.
- [[04-System-prompts]] — cómo se construyen los prompts por modo.
- [[05-Mutation-context]] — sobre policy → severity → approval → ledger → executor.
- [[06-Approval-manager]] — bloqueo asíncrono esperando al humano.
- [[07-Agent-state-modos]] — normal · dry_run · paused.

## Diagrama mental

```mermaid
flowchart LR
    Input[Prompt o trigger] --> Orch[LobsterAgent.run]
    Orch -->|select_model| Model{qwen3:8b ó 32b}
    Orch -->|use_think_mode| Think{think on/off}
    Orch -->|build_system_prompt| Prompt
    Orch -->|tools por CaseUse| Tools
    Model --> Loop[Pydantic-AI loop]
    Prompt --> Loop
    Tools --> Loop
    Loop -->|tool_call mutación| MC[MutationContext]
    MC -->|policy.validate| Policy
    MC -->|severity ≥ NORMAL| AM[ApprovalManager]
    AM -->|Telegram| Op[Operador]
    Op -->|aprobado| MC
    MC --> Exec[Ejecutor real K8s]
    Loop --> Decision[Decision en SQLite]
```

## Enlaces cruzados

- Las herramientas que el agente puede llamar → [[../03-Tools/00-MOC-Tools|Tools]].
- La aprobación pasa por Telegram → [[../04-Telegram/03-Aprobaciones-inline|Aprobaciones inline]].
- Cada decisión se persiste → [[../05-Persistencia/02-Decisions|Decisions]].
- Cada mutación queda registrada → [[../05-Persistencia/03-Actions-ledger|Actions ledger]].
