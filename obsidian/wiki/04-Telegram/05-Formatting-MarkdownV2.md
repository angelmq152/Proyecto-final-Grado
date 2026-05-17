---
title: Telegram — MarkdownV2 formatting
tags: [telegram, markdownv2, formatting, escape]
---

# 🎨 Telegram · MarkdownV2 formatting

> [!abstract] MarkdownV2 no perdona
> Archivo: `lobster_agent/telegram/formatting.py`. Telegram MarkdownV2 es **rigurosísimo**: 18 caracteres especiales hay que escaparlos siempre, los pares `*` `_` `~` deben balancearse, `**` no existe. Esta nota documenta cómo Lobster maneja esto sin volverse loco.

## 🔣 Caracteres especiales (18)

```python
_SPECIAL = re.compile(r'([_*\[\]()~`>#+=|{}.!\\-])')
```

Cada uno se escapa con `\` cuando aparece en texto plano.

## 🛠️ Helpers básicos

```python
def esc(text)  -> str:    # escapa todo el texto plano
def bold(text) -> str:    # *texto*  (escapando dentro)
def italic(text) -> str:  # _texto_
def code(text) -> str:    # `texto`  (escape solo de backticks)
def pre(text, lang='') -> str:    # ```lang\ntexto\n```
```

## 🔄 `md_to_mdv2(text)` — conversión inteligente

> [!info] Para respuestas LLM
> Los LLMs (Qwen3) generan Markdown estándar: `**bold**`, `*italic*`, `_italic_`, código triple-backtick, etc. Trasladarlo directo a Telegram falla. `md_to_mdv2` hace una pasada de single token con prioridades:

```python
patterns = [
    (_CODE_BLOCK, 'code_block'),       # ```...```
    (_INLINE_CODE, 'inline_code'),     # `...`
    (_BOLD, 'bold'),                   # **...**
    (_ITALIC_STAR, 'italic'),          # *...* (sin colisionar con bold)
    (_ITALIC_UNDER, 'italic'),         # _..._
]
```

Algoritmo (greedy left-to-right):

1. Buscar la primera ocurrencia de cualquier patrón.
2. Lo de antes → `esc(...)`.
3. La ocurrencia → conversión correcta a MDV2.
4. Lo de después → siguiente iteración.

> [!tip] Por qué left-to-right
> Las primeras versiones aplicaban patrones secuencialmente (todos los `_CODE_BLOCK`, luego todos los `_BOLD`, ...) y eso causaba que `**bold dentro de bloque de código**` se interpretara dos veces. El one-pass left-to-right resuelve el problema.

## 📋 Uso típico desde handlers

```python
# Mensaje fijo (no viene del LLM):
await message.answer(
    f"{bold('Modo:')} {esc(state.mode.value)}",
    parse_mode=ParseMode.MARKDOWN_V2,
)

# Respuesta del LLM:
reply = md_to_mdv2(result.data or "Sin respuesta.")
await placeholder.edit_text(reply, parse_mode=ParseMode.MARKDOWN_V2)
```

## 💣 Tipos de errores frecuentes

> [!danger] Errores típicos que MDV2 lanza
> - `can't parse entities: Character '.' is reserved` → faltó escapar un punto.
> - `Can't find end of the entity starting at byte offset N` → `*` o `_` sin cerrar.
> - `Unsupported start tag` → enviaste HTML por error con MARKDOWN_V2.
>
> Solución: pasar TODO por `esc()` o `md_to_mdv2()` antes de mandar.

## 🧪 Test

`tests/test_telegram_messages.py` y `tests/test_telegram_handlers.py` verifican que:
- Los `format_approval_request` se rendericen sin error.
- `md_to_mdv2` maneja bloques anidados sin romper.
