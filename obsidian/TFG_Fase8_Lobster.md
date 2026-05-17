# Fase 8 — Migración de Workloads bajo Presión de Nodo

## ¿Qué es la Fase 8?

> [!abstract] Resumen ejecutivo
> La Fase 8 da a Lobster la capacidad de actuar cuando un nodo del clúster K3s entra en situación de presión de CPU o memoria. Hasta ahora el agente podía observar el estado de los nodos, pero no podía hacer nada con esa información. Con esta fase, Lobster ejecuta cada 15 minutos un ciclo de análisis que detecta nodos sobrecargados, identifica los deployments de tenant candidatos a migrar, y los mueve al nodo `fallback` fijando un `nodeSelector`. Una vez que la presión baja, el agente restaura el scheduling libre de forma autónoma.
>
> El principio que guía esta fase es: **el agente debe ser capaz de redistribuir carga sin intervención humana**, salvo para la acción ofensiva (pin), que requiere aprobación explícita. La operación inversa (unpin) es autónoma porque relajar una restricción tiene menor riesgo que imponerla.

> [!note] Tecnologías utilizadas
> `kubernetes.io/hostname nodeSelector` · `lightkube` · `pydantic-ai` · `APScheduler` · `MutationContext` · `ActionSeverity` · `Telegram approval flow`

---

## Lo que está implementado (rama `worktree-fase-8-node-pressure`)

### 1. Dos nuevos métodos en `K8sClient`

> [!tip] Explicación para el TFG
> Se añadieron dos métodos al cliente K8s para gestionar el `nodeSelector` de un Deployment. `patch_deployment_node_selector` aplica un JSON Merge Patch sobre `spec.template.spec.nodeSelector`; pasar `None` elimina el campo por semántica del Merge Patch, liberando el scheduling. `get_deployment_node_selector` lee el selector actual para poder registrarlo como estado previo antes de sobrescribirlo.

> [!example] Código añadido en `lobster_agent/clients/k8s.py`
> ```python
> async def patch_deployment_node_selector(
>     self, namespace: str, name: str, node_selector: dict[str, str] | None
> ) -> None:
>     patch = {"spec": {"template": {"spec": {"nodeSelector": node_selector}}}}
>     await self._get_client().patch(Deployment, name, patch, namespace=namespace)
>
> async def get_deployment_node_selector(
>     self, namespace: str, name: str
> ) -> dict[str, str] | None:
>     deployment = await self.get_deployment(namespace, name)
>     # navega spec.template.spec.nodeSelector y devuelve None si no existe
> ```

---

### 2. Dos nuevas mutation tools (`lobster_agent/agent/tools/mutations/node.py`)

> [!tip] Explicación para el TFG
> Las herramientas de mutación son las funciones que el LLM puede invocar. Cada una pasa por `MutationContext.execute()`, que aplica la política de permisos, determina si necesita aprobación humana, registra la acción en el ledger y la ejecuta. `pin_deployment_to_node` tiene severidad **NORMAL** (requiere aprobación via Telegram). `unpin_deployment_from_node` tiene severidad **AUTONOMOUS** (se ejecuta sin confirmación).

> [!example] Firmas de las herramientas
> ```python
> KnownNode = Literal["leia", "matrix", "sauron", "heimdall", "fallback"]
>
> async def pin_deployment_to_node(
>     ctx: RunContext[AgentDeps],
>     namespace: str,
>     deployment_name: str,
>     node: KnownNode,
> ) -> str: ...
>
> async def unpin_deployment_from_node(
>     ctx: RunContext[AgentDeps],
>     namespace: str,
>     deployment_name: str,
> ) -> str: ...
> ```

> [!example] Mensajes de respuesta al LLM (ejemplos)
> - Éxito pin: `"pin_deployment_to_node completed: tenant-x/web → fallback"`
> - Dry-run pin: `"would set nodeSelector to {'kubernetes.io/hostname': 'fallback'}"`
> - Nada que desanclar: `"nothing to remove — deployment tenant-x/web has no nodeSelector"`
> - Dry-run unpin: `"would remove nodeSelector {'kubernetes.io/hostname': 'fallback'}"`
> - Sin contexto de mutación: `"Mutation context unavailable"`
> - Error pre-acción: `"failed before action creation: <error>"`

---

### 3. Nueva entrada `CaseUse.NODE_PRESSURE`

> [!tip] Explicación para el TFG
> `CaseUse` es el enum que determina qué modelo usa el agente y qué herramientas tiene disponibles. `NODE_PRESSURE` usa **`qwen3:32b` con think mode activado** porque las decisiones de migración requieren razonamiento profundo: hay que ponderar qué deployments mover, en qué orden, y si el nodo destino puede absorber la carga. El conjunto de herramientas es deliberadamente limitado: no tiene herramientas de mutación generales, solo `pin_deployment_to_node` y `unpin_deployment_from_node`.

> [!example] Herramientas disponibles para `NODE_PRESSURE`
> ```
> meta_tools          → request_new_tool
> prometheus_tools    → query_prometheus_instant, query_prometheus_range, get_node_health
> k8s_basic_tools     → list_pods, get_pod, list_deployments, list_ingresses, list_namespaces
> memory_tools        → search_decisions, get_decision
> node_pressure_tools → pin_deployment_to_node, unpin_deployment_from_node
> ```

---

### 4. Prompt del sistema para `NODE_PRESSURE`

> [!tip] Explicación para el TFG
> El prompt del sistema guía al LLM con un flujo de 6 pasos obligatorios. Este diseño evita que el modelo improvise: primero debe recopilar datos (pasos 1-3), luego actuar (pasos 4-5), y finalmente restaurar el estado cuando ya no es necesario (paso 6). La regla de seguridad más importante es que nunca debe pinar deployments si el nodo `fallback` también está bajo presión.

> [!example] Flujo de 6 pasos en `lobster_agent/agent/prompts/system.py`
> 1. Llamar a `get_node_health` para **todos** los nodos conocidos (leia, matrix, sauron, heimdall, fallback)
> 2. Identificar nodos con CPU o memoria por encima del umbral
> 3. Listar deployments de tenant en esos nodos con `list_pods` y `list_deployments`
> 4. Seleccionar candidatos a migrar priorizando los de mayor consumo
> 5. Llamar a `pin_deployment_to_node` con `node='fallback'` (requiere aprobación humana)
> 6. Si la presión ya bajó en nodos donde hay deployments pinados, llamar a `unpin_deployment_from_node` (autónomo)

---

### 5. Nuevo job en el scheduler (`lobster_agent/scheduler.py`)

> [!tip] Explicación para el TFG
> El job `node_pressure` se registra en APScheduler con `IntervalTrigger` y corre cada 15 minutos (configurable). Si detecta una migración o un desanclaje, el resultado se envía por Telegram con el emoji 🌡️. Los umbrales por defecto son 85% para CPU y 85% para memoria, pero pueden sobreescribirse en el fichero de configuración TOML.

> [!example] Configuración en `lobster_agent/config.py`
> ```toml
> [scheduler]
> node_pressure_interval_minutes = 15
> node_pressure_cpu_threshold_pct = 85.0
> node_pressure_memory_threshold_pct = 85.0
> ```

---

### 6. Política de severidad (`lobster_agent/domain/policy.py`)

> [!example] Entradas añadidas a `ACTION_SEVERITIES`
> ```python
> "pin_deployment_to_node":     ActionSeverity.NORMAL,      # requiere aprobación Telegram
> "unpin_deployment_from_node": ActionSeverity.AUTONOMOUS,  # se ejecuta directamente
> ```

---

### 7. Suite de tests (`tests/test_node_pressure_tools.py`)

> [!tip] Explicación para el TFG
> Se añadieron 12 tests unitarios usando `FakeK8sClient` y `FakeMutationContext` (sin dependencias externas). Los tests cubren todos los caminos de código relevantes para ambas herramientas: éxito, dry-run, ausencia de contexto de mutación, error K8s pre-acción, nodo ya libre, registro del selector previo, y la severidad autónoma de `unpin`.

> [!example] Tests incluidos
> | Test | Qué verifica |
> |---|---|
> | `test_pin_deployment_to_node_success` | El pin se aplica correctamente y la severidad es NORMAL |
> | `test_pin_deployment_to_node_no_mutation_context` | Devuelve "unavailable" sin llamar a K8s |
> | `test_pin_deployment_to_node_k8s_error_pre_action` | Error antes de crear la acción → "failed before action creation" |
> | `test_pin_deployment_to_node_dry_run` | Dry-run → "would set nodeSelector" sin modificar K8s |
> | `test_pin_deployment_records_previous_selector` | El selector previo queda en el payload |
> | `test_pin_deployment_to_node_all_known_nodes` | Los 5 nodos conocidos se aceptan correctamente |
> | `test_unpin_deployment_from_node_success` | El unpin limpia el nodeSelector a None |
> | `test_unpin_deployment_from_node_already_free` | Sin pin existente → "nothing to remove" sin acciones |
> | `test_unpin_deployment_from_node_no_mutation_context` | Devuelve "unavailable" |
> | `test_unpin_deployment_from_node_autonomous_severity` | La severidad es AUTONOMOUS |
> | `test_unpin_deployment_from_node_dry_run` | Dry-run → "would remove nodeSelector" sin modificar K8s |
> | `test_unpin_deployment_k8s_error_pre_action` | Error pre-acción en unpin → "failed before action creation" |

> [!success] Estado de los tests
> Todos los tests pasan: **12 nuevos + 235 existentes = 247 en total** ✓

---

## Diagrama de flujo de la Fase 8

```
Cada 15 minutos
      │
      ▼
get_node_health(leia, matrix, sauron, heimdall, fallback)
      │
      ├─ ¿Algún nodo > 85% CPU o memoria?
      │       │ NO → "Todos los nodos dentro de umbrales" → Telegram 🌡️
      │       │
      │       ▼ SÍ
      │   list_deployments(namespace=tenant-*)
      │       │
      │       ▼
      │   ¿fallback también bajo presión?
      │       │ SÍ → Notificar operador, no actuar
      │       │
      │       ▼ NO
      │   pin_deployment_to_node(ns, deploy, node="fallback")
      │       │
      │       ▼
      │   Aprobación Telegram (NORMAL) ──► Rechazada → fin
      │       │ Aprobada
      │       ▼
      │   K8s patch nodeSelector → rolling update automático
      │
      ├─ ¿Algún nodo ya sin presión tiene deployments pinados?
      │       │ NO → fin
      │       │
      │       ▼ SÍ
      │   unpin_deployment_from_node(ns, deploy)
      │       │
      │       ▼ AUTÓNOMO — sin aprobación
      │   K8s patch nodeSelector = null → scheduling libre
      │
      ▼
Resultado enviado por Telegram 🌡️
```

---

## Ficheros modificados / creados

| Fichero | Estado | Qué cambió |
|---|---|---|
| `lobster_agent/clients/k8s.py` | Modificado | +`patch_deployment_node_selector`, +`get_deployment_node_selector` |
| `lobster_agent/agent/tools/mutations/node.py` | **Creado** | Herramientas `pin_deployment_to_node` y `unpin_deployment_from_node` |
| `lobster_agent/agent/tools/mutations/__init__.py` | Modificado | Exporta las dos nuevas herramientas |
| `lobster_agent/agent/routing.py` | Modificado | +`CaseUse.NODE_PRESSURE`, modelo `qwen3:32b`, think mode |
| `lobster_agent/agent/prompts/system.py` | Modificado | +misión y flujo de 6 pasos para `NODE_PRESSURE` |
| `lobster_agent/agent/orchestrator.py` | Modificado | +importes, +`node_pressure_tools`, +entrada en `_build_tools_for_case` |
| `lobster_agent/domain/policy.py` | Modificado | +severidades de las dos nuevas acciones |
| `lobster_agent/config.py` | Modificado | +3 parámetros en `SchedulerConfig` |
| `lobster_agent/scheduler.py` | Modificado | +emoji, +prompt template, +job, +`_node_pressure_job()` |
| `tests/test_node_pressure_tools.py` | **Creado** | 12 tests unitarios |

---

## Lo que queda por hacer

> [!warning] Pendiente de despliegue
> El código está completo y testado en la rama `worktree-fase-8-node-pressure`. No se ha desplegado porque había pruebas en producción en el momento de la implementación. Pasos pendientes:

> [!todo] Checklist de despliegue
> - [ ] **Mergear la rama a main**
>   ```bash
>   git merge worktree-fase-8-node-pressure
>   ```
> - [ ] **Reiniciar el servicio Lobster** en LeIA
>   ```bash
>   sudo systemctl restart lobster
>   ```
> - [ ] **Verificar que el job `node_pressure` aparece en el scheduler** (primer ciclo en ≤15 min)
>   ```bash
>   curl http://localhost:8080/metrics | grep scheduler_runs_total | grep node_pressure
>   ```
> - [ ] **Verificar en Prometheus** que `lobster_scheduler_runs_total{case_use="node_pressure"}` aparece tras el primer ciclo
> - [ ] **Probar en modo dry-run** antes del primer ciclo real:
>   ```toml
>   # En /etc/lobster/config.toml:
>   [agent]
>   dry_run_default = true
>   ```
> - [ ] **Revisar en Telegram** que llegan notificaciones 🌡️ con el resultado del job
> - [ ] **Verificar el ledger de acciones** si se produce alguna migración:
>   ```bash
>   uv run lobster actions list
>   ```

> [!note] Configuración recomendada para el primer despliegue
> Arrancar con `dry_run_default = true` el primer día para validar que el agente identifica correctamente los nodos bajo presión sin ejecutar migraciones reales. Una vez validado, desactivar el dry-run.

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Razón |
|---|---|---|
| `nodeSelector` en lugar de `nodeAffinity` | `nodeAffinity` | Más simple para el caso de uso; K8s hace rolling update automático al cambiar `spec.template` |
| `unpin` es AUTÓNOMO | Requerir aprobación | Relajar una restricción tiene riesgo menor que imponerla; el scheduler lo puede revertir si se equivoca |
| Herramientas separadas `node_pressure_tools` en el orquestador | Añadirlas solo a `mutation_tools` | `NODE_PRESSURE` necesita un conjunto reducido; evita exponer herramientas de tenant (deploy/delete) en este caso de uso |
| `qwen3:32b` con think mode para `NODE_PRESSURE` | `qwen3:8b` sin think | Las decisiones de migración requieren razonar sobre múltiples nodos y deployments simultáneamente |
| Umbral por defecto 85% | 90% | Margen suficiente para que el rolling update (que añade réplicas temporalmente) no cause OOM durante la migración |
