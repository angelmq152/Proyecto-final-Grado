---
title: Failover automático y recuperación de nodos
tags: [operacion, failover, resilencia, k3s, pin, matrix, fallback]
---

# Failover automático y recuperación de nodos

> [!abstract] Autonomía de Lobster ante la caída de un worker
> Cuando el nodo `matrix` (worker principal del clúster K3s) cae o se satura, Lobster detecta el problema en el siguiente ciclo `health_loop`, mueve las cargas de trabajo al nodo `fallback` sin pedir aprobación humana, y revierte el movimiento de forma igualmente autónoma cuando matrix se recupera. Esta capacidad valida el concepto de **orquestación autónoma con supervisión humana selectiva**: las acciones de bajo riesgo (relocación de pods) son autónomas; las de alto riesgo (borrado de tenants) siguen requiriendo confirmación.

## Arquitectura de nodos relevante

El clúster K3s de SaaSphere tiene tres nodos:

| Nodo | Rol K3s | Schedulable para tenants |
|---|---|---|
| `leia` (192.168.1.200) | control-plane (API server) | No — taint `master:NoSchedule` |
| `matrix` (192.168.1.202) | worker principal | Si — recibe toda la carga por defecto |
| `fallback` | worker cold-standby | Si — taint `saasphere/role=fallback:NoSchedule` (requiere tolerations) |

El taint en fallback significa que ningún pod llega ahí de forma ordinaria. Solo cuando Lobster ejecuta `pin_deployment_to_node` con el target `fallback`, añade las tolerations necesarias y el pod migra.

> [!tip] Explicacion para el TFG
> La separación control-plane / worker es fundamental para la resiliencia del agente. Cuando `matrix` cae, la API K8s (en `leia`) sigue operativa. Lobster puede seguir consultando el estado del clúster, leer eventos, y ejecutar mutaciones. Un diseño donde el control-plane estuviera en el mismo nodo que los workloads haría que el agente quedara ciego justo cuando más falta hace.

> [!example] Comando para la captura
> ```bash
> # Verificar los tres nodos del cluster (ejecutar en LeIA)
> kubectl --kubeconfig=/etc/lobster/kubeconfig get nodes -o wide
> ```

## Flujo de failover: caida de matrix

### Fase 1 — Deteccion

El job `health_loop` (APScheduler, cada ~60 s) ejecuta el caso de uso `HEALTH_LOOP_READ`. El agente llama a `is_node_alive('matrix')`, que primero consulta la API K8s:

- Si matrix está `Ready=True` → `alive=True, api_available=True` — no hay nada que hacer.
- Si matrix no está Ready → `alive=False, api_available=True` — la API (en leia) sigue respondiendo, matrix simplemente no está Ready.
- Si la API K8s tampoco responde (situación anómala) → el código hace un **TCP probe** directo al puerto 22 del nodo para distinguir si el nodo está apagado o si es un problema del API server.

> [!tip] Explicacion para el TFG
> El campo `api_available` del modelo `NodeAliveness` es el resultado concreto de la sesión 2026-05-23. Antes de este cambio, si la API no respondía, Lobster no podía distinguir "matrix apagado" de "problema de red con el control-plane". Con el TCP probe como fallback, el agente tiene tres estados observacionales en lugar de dos, lo que elimina falsos negativos en el diagnóstico.

> [!example] Comando para la captura
> ```bash
> # Simular la consulta que hace is_node_alive via la API K8s
> kubectl --kubeconfig=/etc/lobster/kubeconfig get node matrix -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
> ```

### Fase 2 — Analisis y decision

En el ciclo `HEALTH_LOOP_ANALYZE`, el agente recibe el estado de los nodos y decide si actuar. El system prompt establece estas reglas:

1. Si matrix está caído (`alive=False`) y fallback está disponible (`alive=True`, recursos < umbral) → **actuar autónomamente**: llamar `pin_deployment_to_node` para cada deployment de tenant con matrix caído.
2. Si **ambos** workers están bajo presión de recursos → **no actuar**, notificar al operador.
3. Si `alive=True, api_available=False` para un nodo → el nodo está encendido pero la API no responde — informar sin actuar de forma destructiva.

> [!danger] Regla de seguridad critica
> Si fallback también está saturado o caído, Lobster NO migra ningún workload. Mover pods a un nodo ya al límite empeoraría la situación. Esta regla está codificada en el system prompt: *"Si fallback también está bajo presión (según get_node_health), notifica al operador y NO actúes."*

### Fase 3 — Accion autonoma: pin a fallback

`pin_deployment_to_node(namespace, deployment_name, 'fallback')` tiene severidad `AUTONOMOUS` — no requiere aprobación Telegram. La herramienta:

1. Lee el `nodeSelector` actual del Deployment.
2. Lee las `tolerations` actuales.
3. Lee los taints del nodo `fallback` (normalmente `saasphere/role=fallback:NoSchedule`).
4. Genera las tolerations necesarias automáticamente.
5. Aplica un único `patch` al Deployment con `nodeSelector: {kubernetes.io/hostname: fallback}` y las tolerations.
6. K8s hace rolling update: el pod anterior termina, el nuevo arranca en fallback.

> [!tip] Explicacion para el TFG
> La autonomía de `pin_deployment_to_node` es una decisión de diseño deliberada adoptada en la sesión 2026-05-23: antes tenía severidad `NORMAL` (requería aprobación humana). El razonamiento es que ante una caída de nodo, el tiempo de reacción es crítico. Pedir aprobación para migrar pods cuando el operador puede estar dormido o sin conexión haría inútil la capacidad de failover. La aprobación se reserva para acciones que modifican el estado de forma potencialmente irreversible (escalar a cero, borrar tenants).

> [!example] Comando para la captura
> ```bash
> # Ver el nodeSelector actual de todos los deployments de tenant
> kubectl --kubeconfig=/etc/lobster/kubeconfig get deployments \
>   -A -l saasphere.io/tenant=true \
>   -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,NODE:.spec.template.spec.nodeSelector"
> ```

*(Captura manual — mostrar en Telegram el mensaje de Lobster confirmando el pin, con el nombre del deployment y el nodo destino)*

### Fase 4 — Verificacion post-failover

> [!example] Comando para la captura
> ```bash
> # Confirmar que el pod corre en fallback
> kubectl --kubeconfig=/etc/lobster/kubeconfig get pods \
>   -A -l saasphere.io/tenant=true -o wide \
>   | grep fallback
>
> # Verificar que el servicio responde (tenant de ejemplo: saasphere)
> curl -s -o /dev/null -w "%{http_code}\n" \
>   --resolve saasphere.saasphere.local:80:192.168.1.240 \
>   http://saasphere.saasphere.local/
> ```

## Recuperacion: vuelta a matrix

Cuando matrix vuelve a estar `Ready` y lleva al menos 15 minutos por debajo del umbral de CPU/memoria (70 % por defecto), el `health_loop` detecta "workloads pinados a fallback con matrix recuperado" y llama automáticamente a `unpin_deployment_from_node`. Esta acción:

- Elimina el `nodeSelector` del Deployment.
- Elimina solo las tolerations con prefijo `saasphere/` (las que añadió `pin`).
- K8s reprograma el pod libremente — normalmente vuelve a matrix (tiene `preferredDuringScheduling` con weight=100 hacia matrix en los manifests).

> [!tip] Explicacion para el TFG
> El unpin también es autónomo. La lógica de que "quitar una restricción es más seguro que poner una" es académicamente interesante: demuestra que la política de aprobación no es binaria (todo o nada) sino proporcional al riesgo de cada operación. Esto conecta con los conceptos de "supervisión humana selectiva" y "autonomía calibrada por riesgo" que aparecen en la literatura de agentes IA.

> [!example] Comando para la captura
> ```bash
> # Ver el ledger de acciones autonomas de failover/recuperacion
> uv run lobster actions list --limit 20
>
> # Buscar decisiones de health_loop relacionadas con nodos
> uv run lobster decisions list --limit 10
> ```

## Diagrama ASCII del flujo completo

```
health_loop (cada ~60s)
        │
        ▼
HEALTH_LOOP_READ
  is_node_alive('matrix')
        │
        ├─ alive=True, api_available=True ────────────────► sin accion
        │
        ├─ alive=False, api_available=True
        │   (matrix caido, API k3s de leia OK)
        │        │
        │        ▼
        │   HEALTH_LOOP_ANALYZE
        │   is_node_alive('fallback') ?
        │        │
        │        ├─ fallback saturado ──────────────────► alerta al operador
        │        │                                         NO actuar
        │        │
        │        └─ fallback disponible
        │                 │
        │                 ▼
        │           pin_deployment_to_node    ← AUTONOMO (sin aprobacion)
        │           (namespace, deploy, 'fallback')
        │                 │
        │                 ▼
        │           K8s rolling update
        │           pod arranca en fallback
        │                 │
        │                 ▼
        │           workload accesible ────────────────► notifica Telegram
        │
        └─ alive=True, api_available=False
            (nodo encendido, API no responde — caso anómalo)
                     │
                     ▼
               informa al operador, no actua
               sobre scheduling

──────────────────────────────────────────────────────────

matrix se recupera
        │
        ▼
health_loop: matrix Ready + CPU/mem < 70% durante 15 min
        │
        ▼
HEALTH_LOOP_ANALYZE
list_deployments con nodeSelector=fallback
        │
        ▼
unpin_deployment_from_node    ← AUTONOMO
(elimina nodeSelector + tolerations saasphere/*)
        │
        ▼
K8s reprograma pod → vuelve a matrix
```

→ Ver [[../03-Tools/08-Mutations-Nodes]] para el detalle de cada tool.
→ Ver [[09-Postmortem-Failover-Kubeconfig-2026-05-23]] para el incidente que validó este flujo en producción.

---

## Ciclo completo validado (2026-05-23 tarde)

El 23 de mayo de 2026, una vez resueltos los bugs de kubeconfig e `is_node_alive` (documentados en el postmortem), se ejecutó el ciclo completo de failover y recuperación con tres tenants reales en producción: `langosta`, `pepinillo` y `saasphere`.

### Preparación previa

Los tres tenants estaban corriendo en el nodo `fallback` con `nodeSelector` explícito, configurado manualmente tras pruebas previas. Para validar el ciclo completo desde cero, se eliminaron esos selectores mediante `kubectl patch`:

```bash
# Quitar el nodeSelector de cada deployment (ejecutar en LeIA)
for ns in langosta pepinillo saasphere; do
  kubectl --kubeconfig=/etc/lobster/kubeconfig patch deployment $ns \
    -n $ns \
    --type=json \
    -p='[{"op":"remove","path":"/spec/template/spec/nodeSelector"}]'
done
```

Los pods migraron solos a `matrix` gracias a la afinidad `preferredDuringScheduling` con `weight=100` hacia matrix que incluyen los manifests de Jinja2.

**Problema puntual con saasphere:** el namespace `saasphere` tiene una `ResourceQuota` configurada exactamente para un pod (200 m CPU, 256 Mi memoria). El rolling update intenta crear el nuevo pod antes de borrar el viejo, lo que agota la quota y bloquea la transición. Fue necesario borrar el pod viejo manualmente:

```bash
# Identificar el pod viejo de saasphere bloqueando el rolling update
kubectl --kubeconfig=/etc/lobster/kubeconfig get pods -n saasphere

# Borrar el pod viejo para desbloquear el rolling update
kubectl --kubeconfig=/etc/lobster/kubeconfig delete pod \
  -n saasphere $(kubectl --kubeconfig=/etc/lobster/kubeconfig get pods \
  -n saasphere -o jsonpath='{.items[0].metadata.name}')
```

> [!warning] Problema de quota en saasphere
> Este workaround manual revela una limitación de diseño: una `ResourceQuota` igual al límite de un pod bloquea cualquier rolling update. Mientras no se suba la quota o se cambie la estrategia a `Recreate`, los despliegues de saasphere requieren intervención manual. Ver [[../12-Decisiones-Limitaciones/07-Quota-Saasphere-Rolling-Update]] para el análisis completo.

### Ejecucion del failover (~16:15 CEST)

1. El operador desconectó físicamente la red del nodo `matrix` a las ~16:15 CEST.
2. K8s tardó aproximadamente 40 segundos en marcar matrix como `NotReady` (tiempo de gracia del node controller).
3. El ciclo `health_loop_read` de las 16:15 detectó el estado anómalo:

```
is_node_alive('matrix') → alive=False, api_available=True
[ANOMALÍA] matrix caído
```

El campo `api_available=True` confirmaba que la API K8s (en leia, 192.168.1.200) seguía operativa — solo el worker estaba caído.

4. El scheduler ejecutó `pre_analyze`: force-deleted los tres pods atascados en `Terminating` en matrix (los pods no podían terminar limpiamente con el nodo desconectado).
5. El ciclo `health_loop_analyze` de las 16:15 llamó `pin_deployment_to_node` de forma autónoma para los tres tenants:

| Tenant | Accion | Estado |
|---|---|---|
| `langosta/langosta` | `pin_deployment_to_node` → fallback | `completed autonomous` |
| `pepinillo/pepinillo` | `pin_deployment_to_node` → fallback | `completed autonomous` |
| `saasphere/saasphere` | `pin_deployment_to_node` → fallback | `completed autonomous` |

Los tres pods estaban corriendo en `fallback` aproximadamente 1 minuto después de la desconexión.

> [!tip] Explicacion para el TFG
> El tiempo total de recuperación —desde la desconexión de red hasta el pod corriendo en fallback— fue de aproximadamente 1 minuto. Este dato es relevante académicamente: demuestra que la combinación "detección por API K8s + acción autónoma sin aprobación" produce un RTO (Recovery Time Objective) en el orden de los 60 segundos, comparable a soluciones de HA comerciales, pero implementado con un agente LLM sobre infraestructura doméstica.

> [!example] Comando para la captura
> ```bash
> # Ver las acciones de pin registradas en el ledger (ejecutar en LeIA)
> uv run lobster actions list --limit 10
>
> # Confirmar los pods corriendo en fallback con matrix desconectado
> kubectl --kubeconfig=/etc/lobster/kubeconfig get pods \
>   -A -l saasphere.io/tenant=true -o wide | grep fallback
> ```

*(Captura manual — mostrar el ledger con las 3 acciones `pin_deployment_to_node` en estado `completed autonomous`, y los pods corriendo en fallback con matrix en `NotReady`)*

### Recuperacion automatica

1. El operador reconectó la red de matrix.
2. K8s marcó matrix como `Ready` en el siguiente ciclo.
3. El ciclo `health_loop_read` detectó la situación:

```
list_deployments → node_selector={"kubernetes.io/hostname":"fallback"} (los 3 tenants)
is_node_alive('matrix') → alive=True, api_available=True
[ANOMALÍA] workloads pinados a fallback con matrix recuperado
```

4. El ciclo `health_loop_analyze` llamó `unpin_deployment_from_node` autónomamente para los tres tenants. Los pods volvieron a `matrix` sin intervención humana.

> [!tip] Explicacion para el TFG
> La recuperación autónoma exige que `list_deployments` exponga el campo `node_selector` al LLM. Este campo fue añadido específicamente en esta sesión tras descubrir que el agente no podía detectar los pins porque el modelo de datos no lo incluía. Es un ejemplo concreto del ciclo "observar → diagnosticar → corregir el modelo de datos → revalidar", que es parte del proceso de desarrollo iterativo descrito en el TFG.

> [!example] Comando para la captura
> ```bash
> # Ver el ledger completo de la sesion (pin + unpin)
> uv run lobster actions list --limit 20
>
> # Ver el node_selector actual de los deployments (deberia estar vacio tras unpin)
> kubectl --kubeconfig=/etc/lobster/kubeconfig get deployments \
>   -A -l saasphere.io/tenant=true \
>   -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,NODE:.spec.template.spec.nodeSelector"
> ```

### Ledger final de la sesion

```
completed  autonomous  unpin_deployment_from_node  langosta/langosta
completed  autonomous  unpin_deployment_from_node  pepinillo/pepinillo
completed  autonomous  unpin_deployment_from_node  saasphere/saasphere
completed  autonomous  pin_deployment_to_node      saasphere/saasphere
completed  autonomous  pin_deployment_to_node      pepinillo/pepinillo
completed  autonomous  pin_deployment_to_node      langosta/langosta
```

> [!example] Comando para la captura
> ```bash
> # Reproducir el ledger con sqlite directamente
> sqlite3 /var/lib/lobster/state.db \
>   "SELECT status, severity, action_type, namespace || '/' || target_name \
>    FROM actions \
>    WHERE action_type IN ('pin_deployment_to_node','unpin_deployment_from_node') \
>    ORDER BY created_at DESC LIMIT 10;"
> ```

## Diagrama ASCII del ciclo completo validado

```
ESTADO INICIAL: 3 tenants en matrix (sin nodeSelector)
        │
        ▼
Operador desconecta matrix (~16:15 CEST)
        │
        ▼ (~40 s)
K8s: matrix → NotReady
        │
        ▼
┌─────────────────────────────────────────────┐
│  health_loop_read (16:15)                   │
│  is_node_alive('matrix')                    │
│  → alive=False, api_available=True          │
│  [ANOMALÍA] matrix caído                    │
└─────────────────────────────────────────────┘
        │
        ▼
scheduler.pre_analyze
force-delete pods Terminating en matrix
        │
        ▼
┌─────────────────────────────────────────────┐
│  health_loop_analyze (16:15)                │
│  is_node_alive('fallback') → OK             │
│  pin_deployment_to_node × 3 [AUTONOMOUS]    │
└─────────────────────────────────────────────┘
        │
        ▼ (~1 min total desde desconexión)
3 pods corriendo en fallback
        │
        ▼
Operador reconecta matrix
        │
        ▼
K8s: matrix → Ready
        │
        ▼
┌─────────────────────────────────────────────┐
│  health_loop_read (siguiente ciclo)         │
│  list_deployments → node_selector=fallback  │
│  is_node_alive('matrix') → alive=True       │
│  [ANOMALÍA] workloads pinados a fallback    │
│             con matrix recuperado           │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│  health_loop_analyze                        │
│  unpin_deployment_from_node × 3 [AUTONOMOUS]│
└─────────────────────────────────────────────┘
        │
        ▼
3 pods de vuelta en matrix
        │
        ▼
ESTADO FINAL: 3 tenants en matrix (sin nodeSelector)
              — identico al estado inicial
```

→ Ver [[09-Postmortem-Failover-Kubeconfig-2026-05-23]] para los bugs de implementación encontrados durante esta sesión.
→ Ver [[../12-Decisiones-Limitaciones/07-Quota-Saasphere-Rolling-Update]] para el problema de quota de saasphere.
