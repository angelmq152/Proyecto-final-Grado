---
title: Tabla — actions (mutation ledger)
tags: [persistencia, actions, ledger, mutaciones]
---

# 📜 Tabla `actions` — ledger de mutaciones

> [!abstract] El "libro mayor" del agente
> Cada vez que una tool de mutación pasa por `MutationContext.execute(...)`, se crea una fila en `actions`. Es el **registro auditable** de absolutamente todo lo que el agente ha intentado hacer al clúster, exitoso o no.

## 📐 Modelo

```python
class Action(SQLModel, table=True):
    id: str (PK)                          # uuid string
    created_at: datetime
    updated_at: datetime
    action_type: str                      # restart_pod | deploy_tenant | ...
    namespace: str
    target: str                           # pod_name, deployment_name, etc.
    severity: str                         # autonomous | normal | critical | forbidden
    status: str                           # ActionStatus
    payload: str                          # JSON serializado
    result: str | None                    # JSON con el resultado
    decision_id: str | None (FK)          # qué Decision la disparó
    approval_id: str | None               # qué Approval la cubrió
    dry_run: bool

    # Legacy columns (de migraciones antiguas, se mantienen para compatibilidad):
    timestamp_created, timestamp_started, timestamp_finished
    category, target_namespace, target_kind, target_name
    idempotency_key, state, error
```

## 🔁 Máquina de estados

→ Ver [[../02-Agente/05-Mutation-context#diagrama-de-estados-de-action]] para el diagrama completo.

```python
VALID_ACTION_TRANSITIONS = {
    PENDING:           {AWAITING_APPROVAL, RUNNING, ABORTED_DRY_RUN, ABORTED_POLICY},
    AWAITING_APPROVAL: {APPROVED, REJECTED, ABORTED_POLICY},
    APPROVED:          {RUNNING, ABORTED_DRY_RUN, ABORTED_POLICY},
    RUNNING:           {COMPLETED, FAILED},
    REJECTED:          set(),     # terminal
    COMPLETED:         set(),     # terminal
    FAILED:            set(),     # terminal
    ABORTED_DRY_RUN:   set(),
    ABORTED_POLICY:    set(),
}
```

> [!warning] Transiciones inválidas lanzan ValueError
> `ActionRepository.update_status` valida y rechaza saltos arbitrarios. Esto previene corrupción accidental.

## 📋 Inspección operativa

```bash
# Lista las últimas 20
uv run lobster actions list

# Filtra por estado
uv run lobster actions list --status failed

# Detalle JSON
uv run lobster actions show <id>

# Estadísticas por estado
uv run lobster actions stats
# completed: 142
# failed: 3
# aborted_policy: 12
# aborted_dry_run: 8
# rejected: 5
```

## 🎯 Casos típicos

> [!example] Una mutación exitosa
> ```
> 2026-05-16T17:32:12 a5f23c91…  completed  normal  restart_deployment tenant-acme/wordpress
> payload: {"current_replicas": 2, "ready_replicas": 0, ...}
> result:  {"restarted": true, "deployment_name": "wordpress", ...}
> approval_id: b8e91234…
> decision_id: c47ab2…
> ```

> [!example] Una abortada por policy
> ```
> 2026-05-16T18:01:48  ff10ab22…  aborted_policy  forbidden  delete_pod kube-system/coredns
> result: {"reason": "system namespace is protected", "violations": ["system_namespace"]}
> ```

## 🔗 Cruzando tablas

```sql
-- ¿Qué decisión disparó cada acción exitosa?
SELECT a.id, a.action_type, a.target, d.case_use, d.timestamp
FROM actions a LEFT JOIN decisions d ON a.decision_id = d.id
WHERE a.status = 'completed'
ORDER BY a.created_at DESC;
```

## 🚨 Acción aprobada pero fallida

> [!info] Caso 1 % pero documentado
> Si `executor()` lanza una excepción durante la ejecución (p.ej. K8s API caída justo al patch), la fila pasa a `FAILED` y `error` se llena con el mensaje. La aprobación humana ya fue consumida pero la mutación no se aplicó. El agente reporta el fallo y el operador decide si reintenta.

## 🧮 Volumen esperado

> [!tip] Menos que decisions
> Solo las **mutaciones** llegan aquí, no las lecturas. En SaaSphere típico: 5-30 acciones/día. Total año < 11k filas. Diminuto.
