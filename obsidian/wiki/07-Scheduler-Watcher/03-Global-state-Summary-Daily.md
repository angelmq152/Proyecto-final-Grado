---
title: Global state, hourly summary, daily summary
tags: [scheduler, global-state, summary, daily-summary]
---

# 🌐📅 Global state · Hourly · Daily summary

> [!abstract] Tres ritmos distintos
> Tres jobs que cubren cadencias diferentes: **30 min** (snapshot global), **1 h** (resumen breve), **24 h** (informe completo al vault Obsidian).

## 🌐 `global_state` — cada 30 min

```python
_GLOBAL_STATE_PROMPT = (
    "Resume el estado global de SaaSphere: uso de CPU, memoria y disco por nodo, "
    "tenants activos e inactivos, alertas activas. Detecta tendencias preocupantes "
    "y registra un snapshot del estado."
)
```

- Modelo: `qwen3:8b`, think ✅.
- Notify: ❌ (silencioso).
- Tools: meta + prometheus + alertmanager + k8s_basic + memory.
- Timeout: 600 s.

> [!tip] Por qué no notifica
> El operador ya tiene `/status` y Grafana. Este job alimenta `decisions` para que ANALYZE y DAILY puedan consultar el contexto histórico (`search_decisions(case_use="global_state")`).

## 📊 `hourly_summary` — cada hora (`0 * * * *`)

```python
_HOURLY_SUMMARY_PROMPT = (
    "Genera un resumen operativo de la última hora: decisiones tomadas, "
    "alertas recibidas, acciones ejecutadas, errores detectados. Sé breve."
)
```

- Modelo: `qwen3:8b`, think ❌.
- Notify: ✅ (header `📊 Lobster [summary]`).
- Tools: meta + memory + list_active_alerts.
- Timeout: 600 s.

> [!example] Output típico en Telegram
> ```
> 📊 Lobster [summary]
>
> Última hora:
> - 2 decisiones tomadas (1 health_loop_analyze, 1 alert_reactive)
> - 0 alertas activas
> - 1 restart_pod ejecutado en tenant-acme
> - Sin errores
> ```

## 📅 `daily_summary` — diario a las 08:00

```python
_DAILY_SUMMARY_PROMPT = """\
Genera el informe operativo diario de SaaSphere. Debes llamar a las herramientas \
disponibles y usar sus resultados reales. Nunca escribas "???" ni texto placeholder. \
Si una herramienta falla, anota el error y continúa con la siguiente.

Llama a estas herramientas:
- get_node_health
- list_namespaces
- list_pods
- list_deployments
- list_ingresses
- list_active_alerts
- get_recent_errors (hours=24)
- search_decisions (limit=20)
- list_recent_events

Con los datos obtenidos, genera un informe en Markdown con estas secciones:

# Resumen diario
## 🖥️ Nodos
## 🏢 Tenants y pods
## ⚠️ Pods problemáticos
## 🚨 Alertas activas
## 🪵 Errores en logs (últimas 24 h)
## 📋 Decisiones del día
## ✅ Conclusión
"""
```

- Modelo: `qwen3:32b` (largo y de calidad).
- Think: ❌ (think rompe los tool calls en este caso de uso).
- Notify: ✅ (header `📅 Lobster [daily_summary]`).
- Save Obsidian: ✅ → `obsidian/YYYY-MM/YYYY-MM-DD_daily_summary.md`.
- Timeout: **1800 s (30 min)**. Por qué tan largo:

> [!warning] Fix de timeout (commit fcedb6f)
> Comentario en el código:
> *"1800s = 30 min: qwen3:32b sin think hace ~10 tool calls y cada uno puede tardar varios minutos. 1200s antes cancelaba el job a mitad de generación y se perdía la notificación a Telegram + Obsidian."*

## 📓 Guardado en Obsidian

```python
def _save_obsidian_note(base_path, case_use, content):
    now = datetime.now()
    month_dir = Path(base_path) / now.strftime("%Y-%m")
    month_dir.mkdir(parents=True, exist_ok=True)
    note_path = month_dir / f"{now.strftime('%Y-%m-%d')}_{case_use.value}.md"
    frontmatter = f"""---
date: {now.strftime('%Y-%m-%d')}
time: {now.strftime('%H:%M')}
type: {case_use.value}
tags: [lobster, {case_use.value}]
---

# {now.strftime('%Y-%m-%d')} — {case_use.value.replace('_', ' ').title()}

*Generado automáticamente por Lobster a las {now.strftime('%H:%M')}*
"""
    mode = "a" if note_path.exists() else "w"
    with note_path.open(mode, encoding="utf-8") as f:
        if mode == "w":
            f.write(frontmatter)
        else:
            f.write(f"\n---\n\n*Actualización a las {now.strftime('%H:%M')}*\n\n")
        f.write(content)
        f.write("\n")
```

> [!tip] Append-only por día
> Si el job se dispara dos veces el mismo día (poco probable pero posible con `/admin/trigger`), añade un separador `---` y la actualización al pie. No sobreescribe.

> [!warning] Fallo de I/O no falla el job
> Si `mkdir` o `write` lanza `OSError`, se incrementa `lobster_errors_total{component="scheduler", severity="warning"}` y se loguea, pero el job sigue como exitoso (ya emitió Telegram y guardó la `Decision`).

## 📁 Resultado en el vault

```text
obsidian/
├── 2026-05/
│   ├── 2026-05-14_daily_summary.md
│   ├── 2026-05-15_daily_summary.md
│   └── 2026-05-16_daily_summary.md
```

Estos archivos **existen ya** en el vault. La wiki en `obsidian/wiki/` que estás leyendo **no los toca**.
