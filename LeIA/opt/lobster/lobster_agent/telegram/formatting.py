"""Telegram MarkdownV2 formatting helpers."""

import re

# All MarkdownV2 special chars that need backslash-escaping in plain text
_SPECIAL = re.compile(r"([_*\[\]()~`>#+=|{}.!\\-])")


def esc(text: str) -> str:
    """Escape a plain-text string for MarkdownV2."""
    return _SPECIAL.sub(r"\\\1", str(text))


def bold(text: str) -> str:
    return f"*{esc(text)}*"


def italic(text: str) -> str:
    return f"_{esc(text)}_"


def code(text: str) -> str:
    return f"`{str(text).replace('`', '\\`')}`"


def pre(text: str, lang: str = "") -> str:
    safe = str(text).replace("`", "\\`")
    return f"```{lang}\n{safe}\n```"


def md_to_mdv2(text: str) -> str:
    """
    Best-effort conversion of LLM markdown output to Telegram MarkdownV2.

    Processes fenced code blocks, inline code, **bold**, *italic*, _italic_
    in priority order, then escapes all remaining plain-text special chars.
    """
    _CODE_BLOCK = re.compile(r"```(\w*)\n?(.*?)```", re.DOTALL)
    _INLINE_CODE = re.compile(r"`([^`\n]+)`")
    _BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
    _ITALIC_STAR = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", re.DOTALL)
    _ITALIC_UNDER = re.compile(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", re.DOTALL)

    patterns: list[tuple[re.Pattern[str], str]] = [
        (_CODE_BLOCK, "code_block"),
        (_INLINE_CODE, "inline_code"),
        (_BOLD, "bold"),
        (_ITALIC_STAR, "italic"),
        (_ITALIC_UNDER, "italic"),
    ]

    result: list[str] = []
    remaining = text

    while remaining:
        earliest_match: re.Match[str] | None = None
        earliest_pos = len(remaining)
        earliest_type: str | None = None

        for pattern, kind in patterns:
            m = pattern.search(remaining)
            if m and m.start() < earliest_pos:
                earliest_match = m
                earliest_pos = m.start()
                earliest_type = kind

        if earliest_match is None:
            result.append(esc(remaining))
            break

        if earliest_pos > 0:
            result.append(esc(remaining[:earliest_pos]))

        if earliest_type == "code_block":
            lang = earliest_match.group(1)
            content = earliest_match.group(2).replace("`", "\\`")
            result.append(f"```{lang}\n{content}\n```")
        elif earliest_type == "inline_code":
            content = earliest_match.group(1).replace("`", "\\`")
            result.append(f"`{content}`")
        elif earliest_type == "bold":
            result.append(f"*{esc(earliest_match.group(1))}*")
        elif earliest_type == "italic":
            result.append(f"_{esc(earliest_match.group(1))}_")

        remaining = remaining[earliest_pos + len(earliest_match.group(0)) :]

    return "".join(result)
