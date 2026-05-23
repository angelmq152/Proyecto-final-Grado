---
title: Limitación — ResourceQuota de saasphere bloquea rolling updates
tags: [limitaciones, kubernetes, quota, saasphere, rolling-update, pendiente]
---

# Limitacion — ResourceQuota de saasphere bloquea rolling updates

> [!abstract] Un rolling update necesita espacio para dos pods; la quota solo permite uno
> El namespace `saasphere` tiene una `ResourceQuota` configurada exactamente para los límites de un solo pod (200 m CPU, 256 Mi memoria). Cuando K8s ejecuta un rolling update (ya sea por un cambio de imagen, un cambio de nodeSelector o cualquier otra modificación al pod template), intenta crear el nuevo pod **antes** de terminar el viejo. En ese instante hay dos pods intentando coexistir, lo que supera la quota y bloquea el despliegue. El rolling update queda indefinidamente en espera hasta que alguien borra el pod viejo manualmente.

## Contexto

La quota fue configurada de este modo como medida de control de recursos: el tenant `saasphere` es la landing page del proyecto (contenido estático o webapp ligera) y no debería consumir más de 200 m CPU ni 256 Mi de memoria en ningún momento. La intención era correcta, pero la implementación no tuvo en cuenta la mecánica de los rolling updates.

El problema se manifestó por primera vez de forma evidente el 2026-05-23 durante el test de failover: al desactivar el `nodeSelector` de fallback para que los pods migrasen a matrix, el rolling update de `saasphere` quedó bloqueado mientras los de `langosta` y `pepinillo` completaron sin problema (estos namespaces no tenían quota tan ajustada).

> [!tip] Explicacion para el TFG
> Esta limitación es un ejemplo clásico de la tensión entre **control de recursos** y **operabilidad**. Kubernetes permite definir quotas con mucha granularidad, pero sin comprender la interacción con las estrategias de despliegue, una configuración aparentemente razonable produce comportamientos inesperados en operaciones rutinarias. Para el TFG, ilustra la importancia de validar la configuración de infraestructura no solo en estado estacionario sino también durante las transiciones (deploys, failovers, actualizaciones).

## Diagnostico

El síntoma visible es que el Deployment de saasphere se queda con `0/1` pods disponibles y los eventos del namespace muestran:

> [!example] Comando para la captura
> ```bash
> # Ver el estado del deployment de saasphere
> kubectl --kubeconfig=/etc/lobster/kubeconfig get deployment saasphere -n saasphere
>
> # Ver los eventos de quota del namespace
> kubectl --kubeconfig=/etc/lobster/kubeconfig get events -n saasphere \
>   --field-selector reason=FailedCreate \
>   --sort-by='.lastTimestamp'
>
> # Ver la quota actual
> kubectl --kubeconfig=/etc/lobster/kubeconfig describe resourcequota -n saasphere
> ```

El evento de error es del tipo:
```
Error creating: pods "saasphere-xxx" is forbidden:
exceeded quota: saasphere-quota,
requested: requests.cpu=200m,requests.memory=256Mi,
used: requests.cpu=200m,requests.memory=256Mi,
limited: requests.cpu=200m,requests.memory=256Mi
```

## Opciones de solucion

### Opcion A — Subir la quota para permitir 2 pods temporalmente (recomendada)

Doblar los límites de la quota:

```bash
kubectl --kubeconfig=/etc/lobster/kubeconfig patch resourcequota saasphere-quota \
  -n saasphere \
  --type=merge \
  -p='{"spec":{"hard":{"requests.cpu":"400m","requests.memory":"512Mi","limits.cpu":"400m","limits.memory":"512Mi"}}}'
```

Ventaja: sin cambios en el manifest del tenant; el rolling update funciona de forma natural.  
Inconveniente: durante el rolling update hay picos de consumo de hasta 2x los recursos nominales. En un homelab con recursos limitados, esto puede ser aceptable.

> [!tip] Explicacion para el TFG
> Esta es la solución estándar en producción: la quota debe ser al menos 2x el tamaño de un pod para permitir rolling updates. En equipos grandes, se usa `maxSurge=1` en la estrategia de despliegue junto con quotas dimensionadas para `replicas + maxSurge` pods simultáneos.

### Opcion B — Cambiar la estrategia a `Recreate`

```bash
kubectl --kubeconfig=/etc/lobster/kubeconfig patch deployment saasphere \
  -n saasphere \
  --type=merge \
  -p='{"spec":{"strategy":{"type":"Recreate"}}}'
```

Ventaja: nunca hay más de un pod. La quota no se supera.  
Inconveniente: hay un periodo de **downtime** entre que el pod viejo termina y el nuevo arranca. Para la landing page de SaaSphere esto podría ser aceptable (unos segundos), pero no es ideal.

> [!warning] `Recreate` implica downtime
> Con estrategia `Recreate`, el pod viejo se borra antes de crear el nuevo. Si el nuevo tarda en arrancar (imagen grande, CrashLoopBackOff, etc.), el servicio está caído durante ese tiempo. En producción real esto sería inaceptable para la mayoría de servicios web.

### Opcion C — Cambiar la estrategia a `RollingUpdate` con `maxSurge=0`

```bash
kubectl --kubeconfig=/etc/lobster/kubeconfig patch deployment saasphere \
  -n saasphere \
  --type=merge \
  -p='{"spec":{"strategy":{"type":"RollingUpdate","rollingUpdate":{"maxSurge":0,"maxUnavailable":1}}}}'
```

Ventaja: sin cambios en la quota; el pod viejo se borra antes de crear el nuevo.  
Inconveniente: comportamiento equivalente a `Recreate` en términos de disponibilidad (siempre hay un instante sin pod disponible). Técnicamente diferente pero el resultado observable es el mismo.

## Workaround actual

Mientras no se adopte ninguna de las opciones anteriores, el procedimiento manual cuando un rolling update de saasphere queda bloqueado es:

```bash
# 1. Identificar el pod viejo que bloquea la quota
kubectl --kubeconfig=/etc/lobster/kubeconfig get pods -n saasphere

# 2. Borrar el pod viejo (K8s creará el nuevo inmediatamente)
kubectl --kubeconfig=/etc/lobster/kubeconfig delete pod \
  -n saasphere <nombre-del-pod-viejo>

# 3. Verificar que el nuevo pod arranca
kubectl --kubeconfig=/etc/lobster/kubeconfig get pods -n saasphere -w
```

> [!danger] Este workaround implica downtime breve
> Al borrar el pod viejo antes de que el nuevo esté Ready, hay un instante en que no hay ningún pod disponible para saasphere. El tiempo de downtime depende de la velocidad de arranque del contenedor (normalmente < 10 segundos para una imagen ya cacheada).

## Estado actual

| Campo | Valor |
|---|---|
| Detectado | 2026-05-23 |
| Manifiesto afectado | `lobster_agent/manifests/static_site.yaml.j2` (o `web_app.yaml.j2` según tipo de tenant) |
| Workaround activo | Borrado manual del pod viejo |
| Solución elegida | Pendiente de decisión |
| Prioridad | Media — solo afecta a saasphere; los otros tenants no tienen quota tan ajustada |

## Relacion con Lobster

Lobster no detecta actualmente este estado bloqueado como una anomalía. El deployment aparece como `0/1 available` pero Lobster lo trataría genéricamente como "pod no listo", no como "rolling update bloqueado por quota". Una mejora futura sería que `health_loop_read` llamara `list_recent_events(namespace, minutes=5)` y detectara eventos `FailedCreate` con texto `exceeded quota` para reportarlos con instrucciones específicas de resolución.

> [!tip] Explicacion para el TFG
> La incapacidad de Lobster para distinguir "pod no listo por error de aplicación" de "pod no listo porque la quota bloquea el rolling update" es un ejemplo de la dificultad de observabilidad semántica: los síntomas superficiales son iguales pero las causas y soluciones son completamente distintas. Añadir patrones de detección para errores de quota es un ejemplo concreto del trabajo de "refinamiento del agente" que es parte del proceso iterativo del TFG.

→ Ver [[../10-Operacion/08-Failover-y-recuperacion]] para el contexto en que se detectó este problema.
→ Ver [[02-Limitaciones-actuales]] para otras limitaciones del proyecto.
