import asyncio
import json
import time
from collections.abc import MutableMapping
from typing import Any

import httpx
import structlog

from lobster_agent.observability.metrics import lobster_loki_queue_size

_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)
_loki_url: str = ""
_flush_interval: int = 5
_batch_size: int = 100
_flush_task: asyncio.Task[None] | None = None


def setup_logging(
    log_level: str,
    loki_url: str,
    flush_interval: int = 5,
    batch_size: int = 100,
) -> None:
    global _loki_url, _flush_interval, _batch_size
    _loki_url = loki_url
    _flush_interval = flush_interval
    _batch_size = batch_size

    import logging

    level = getattr(logging, log_level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _loki_enqueue_processor,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _loki_enqueue_processor(
    logger: Any, method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Captura el evento (como dict) antes de que JSONRenderer lo serialice."""
    try:
        _queue.put_nowait(dict(event_dict))
    except asyncio.QueueFull:
        pass
    return event_dict


async def _flush_to_loki(entries: list[dict[str, Any]]) -> None:
    if not entries or not _loki_url:
        return

    now_ns = str(int(time.time() * 1_000_000_000))
    values = [[now_ns, json.dumps(e)] for e in entries]
    payload = {
        "streams": [
            {
                "stream": {"service": "lobster", "host": "leia"},
                "values": values,
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(_loki_url, json=payload)
    except Exception:
        pass  # Journald es el fallback; si Loki no responde, silencio


async def _flush_loop() -> None:
    while True:
        await asyncio.sleep(_flush_interval)
        lobster_loki_queue_size.set(_queue.qsize())
        entries: list[dict[str, Any]] = []
        for _ in range(_batch_size):
            try:
                entries.append(_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        await _flush_to_loki(entries)


async def start_loki_flusher() -> None:
    global _flush_task
    _flush_task = asyncio.create_task(_flush_loop())


async def stop_loki_flusher() -> None:
    if _flush_task:
        _flush_task.cancel()
        try:
            await _flush_task
        except asyncio.CancelledError:
            pass
    # Flush de lo que quede en la cola antes de cerrar
    remaining: list[dict[str, Any]] = []
    while not _queue.empty():
        try:
            remaining.append(_queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    await _flush_to_loki(remaining)
