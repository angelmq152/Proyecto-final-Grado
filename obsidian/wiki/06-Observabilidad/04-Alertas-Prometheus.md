---
title: Observabilidad — Alertas Prometheus
tags: [observabilidad, alertas, prometheus, fase7]
---

# 🚨 Alertas · Prometheus

> [!abstract] 5 alertas vigilan al vigilante
> Archivo: `deploy/prometheus/lobster.rules.yaml`. Reglas que Prometheus carga para vigilar al propio Lobster. Si alguna dispara, Alertmanager las route como cualquier otra alerta.

## 📋 Reglas

### `LobsterSinActividad` (critical)

```yaml
- alert: LobsterSinActividad
  expr: (time() - max(lobster_last_cycle_timestamp)) > 900
  for: 2m
  labels: { severity: critical, team: ops }
  annotations:
    summary: "Lobster sin actividad durante {{ $value | humanizeDuration }}"
    description: >
      El campo lobster_last_cycle_timestamp no se ha actualizado en más de 15 minutos.
    runbook: "Revisar `systemctl status lobster` en LeIA y los logs en Grafana/Loki."
```

> [!danger] Crítica porque el proceso podría estar muerto
> Si el scheduler corre cada 5 min, no actualizar el timestamp en 15 min es indicación de proceso bloqueado/caído.

### `LobsterTasaErroresAlta` (warning)

```yaml
- alert: LobsterTasaErroresAlta
  expr: sum(rate(lobster_errors_total{severity="error"}[5m])) > 0.05
  for: 3m
```

> [!info] 0.05 err/s = 3 errores/minuto sostenido
> Indica un bug nuevo o un problema sistémico (LLM dando respuestas inválidas, K8s caído, …).

### `LobsterLatenciaLLMAlta` (warning)

```yaml
- alert: LobsterLatenciaLLMAlta
  expr: |
    histogram_quantile(0.95,
      sum(rate(lobster_llm_latency_seconds_bucket{model=~"qwen3:8b"}[10m])) by (le, model)
    ) > 300
  for: 5m
```

> [!warning] p95 de 8b > 5 min
> Eso debería ser raro. Suele indicar GPU saturada o swap. La regla solo mira 8b porque 32b sí puede tardar de forma legítima.

### `LobsterDecisionesFallidas` (warning)

```yaml
- alert: LobsterDecisionesFallidas
  expr: |
    sum(rate(lobster_decisions_total{outcome="failed"}[10m]))
    / sum(rate(lobster_decisions_total[10m]))
    > 0.30
```

> [!info] 30 % de decisiones fallidas
> Algo se rompió en el camino LLM (tool error, prompt inválido, modelo retornando JSON malformado). Revisar `lobster decisions list --limit 20`.

### `LobsterRestart` (info)

```yaml
- alert: LobsterRestart
  expr: lobster_uptime_seconds < 120
  for: 0m
```

> [!tip] Severidad info
> No es un problema en sí — un reinicio manual lo dispara. Útil para correlación: "el agente se reinició a las 14:32, ¿es eso lo que rompió X?".

## 🚏 Cómo cargarlas en Sauron

> [!example] En `prometheus.yml`
> ```yaml
> rule_files:
>   - "/etc/prometheus/rules/lobster.rules.yaml"
> ```
> Luego `cp deploy/prometheus/lobster.rules.yaml /etc/prometheus/rules/` en Sauron y `systemctl reload prometheus`.

## 🔁 Bucle reactivo

> [!danger] Si las alertas se rutean al webhook de Lobster…
> El propio agente recibirá el webhook y razonará: *"LobsterSinActividad disparada — pero soy yo el que la recibe, ¿estoy vivo?"*. Aunque conceptualmente paradójico, en práctica funciona: si el webhook llega, Lobster responde. Si no responde, Telegram tampoco recibe nada y el operador investiga manualmente.

→ Detalles operativos en `docs/fase_7_alertas_prometheus.md`.
