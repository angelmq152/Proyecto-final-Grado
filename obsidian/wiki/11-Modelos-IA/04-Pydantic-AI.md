---
title: Pydantic-AI
tags: [llm, pydantic-ai, framework, tools]
---

# 🦾 Pydantic-AI

> [!abstract] El framework agéntico
> Pydantic-AI es una librería para construir agentes LLM tipados. Minimalista, async-nativa, sin dependencias absurdas. Lobster la usa exclusivamente.

## 📦 Instalación

```toml
dependencies = [
    "pydantic-ai-slim[openai]>=1.93.0",
]
```

> [!info] Slim + extras
> `pydantic-ai-slim` es el core sin proveedores. `[openai]` añade soporte para el protocolo OpenAI (que Ollama también habla).

## 🧬 Componentes que Lobster usa

| Pieza | De dónde | Uso |
|---|---|---|
| `Agent` | `pydantic_ai` | el "agente" con sus tools y deps |
| `Tool` | `pydantic_ai` | wrapper de función registrada |
| `RunContext[T]` | `pydantic_ai` | inyección de deps |
| `OpenAIChatModel` | `pydantic_ai.models.openai` | binding a Ollama OpenAI-compat |
| `OpenAIProvider` | `pydantic_ai.providers.openai` | configuración base_url/api_key |
| `ModelSettings` | `pydantic_ai.settings` | timeouts, extra_body |
| `ModelMessage`, `ModelRequest`, `ModelResponse`, `TextPart`, `UserPromptPart`, `ToolCallPart` | `pydantic_ai.messages` | construcción de historial |

## 🚀 Construcción típica

```python
agent = Agent(
    model,                            # OpenAIChatModel
    output_type=str,                  # respuesta final como string
    deps_type=AgentDeps,              # dataclass con dependencias
    tools=[
        reading.list_pods,
        reading.get_pod,
        restart_pod,
        ...
    ],
    tool_retries=1,                   # reintenta tool calls 1 vez
    output_retries=1,                 # reintenta parsing 1 vez
)
```

## 🔄 Ejecución

```python
result = await agent.run(
    user_input,
    instructions=system_prompt,
    deps=deps,
    message_history=history,
)
output = str(result.output)
usage = result.usage()                # tokens
messages = result.all_messages()      # ModelMessage[]
```

## 💉 Inyección de dependencias

> [!tip] `RunContext[AgentDeps]`
> Las tools tienen firma:
> ```python
> async def my_tool(ctx: RunContext[AgentDeps], arg1: str) -> ResultModel:
>     await ctx.deps.k8s.list_pods(...)
> ```
> Pydantic-AI ve `RunContext` y le inyecta automáticamente las deps registradas. Sin globals, sin singletons.

## 🛠️ Tools tipadas

```python
async def list_pods(
    ctx: RunContext[AgentDeps],
    namespace: str | None = None,                # opcional
) -> list[PodSummary] | ToolError:
    """List Kubernetes pods..."""
    ...
```

> [!info] Tres cosas que el LLM ve
> - **Nombre** de la función (`list_pods`).
> - **Docstring** (descripción que el modelo lee).
> - **Schema JSON** generado a partir de los tipos Pydantic.

## 🔁 Reintentos

```python
tools=[...],
tool_retries=1,        # si la tool falla, reintenta 1 vez
output_retries=1,      # si parsing del output_type falla, reintenta 1 vez
```

> [!warning] No es retry de Ollama
> Estos retries son lógicos. Si Ollama está caído, fallarán igual. Para retries de Ollama → `httpx` no los hace por defecto; Lobster no implementa retries del cliente HTTP.

## 📜 Historia de mensajes

```python
def _build_message_history(turns: list[tuple[str, str]]) -> list[ModelMessage]:
    messages: list[ModelMessage] = []
    for role, content in turns:
        if role == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        else:
            messages.append(ModelResponse(parts=[TextPart(content=content)]))
    return messages
```

> [!info] Roles user / assistant
> Pydantic-AI usa `ModelRequest` para mensajes del usuario y `ModelResponse` para los del modelo. La conversación se monta como lista alternada.

## 📊 `usage()` para tokens

```python
usage = result.usage()
tokens_input  = usage.input_tokens  or 0
tokens_output = usage.output_tokens or 0
```

Persistidos en `Decision.tokens_input` y `Decision.tokens_output`, y emitidos como `lobster_llm_tokens_total{direction}`.

## 🧪 Tests con Pydantic-AI

```python
# Mock del modelo:
async def fake_model(model_name, think):
    return FakeModel(...)

agent = LobsterAgent(settings, deps, model_factory=fake_model)
```

`model_factory` es un override para tests — permite inyectar un modelo fake sin tocar la red.

→ Continúa en [[05-Tool-calling]].
