---
title: Ollama y GPU
tags: [infraestructura, ollama, gpu, qwen3, inferencia]
---

# 🚀 Ollama y GPU en LeIA

> [!abstract] El inferenciador local
> Ollama es el servidor de inferencia LLM. Corre en LeIA, escucha en `:11434`, expone API "OpenAI-compatible" en `/v1`. Lobster lo usa exclusivamente para los modelos Qwen3.

## ⚙️ Instalación típica

```bash
# En LeIA, como usuario lobster:
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:8b
ollama pull qwen3:32b
systemctl enable --now ollama
```

## 🔌 Endpoint OpenAI-compatible

```python
class OllamaConfig:
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"      # Ollama acepta cualquier valor
    timeout_seconds: float = 180.0
```

Lobster apunta a `http://localhost:11434/v1/chat/completions` vía `OpenAIChatModel` de Pydantic-AI.

## 🎮 GPU

> [!info] Una GPU consumer
> El homelab tiene una sola GPU con ~24-26 GB de VRAM. Esto:
> - **Cabe** `qwen3:32b` (justo).
> - **No cabe** `qwen3:8b` + `qwen3:32b` simultáneamente.
> - **Cambiar** entre modelos exige descargar uno y cargar otro → ~8 s perdidos.

> [!warning] La razón de la cola Fase 9
> Sin serialización, dos jobs paralelos con modelos diferentes hacen thrashing constante. Con la cola FIFO, los modelos se reusan eficientemente.

## 📋 Estado real

```bash
# Ver qué modelo está cargado:
curl -s http://localhost:11434/api/ps | jq
# {"models": [{"name": "qwen3:8b", "size_vram": 9521664000, ...}]}

# Forzar carga:
curl -X POST http://localhost:11434/api/generate -d '{"model":"qwen3:8b","prompt":""}'

# Descargar (free VRAM):
curl -X POST http://localhost:11434/api/generate -d '{"model":"qwen3:8b","keep_alive":0}'
```

## ⚙️ Variables Ollama útiles

> [!example] `/etc/systemd/system/ollama.service.d/override.conf`
> ```ini
> [Service]
> Environment="OLLAMA_HOST=0.0.0.0"
> Environment="OLLAMA_KEEP_ALIVE=5m"        # auto-descarga tras 5 min sin uso
> Environment="OLLAMA_NUM_PARALLEL=1"        # 1 request a la vez por modelo
> Environment="OLLAMA_MAX_LOADED_MODELS=1"   # solo un modelo a la vez
> ```

## 🧠 Think mode de Qwen3

> [!info] `/think` extension
> Qwen3 soporta razonamiento explícito. Pydantic-AI lo activa pasando `extra_body={"think": True}` en `ModelSettings`. Ollama lo propaga al modelo.

→ Detalle en [[../11-Modelos-IA/03-Think-mode]].

## 🚦 Timeouts dinámicos por modelo

```python
# orchestrator._build_model
if think:
    timeout = httpx.Timeout(None, connect=30.0)      # sin read timeout
elif "32b" in model_name:
    timeout = max(settings.ollama.timeout_seconds, 900.0)
else:
    timeout = settings.ollama.timeout_seconds         # default 180 s
```

> [!warning] qwen3:32b sin think necesita 900 s
> Memory: el daily_summary llama ~10 tools, cada una puede tomar varios segundos. La latencia acumulada hace que 180 s sea insuficiente. 900 s = 15 min cubre incluso peor escenario.

## 🔍 Verificar conectividad desde Lobster

```bash
# Smoke test
uv run lobster ask "qué hora es?" --no-tools
# 2026-05-16T17:32:00+00:00
```

Si esto falla, Ollama no está corriendo o el modelo no está pulled.

→ Ver [[../11-Modelos-IA/00-MOC-Modelos|MOC Modelos]] para detalle del uso.
