---
tags: [alertmanager, sauron, monitoring, incidente, fix, tfg]
created: 2026-05-17T00:55:00+02:00
closed: 2026-05-17T01:05:00+02:00
status: resuelto
---

# Fix routing Alertmanager — Telegram + Lobster — 2026-05-17

> [!info] Síntoma reportado
> *"No me están llegando alertas del Alertmanager por Telegram, creo que solo le llegan a Lobster o algo así."*

---

## 1. Diagnóstico

### Configuración previa (incorrecta)

`/opt/monitoring/alertmanager/alertmanager.yml` en `sauron`:

```yaml
route:
  group_by: ['alertname', 'instance']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 12h
  receiver: telegram          # default — solo si NINGUNA subroute matchea
  routes:
    - receiver: lobster
      continue: true
```

### Causa raíz

En Alertmanager las **subroutes se evalúan antes** que el receiver del padre. La subroute `lobster` no tenía matchers, así que **toda** alerta hacía match y se enrutaba allí. El `continue: true` sólo continúa evaluando subroutes **hermanas** (no había ninguna), y nunca cae de vuelta al `receiver: telegram` de la raíz.

> [!danger] Consecuencia
> El `receiver: telegram` raíz **nunca se invocaba**. Telegram quedó silenciado durante todo el periodo en el que la subroute `lobster` estuvo desplegada.

### Evidencia en logs

`docker logs alertmanager` mostraba sólo entregas a `receiver=lobster` (con errores `connect: no route to host` cuando leia estaba caída), cero líneas con `receiver=telegram`:

```
ts=2026-05-16T11:51:49Z ... receiver=lobster integration=webhook[0] aggrGroup=...{alertname="LobsterSinActividad", instance="leia"} ... err="...dial tcp 192.168.1.200:8080: connect: no route to host"
ts=2026-05-16T12:20:18Z ... receiver=lobster integration=webhook[0] aggrGroup=...{alertname="NodoInaccesible", instance="leia"} msg="Notify success"
```

---

## 2. Fix aplicado

### Backup

```bash
cp /opt/monitoring/alertmanager/alertmanager.yml \
   /opt/monitoring/alertmanager/alertmanager.yml.bak.20260517-005952
```

### Nueva configuración

`/opt/monitoring/alertmanager/alertmanager.yml`:

```yaml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'instance']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 12h
  receiver: telegram
  routes:
    - receiver: telegram
      continue: true
    - receiver: lobster
      continue: true

receivers:
  - name: telegram
    telegram_configs:
      - bot_token: '<redacted>'
        chat_id: 5857999164
        message: |
          🚨 *{{ .Status | toUpper }}* — {{ .CommonLabels.alertname }}
          📍 *Nodo:* {{ .CommonLabels.instance }}
          📝 {{ .CommonAnnotations.summary }}
          {{ if eq .Status "resolved" }}✅ Recuperado{{ end }}
        parse_mode: Markdown

  - name: lobster
    webhook_configs:
      - url: 'http://192.168.1.200:8080/webhook/alert'
        send_resolved: true
```

### Recarga sin reinicio

```bash
curl -X POST http://localhost:9093/-/reload  # HTTP 200
```

Log de Alertmanager confirma:

```
ts=2026-05-16T23:00:04Z caller=coordinator.go level=info msg="Loading configuration file" file=/etc/alertmanager/alertmanager.yml
ts=2026-05-16T23:00:04Z caller=coordinator.go level=info msg="Completed loading of configuration file"
```

---

## 3. Por qué funciona el nuevo routing

| Elemento | Comportamiento |
|---|---|
| Subroute 1 `telegram` (sin matchers) | Matchea **toda** alerta → envía a Telegram |
| `continue: true` en subroute 1 | Permite seguir evaluando subroutes hermanas |
| Subroute 2 `lobster` (sin matchers) | Matchea **toda** alerta → envía webhook a Lobster |
| `continue: true` en subroute 2 | Inofensivo (no hay más hermanas) |
| `receiver: telegram` raíz | Sigue siendo default; no se invoca porque siempre hay subroutes que matchean |

> [!tip] Alternativa equivalente
> También funcionaría un único receiver `telegram-and-lobster` que combine `telegram_configs` y `webhook_configs` en el mismo bloque. La variante con dos subroutes es más explícita y permite añadir matchers (por severidad, por ejemplo) si en el futuro se quiere enrutar selectivamente.

---

## 4. Verificación

### Test alert disparada

```bash
curl -X POST http://localhost:9093/api/v2/alerts \
  -H 'Content-Type: application/json' \
  -d '[{"labels":{"alertname":"TestRoutingTelegram","instance":"sauron","severity":"info"},
        "annotations":{"summary":"Prueba de routing tras fix - debe llegar a Telegram"}}]'
# HTTP 200
```

Resultado: notificación recibida en Telegram (confirmado por el operador) y entrega al webhook de Lobster en paralelo.

---

## 5. Archivos tocados

| Archivo | Cambio |
|---|---|
| `sauron:/opt/monitoring/alertmanager/alertmanager.yml` | Routing dual `telegram` + `lobster` |
| `sauron:/opt/monitoring/alertmanager/alertmanager.yml.bak.20260517-005952` | Backup de la versión anterior |
| `wiki/06-Observabilidad/05-Webhook-Alertmanager.md` | Actualizado snippet de routing (estaba con la versión antigua) |
| `wiki/10-Operacion/07-Troubleshooting.md` | Nueva entrada *"Alertas no llegan a Telegram"* |

---

## 6. Lecciones aprendidas

1. **Las subroutes sin matchers son atrapa-todo.** Si añades una y dejas el receiver del padre como default, el default deja de invocarse a menos que metas también el padre como subroute con `continue: true`.
2. **`continue: true` se queda en el nivel actual.** No "rebota" al padre — solo continúa por las hermanas. Útil tenerlo en cuenta cuando se diseñan árboles de routing.
3. **Validar el routing en logs**, no solo en la sintaxis. `amtool config routes test` o simplemente buscar `receiver=X` en `docker logs alertmanager` confirma a quién se entrega cada alerta de verdad.

---

## 7. Enlaces

- Webhook Lobster: [[../wiki/06-Observabilidad/05-Webhook-Alertmanager]]
- Troubleshooting: [[../wiki/10-Operacion/07-Troubleshooting]]
- Doc Alertmanager routing: <https://prometheus.io/docs/alerting/latest/configuration/#route>
