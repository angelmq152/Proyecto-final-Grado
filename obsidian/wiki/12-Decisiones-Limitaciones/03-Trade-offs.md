---
title: Trade-offs
tags: [decisiones, tradeoffs, tfg, academico]
---

# ⚖️ Trade-offs

> [!abstract] A vs B y por qué A
> Compendio de elecciones donde había una alternativa razonable y se eligió una específica. Cada trade-off lista la ventaja conseguida y el coste asumido.

## 🚆 Simplicidad vs Sofisticación

### Cola FIFO sin prioridades (Fase 9)

| Ventaja conseguida | Coste asumido |
|---|---|
| Código simple, sin bugs de starvation | Daily summary puede retrasar alert_reactive |

> Razón: el % de runs donde un alert_reactive entra detrás de un daily_summary es < 1 %. No vale la complejidad.

### SQLite vs Postgres

| Ventaja conseguida | Coste asumido |
|---|---|
| Cero infra adicional, deploy trivial | No multi-writer, no escalable a multi-instancia |

> Razón: homelab single-instance.

## 🧠 Calidad vs Latencia

### qwen3:8b para health_loop_read

| Ventaja conseguida | Coste asumido |
|---|---|
| 15-30 s de respuesta | A veces miss anomalías sutiles |

> Razón: lo importante es ejecutar cada 5 min sin retrasos. Si miss una vez, la siguiente la pillará.

### qwen3:32b para daily_summary

| Ventaja conseguida | Coste asumido |
|---|---|
| Texto coherente, secciones bien escritas | 10-30 min por job, sin uso GPU para otros mientras |

> Razón: el informe se lee por un humano. Calidad importa. Solo una vez al día.

## 🔒 Seguridad vs Usabilidad

### Approval bloqueante con poll SQLite

| Ventaja conseguida | Coste asumido |
|---|---|
| Flujo lineal LLM simple | Agent "ocupado" durante minutos esperando |

> Razón: la alternativa (command pattern asíncrono) introduce mucha complejidad para un beneficio marginal.

### `delete_tenant` con confirmación textual

| Ventaja conseguida | Coste asumido |
|---|---|
| Imposible borrar tenant por error | El LLM tiene que generar el namespace dos veces literalmente |

> Razón: borrar un tenant es destruction permanente. Una capa extra de "type it twice" vale la pena.

## 🧪 Determinismo vs Flexibilidad

### Severidad calculada en código, no por LLM

| Ventaja conseguida | Coste asumido |
|---|---|
| El LLM no puede "escapar" pidiendo AUTONOMOUS para algo crítico | No hay matiz: scale_deployment 0 → CRITICAL, siempre |

> Razón: dejar al LLM decidir su propia severidad es una superficie de ataque. Mejor reglas en `policy.py` testeables.

### CaseUse fijo determina modelo y think

| Ventaja conseguida | Coste asumido |
|---|---|
| Predicibilidad operativa | No se puede pedir "razona con 32b y think" en el momento |

> Razón: cada `CaseUse` tiene un coste/latencia conocido. Métricas estables.

## 💾 Persistencia vs Ligereza

### Decisiones siempre persistidas

| Ventaja conseguida | Coste asumido |
|---|---|
| Auditoría total | ~500 filas/día → 150 MB/año |

> Razón: la trazabilidad es la primera línea de defensa contra "qué demonios hizo el agente". Esos 150 MB son nada.

### Conversation turns SIN TTL

| Ventaja conseguida | Coste asumido |
|---|---|
| Historial completo recuperable | Tabla crece sin límite |

> Razón: en práctica son 30 turnos/día. ~10k filas/año. Insignificante.

## 🚦 Estricto vs Permisivo

### `enforce_resource_limits = True` por default

| Ventaja conseguida | Coste asumido |
|---|---|
| Manifests sin limits se rechazan | Operador no puede aplicar un manifest "rápido y sucio" |

> Razón: en homelab los limits son la única protección contra runaway pods. Mejor forzar.

### `StrictUndefined` en Jinja2

| Ventaja conseguida | Coste asumido |
|---|---|
| Template silenciosamente vacío imposible | Bug visible al primer renderizado |

> Razón: errores ruidosos > errores silenciosos.

## 📡 Pull vs Push

### Prometheus scrape (pull)

| Ventaja conseguida | Coste asumido |
|---|---|
| Lobster no necesita saber dónde está Prom | Latencia añadida de scrape interval |

> Razón: paradigma Prom estándar.

### Loki push (HTTP POST)

| Ventaja conseguida | Coste asumido |
|---|---|
| Lobster decide cuándo flushear | Si Loki cae, los logs se pierden hasta que vuelve |

> Razón: queremos visibilidad en tiempo real. Promtail sería otra opción pero introduce un agente más.

## 🚏 Autonomía vs Control

### Restart_pod autónomo en CrashLoopBackOff

| Ventaja conseguida | Coste asumido |
|---|---|
| El operador no recibe spam de aprobaciones por cosas obvias | Si el agente se equivoca, restartea sin avisar |

> Razón: en SaaSphere los CrashLoopBackOff son frecuentes (apps inestables del tenant). Pedir aprobación cada vez sería ruidoso. El restart es reversible (peor caso: vuelve a CrashLoop, próximo ciclo se intenta de nuevo, eventualmente notify).

### Pause_tenant requiere aprobación

| Ventaja conseguida | Coste asumido |
|---|---|
| El operador sabe si su tenant fue pausado | Si el agente decide hibernar tres tenants, son 3 mensajes |

> Razón: scale-to-zero es visible al usuario final ("mi web no responde"). Confirmación humana.

→ Sigue en [[04-Riesgos]].
