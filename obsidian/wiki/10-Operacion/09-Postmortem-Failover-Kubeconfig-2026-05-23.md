---
title: Postmortem — Failover bloqueado por kubeconfig incorrecto (2026-05-23)
tags: [postmortem, failover, k3s, kubeconfig, resiliencia, incidente]
---

# Postmortem · Failover bloqueado por kubeconfig incorrecto (2026-05-23)

> [!abstract] Dos problemas ortogonales que impedían el failover autonomo
> Durante la sesión del 23 de mayo de 2026 se descubrió que Lobster no era capaz de hacer failover automático cuando matrix caía. La investigación reveló dos problemas completamente distintos que se acumulaban: el kubeconfig apuntaba al clúster equivocado (matrix en lugar de leia), y la función `is_node_alive` no tenía fallback cuando la API K8s no respondía. Ambos se resolvieron en la misma sesión y el failover quedó validado en producción.

## Contexto previo

El clúster K3s de SaaSphere tiene la siguiente topología real:

- `leia` (192.168.1.200) — control-plane: corre el API server en `:6443`
- `matrix` (192.168.1.202) — worker principal: corre `k3s-agent`
- `fallback` — worker cold-standby: corre `k3s-agent` con taint `saasphere/role=fallback:NoSchedule`

Esta topología no quedó documentada correctamente desde el principio. La confusión provocó el Problema 1.

## Problema 1: kubeconfig apuntaba al clúster equivocado

### Síntoma

```
kubectl --kubeconfig=/etc/lobster/kubeconfig get nodes
→ error: ... connection refused (192.168.1.202:6443)
```

Al apagar matrix, Lobster perdía toda conectividad con K8s. Si matrix estaba el nodo que debía vigilar y también el que alojaba la API, cualquier caída de matrix hacía al agente completamente ciego.

### Causa raiz

`/etc/lobster/kubeconfig` contenía:

```yaml
server: https://192.168.1.202:6443
```

Esta URL apuntaba al k3s standalone que matrix tenía instalado por separado (como experimento previo), no al clúster principal cuyo control-plane está en leia. Adicionalmente, matrix corría dos servicios k3s en conflicto:

- `k3s.service` — servidor standalone (el antiguo experimento)
- `k3s-agent.service` — agente para unirse al clúster de leia

El `k3s-agent` de matrix fallaba porque `k3s.service` retenía el puerto 6444, impidiendo que el agente arrancara y se uniera al clúster correcto.

### Solucion

```bash
# En matrix (192.168.1.202):
sudo systemctl stop k3s
sudo systemctl disable k3s

# Liberar puerto si quedaba proceso zombie:
sudo fuser -k 6444/tcp

# Arrancar el agente correcto:
sudo systemctl start k3s-agent
sudo systemctl enable k3s-agent

# En LeIA — actualizar el kubeconfig:
# Cambiar server: https://192.168.1.202:6443 por:
# server: https://192.168.1.200:6443
sudo sed -i 's|https://192.168.1.202:6443|https://192.168.1.200:6443|g' /etc/lobster/kubeconfig

# Verificar los tres nodos:
kubectl --kubeconfig=/etc/lobster/kubeconfig get nodes
# NAME       STATUS   ROLES                  AGE   VERSION
# leia       Ready    control-plane,master   ...   v1.x.x
# matrix     Ready    <none>                 ...   v1.x.x
# fallback   Ready    <none>                 ...   v1.x.x
```

> [!tip] Explicacion para el TFG
> Este problema ilustra un error arquitectónico clásico: el kubeconfig fue generado en un momento en que matrix aún era un clúster standalone independiente, y nunca se actualizó cuando la arquitectura evolucionó. La lección es que los ficheros de configuración de infraestructura son "deuda técnica invisible" — funcionan hasta que el escenario para el que fueron creados deja de existir. En el contexto del TFG, demuestra por qué es importante documentar la topología real y revisarla periódicamente.

> [!example] Comando para la captura
> ```bash
> # Ver la IP configurada en el kubeconfig de Lobster
> grep server /etc/lobster/kubeconfig
> # Debe mostrar: https://192.168.1.200:6443
>
> # Verificar que la API responde desde LeIA
> curl -k https://192.168.1.200:6443/healthz
> # → ok
> ```

## Problema 2: is_node_alive sin fallback TCP

### Síntoma

Incluso con el kubeconfig corregido, se identificó un segundo problema potencial: si en algún escenario futuro la API K8s no respondiera (ej. reinicio del proceso k3s en leia), `is_node_alive` lanzaría `K8sClientError` y el agente no podría distinguir entre "nodo apagado" y "API temporalmente no disponible".

El modelo anterior de `NodeAliveness` solo tenía `alive: bool` y `detail: str`. Sin un campo que indicara si la API estaba disponible, el agente podía tomar decisiones equivocadas:

- API caída + nodo encendido → el agente podía inferir "nodo apagado" y activar reglas de "ambos workers bajo presión" sin base real.

### Causa raiz

`is_node_alive` en `reading.py` propagaba la excepción `K8sClientError` directamente al agente como error de tool, sin intentar ninguna verificación alternativa.

### Solucion

Se añadió un probe TCP directo como fallback. El nuevo flujo en `is_node_alive`:

1. Intentar `get_node_ready(node)` via API K8s.
2. Si hay `K8sClientError` → ejecutar `_probe_node_tcp(host, port=22, timeout=3.0)` con `asyncio.open_connection`.
3. Devolver `NodeAliveness` con el campo `api_available: bool` para que el agente distinga los tres casos:

| `alive` | `api_available` | Interpretacion |
|---|---|---|
| `True` | `True` | Nodo sano, API operativa — estado normal |
| `True` | `False` | Nodo encendido (TCP ok) pero API k3s no responde — situacion anómala, no actuar sobre scheduling |
| `False` | `False` | Nodo apagado o sin red — iniciar protocolo de failover |

Nota importante: cuando matrix cae como **worker**, la API (en leia) sigue respondiendo. Por tanto `is_node_alive('matrix')` devolverá `alive=False, api_available=True` — no es el caso de "API no disponible".

> [!tip] Explicacion para el TFG
> Este cambio añade **observabilidad de segundo nivel** al agente: cuando el canal primario (API K8s) falla, hay un canal secundario (TCP probe). En términos de sistemas distribuidos, esto implementa el patrón "health check with degraded mode" — el agente puede seguir operando (aunque con funcionalidad reducida) en lugar de bloquearse completamente. El campo `api_available` es un ejemplo concreto de cómo enriquecer el modelo de datos de una herramienta mejora la calidad del razonamiento del LLM.

> [!example] Comando para la captura
> ```bash
> # Verificar el modelo NodeAliveness directamente en el código
> grep -n "api_available\|NodeAliveness\|_probe_node_tcp" \
>   /opt/openclaw/lobster_agent/agent/tools/reading.py
> ```

## Problema 3 (secundario): LLM alucinaba "modo DRY_RUN"

### Síntoma

El agente respondía "estás en modo DRY_RUN, las acciones no se ejecutarán realmente" cuando el agente estaba en modo normal.

### Causa raiz

La instrucción sobre el modo dry_run estaba incluida siempre en el system prompt, independientemente del modo actual. El LLM leía la instrucción y la interpretaba como que el sistema estaba en ese modo.

### Solucion

La función `_dry_run_instruction(context)` en `system.py` solo añade la instrucción si `context["agent_mode"] == "dry_run"`. En cualquier otro modo el bloque ni siquiera aparece en el prompt, eliminando la ambigüedad.

> [!tip] Explicacion para el TFG
> Este bug ilustra un problema frecuente con los LLMs: el modelo no distingue entre "instrucción sobre un modo" y "el sistema está en ese modo". La solución — no incluir la instrucción si no aplica — es un ejemplo de "prompt engineering defensivo". En el TFG puede citarse como caso práctico de cómo el contexto dinámico del system prompt debe construirse condicionalmente, no como plantilla estática.

> [!example] Comando para la captura
> ```bash
> # Ver la implementacion de _dry_run_instruction
> grep -A 10 "_dry_run_instruction" \
>   /opt/openclaw/lobster_agent/agent/prompts/system.py
> ```

## Incidente K3s durante la sesion

Durante la corrección del Problema 1 se produjeron complicaciones adicionales en matrix:

**Puerto 6444 retenido por proceso zombie:**

```bash
# Síntoma
sudo systemctl start k3s-agent
# → Error: "bind: address already in use" (port 6444)

# Diagnóstico y remedio
sudo fuser -k 6444/tcp
sudo systemctl start k3s-agent
```

> [!example] Comando para la captura
> ```bash
> # Verificar si hay procesos reteniendo el puerto
> sudo ss -tlnp | grep 6444
> # Si aparece algo: sudo fuser -k 6444/tcp
> ```

**TLS mismatch tras restart de k3s:**

Después de parar y arrancar k3s en matrix, el certificado del servidor cambió. El kubeconfig antiguo (con el certificado embebido) dejaba de funcionar. La solución fue copiar el kubeconfig regenerado desde matrix y ajustar la IP:

```bash
# En matrix:
# k3s genera /etc/rancher/k3s/k3s.yaml con server: https://127.0.0.1:6443

# En LeIA (una vez confirmado que el control-plane está en leia, no en matrix):
# Esto no aplica — el kubeconfig de leia se gestiona desde leia directamente
# El kubeconfig de Lobster apunta al API server de leia: https://192.168.1.200:6443
```

## Validacion del failover en produccion

Con ambos problemas resueltos, se validó el flujo completo:

1. Usuario apaga matrix manualmente.
2. Lobster detecta `is_node_alive('matrix') → alive=False, api_available=True` en el siguiente ciclo health_loop.
3. Lobster llama `pin_deployment_to_node(namespace, deployment, 'fallback')` — acción autónoma, sin Telegram.
4. K8s ejecuta rolling update, pod arranca en fallback.
5. Servicio web accesible desde fallback con matrix apagado.

> [!example] Comando para la captura
> ```bash
> # Ver las acciones de failover registradas en el ledger
> uv run lobster actions list --limit 10
>
> # Buscar acciones de tipo pin_deployment_to_node
> sqlite3 /var/lib/lobster/state.db \
>   "SELECT id, action_type, status, created_at FROM actions \
>    WHERE action_type = 'pin_deployment_to_node' ORDER BY created_at DESC LIMIT 5;"
> ```

*(Captura manual — mostrar el pod corriendo en fallback con `kubectl get pods -A -o wide` y la web accesible en el navegador con matrix apagado)*

## Fase 2: bugs de recuperacion autonoma (tarde del 2026-05-23)

Con el failover de ida funcionando, la sesión de tarde reveló tres bugs adicionales que impedían la recuperación autónoma (el unpin cuando matrix vuelve).

---

### Bug 1 — `node_selector` nunca llegaba al LLM

#### Síntoma

`health_loop_read` nunca reportaba "[ANOMALÍA] workloads pinados a fallback con matrix recuperado" aunque los `nodeSelector` estaban presentes en los deployments. El agente simplemente no los veía.

#### Causa raiz

El modelo `DeploymentSummary` (el objeto compacto que la tool `list_deployments` devuelve al LLM) no tenía el campo `node_selector`. Cuando el agente llamaba `list_deployments`, el resultado omitía por completo la información de pinning. Para el LLM, todos los deployments parecían sin restricción de nodo.

El campo existía en el modelo de dominio `DeploymentInfo` pero no se había propagado hacia arriba al modelo de presentación.

#### Fix

Se añadió `node_selector: dict[str, str] | None = None` en tres lugares de la cadena de datos:

| Archivo | Cambio |
|---|---|
| `lobster_agent/domain/models.py` | Campo `node_selector` en `DeploymentInfo` |
| `lobster_agent/agent/tools/reading.py` | Campo `node_selector` en `DeploymentSummary`; propagado en `_deployment_summary()` |
| `lobster_agent/agent/tools/k8s_read.py` | `_deployment_info_from_deployment()` extrae `spec→template→spec→nodeSelector` |

> [!tip] Explicacion para el TFG
> Este bug ilustra el patrón de "modelo de datos que filtra demasiado". Los resúmenes compactos que se envían al LLM son necesarios para ahorrar tokens, pero si filtran un campo clave, el agente toma decisiones sobre una imagen incompleta de la realidad. La lección: cada vez que se añade una capacidad nueva al agente (aquí, el pinning), hay que auditar qué información necesita ver para detectar que esa capacidad ha sido usada.

> [!example] Comando para la captura
> ```bash
> # Ver el campo node_selector en DeploymentSummary
> grep -n "node_selector" \
>   /opt/openclaw/lobster_agent/agent/tools/reading.py
>
> # Verificar que list_deployments expone node_selector via kubectl
> kubectl --kubeconfig=/etc/lobster/kubeconfig get deployments \
>   -A -l saasphere.io/tenant=true \
>   -o custom-columns="NAME:.metadata.name,NODE:.spec.template.spec.nodeSelector"
> ```

---

### Bug 2 — `_get_attr` no encadena atributos

#### Síntoma

Tras el primer fix, `node_selector` seguía siendo `None` en `_deployment_info_from_deployment()` aunque los deployments tuvieran nodeSelector en el clúster real.

#### Causa raiz

La llamada original era:

```python
raw_selector = _get_attr(spec, "template", "spec")
```

La función `_get_attr` itera sobre los nombres que recibe como alternativas, no como cadena. Es decir, busca `spec.template` **O** `spec.spec` — toma el primero que no sea `None`. No encadena `spec → template → spec`.

Para acceder a `deployment.spec.template.spec.nodeSelector` hacen falta tres llamadas independientes:

```python
template = _get_attr(spec, "template")
pod_spec = _get_attr(template, "spec")
raw_selector = _get_attr(pod_spec, "nodeSelector", "node_selector")
```

#### Fix

Corregido en `lobster_agent/agent/tools/k8s_read.py`, función `_deployment_info_from_deployment()`:

```python
def _deployment_info_from_deployment(deployment: object) -> DeploymentInfo:
    metadata = _get_attr(deployment, "metadata")
    spec = _get_attr(deployment, "spec")
    status = _get_attr(deployment, "status")
    template = _get_attr(spec, "template")
    pod_spec = _get_attr(template, "spec")
    raw_selector = _get_attr(pod_spec, "nodeSelector", "node_selector")
    node_selector: dict[str, str] | None = None
    if isinstance(raw_selector, dict) and raw_selector:
        node_selector = {str(k): str(v) for k, v in raw_selector.items()}
    ...
```

> [!tip] Explicacion para el TFG
> La función `_get_attr` del cliente K8s usa múltiples nombres como **alternativas** (camelCase vs snake_case), no como cadena de acceso. Esto es correcto para manejar la dualidad de lightkube (que expone objetos con atributos en snake_case) frente a dicts (que usan camelCase), pero es fácil confundirlo con encadenamiento. El test que habría detectado este bug antes es uno que construya un objeto `Deployment` real con lightkube y compruebe que `node_selector` se extrae correctamente — un ejemplo de por qué los tests unitarios sobre los adaptadores de infraestructura son valiosos.

> [!example] Comando para la captura
> ```bash
> # Ver la implementacion actual de _deployment_info_from_deployment
> grep -n -A 20 "_deployment_info_from_deployment" \
>   /opt/openclaw/lobster_agent/agent/tools/k8s_read.py
> ```

---

### Bug 3 — `health_loop_read` no marcaba pins como anomalía

#### Síntoma

Incluso con `node_selector` correctamente propagado, Lobster no ejecutaba el unpin automático cuando matrix volvía a estar disponible. `health_loop_read` no reportaba ninguna anomalía aunque los deployments tuvieran `node_selector={"kubernetes.io/hostname": "fallback"}`.

#### Causa raiz

El prompt del caso de uso `HEALTH_LOOP_READ` no tenía instrucción explícita de llamar `list_deployments` en cada ciclo ni de considerar los pins como condición anómala. El ciclo de recuperación solo se disparaba si se detectaba una anomalía; pero como nada de lo que hacía el agente marcaba "pins activos con matrix recuperado" como anomalía, el ciclo de análisis nunca arrancaba.

La instrucción sobre recuperación estaba en el prompt de `HEALTH_LOOP_ANALYZE` (correcto), pero `HEALTH_LOOP_READ` necesitaba ser quien levantara la bandera primero.

#### Fix

Se añadió instrucción explícita en el system prompt de `HEALTH_LOOP_READ`:

```text
(C) Workloads pinados pendientes de devolver: llama list_deployments en cada ciclo.
Si algún deployment tiene node_selector={"kubernetes.io/hostname":"fallback"}
Y matrix está vivo (is_node_alive → alive=True, api_available=True)
→ reportar como [ANOMALÍA] workloads pinados a fallback con matrix recuperado.
```

> [!tip] Explicacion para el TFG
> Este bug muestra un problema sutil de división de responsabilidades en los system prompts. El agente tiene dos momentos en el ciclo: READ (observar y clasificar) y ANALYZE (decidir y actuar). Si READ no clasifica algo como anomalía, ANALYZE nunca lo ve. Cada condición que debe disparar una acción necesita estar explícitamente representada en READ, no solo en ANALYZE. Es un ejemplo de cómo el "diseño de prompts" tiene su propia arquitectura, tan relevante como el diseño del código.

> [!example] Comando para la captura
> ```bash
> # Ver la instruccion de recuperacion en el system prompt de HEALTH_LOOP_READ
> grep -n -A 10 "pinados\|unpin\|fallback con matrix" \
>   /opt/openclaw/lobster_agent/agent/prompts/system.py
> ```

---

## Cambios en el codigo

**Fase 1 (mañana):**

| Archivo | Cambio |
|---|---|
| `lobster_agent/domain/policy.py` | `pin_deployment_to_node` → `ActionSeverity.AUTONOMOUS` |
| `lobster_agent/agent/tools/reading.py` | `NodeAliveness` añade campo `api_available`; nueva función `_probe_node_tcp` |
| `lobster_agent/agent/tools/mutations/node.py` | Comentario actualizado: severidad AUTONOMOUS en docstring de `pin_deployment_to_node` |
| `lobster_agent/agent/prompts/system.py` | `_dry_run_instruction` condicional; instrucciones actualizadas sobre topología (leia=control-plane) y frases prohibidas (`fallback inoperable`) |
| `/etc/lobster/kubeconfig` | `server` cambiado de `https://192.168.1.202:6443` a `https://192.168.1.200:6443` |

**Fase 2 (tarde):**

| Archivo | Cambio |
|---|---|
| `lobster_agent/domain/models.py` | Campo `node_selector: dict[str, str] \| None` añadido a `DeploymentInfo` |
| `lobster_agent/agent/tools/reading.py` | Campo `node_selector` añadido a `DeploymentSummary`; propagado en `_deployment_summary()` |
| `lobster_agent/agent/tools/k8s_read.py` | `_deployment_info_from_deployment()` extrae correctamente `spec→template→spec→nodeSelector` con tres llamadas `_get_attr` independientes (Bug 2) |
| `lobster_agent/agent/prompts/system.py` | Instrucción explícita en `HEALTH_LOOP_READ` para llamar `list_deployments` y detectar pins activos como anomalía (Bug 3) |

## Lecciones aprendidas

> [!tip] Cinco lecciones de esta sesion

1. **Verifica siempre el kubeconfig antes de culpar al agente.** `kubectl --kubeconfig=/etc/lobster/kubeconfig get nodes` es el primer comando de diagnóstico — si falla, todo lo demás es ruido.
2. **Control-plane y workloads en nodos distintos.** El agente debe poder operar (leer, razonar, mutar) incluso cuando el nodo que aloja las cargas de trabajo cae. Esto requiere que la API K8s esté en un nodo separado de los workloads.
3. **Las herramientas de diagnóstico necesitan fallbacks.** Un health check que solo usa la API K8s es frágil: si la API falla, el agente queda ciego. TCP probe como segundo nivel de observabilidad elimina falsos negativos.
4. **El system prompt no es una plantilla estática.** Las instrucciones condicionales (como `_dry_run_instruction`) evitan que el LLM interprete instrucciones sobre un estado como si ese estado estuviera activo.
5. **El cambio de severidad de NORMAL a AUTONOMOUS es una decisión de política, no técnica.** Se basa en el análisis de riesgo: "mover pods a otro nodo" es reversible y urgente; "borrar datos" no. Documentar esta distinción es parte del TFG.

## Cronologia

| Hora (CEST) | Evento |
|---|---|
| 2026-05-23 11:00 | Usuario reporta que Lobster no hace failover cuando matrix cae |
| 2026-05-23 11:15 | Descubierto: kubeconfig apunta a `https://192.168.1.202:6443` (incorrecto) |
| 2026-05-23 11:30 | Identificado conflicto `k3s.service` vs `k3s-agent.service` en matrix |
| 2026-05-23 12:00 | Puerto 6444 liberado con `fuser -k`; `k3s-agent` arranca correctamente |
| 2026-05-23 12:15 | Kubeconfig actualizado a `https://192.168.1.200:6443`; tres nodos `Ready` |
| 2026-05-23 12:30 | Identificado Problema 2: `is_node_alive` sin fallback TCP |
| 2026-05-23 13:00 | Implementado `_probe_node_tcp`; `NodeAliveness.api_available` añadido |
| 2026-05-23 13:15 | Fix dry_run en system prompt (`_dry_run_instruction` condicional) |
| 2026-05-23 13:30 | `pin_deployment_to_node` cambiado a AUTONOMOUS en `policy.py` |
| 2026-05-23 14:00 | Failover de ida validado: matrix apagado, pods en fallback en ~1 min |
| 2026-05-23 14:30 | Inicio sesión tarde: descubierto Bug 1 (`node_selector` ausente de `DeploymentSummary`) |
| 2026-05-23 15:00 | Descubierto Bug 2 (`_get_attr` no encadena); fix en `_deployment_info_from_deployment` |
| 2026-05-23 15:30 | Descubierto Bug 3 (`HEALTH_LOOP_READ` no marcaba pins como anomalía); fix en system prompt |
| 2026-05-23 16:15 | Ciclo completo validado: failover + recuperación autónoma con 3 tenants reales |
| 2026-05-23 17:00 | Postmortem actualizado con Fase 2 |

→ Ver [[08-Failover-y-recuperacion]] para el procedimiento operativo completo.
→ Ver [[../03-Tools/08-Mutations-Nodes]] para el detalle de `pin_deployment_to_node` y `is_node_alive`.
