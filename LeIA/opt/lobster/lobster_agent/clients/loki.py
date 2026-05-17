from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

QueryParams = dict[str, str | int | float | bool | None]


class LokiQueryError(RuntimeError):
    pass


@dataclass(frozen=True)
class LogEntry:
    timestamp: datetime
    labels: dict[str, str]
    line: str


class LokiClient:
    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )

    async def query_range(
        self,
        logql: str,
        start: datetime,
        end: datetime,
        limit: int = 100,
    ) -> list[LogEntry]:
        payload = await self._get_json(
            "/loki/api/v1/query_range",
            params={
                "query": logql,
                "start": _to_nanoseconds(start),
                "end": _to_nanoseconds(end),
                "limit": limit,
            },
        )
        data = _extract_data(payload)
        if not isinstance(data, dict):
            raise LokiQueryError("Loki data response has unexpected format")
        result = data.get("result")
        if not isinstance(result, list):
            raise LokiQueryError("Loki result response has unexpected format")

        entries: list[LogEntry] = []
        for stream in result:
            entries.extend(_parse_stream(stream))
        return entries

    async def list_labels(self) -> list[str]:
        payload = await self._get_json("/loki/api/v1/labels")
        data = _extract_data(payload)
        if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
            raise LokiQueryError("Loki labels response has unexpected format")
        return data

    async def list_series(self, match: str) -> list[dict[str, object]]:
        payload = await self._get_json("/loki/api/v1/series", params={"match[]": match})
        data = _extract_data(payload)
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise LokiQueryError("Loki series response has unexpected format")
        return [dict(item) for item in data]

    async def close(self) -> None:
        await self._client.aclose()

    async def _get_json(
        self,
        path: str,
        params: QueryParams | None = None,
    ) -> dict[str, Any]:
        response = await self._client.get(path, params=params)
        if not 200 <= response.status_code < 300:
            raise LokiQueryError(f"Loki returned HTTP {response.status_code}: {response.text}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise LokiQueryError("Loki returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise LokiQueryError("Loki response has unexpected format")
        if payload.get("status") == "error":
            message = payload.get("error") or payload.get("errorType") or "unknown error"
            raise LokiQueryError(f"Loki query failed: {message}")
        return payload


def _extract_data(payload: dict[str, Any]) -> object:
    if "data" not in payload:
        raise LokiQueryError("Loki response missing data")
    return payload["data"]


def _parse_stream(stream: object) -> list[LogEntry]:
    if not isinstance(stream, dict):
        raise LokiQueryError("Loki stream response has unexpected format")

    labels = stream.get("stream")
    values = stream.get("values")
    if not isinstance(labels, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in labels.items()
    ):
        raise LokiQueryError("Loki stream labels have unexpected format")
    if not isinstance(values, list):
        raise LokiQueryError("Loki stream values have unexpected format")

    entries: list[LogEntry] = []
    for value in values:
        entries.append(_parse_value(labels, value))
    return entries


def _parse_value(labels: dict[str, str], value: object) -> LogEntry:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not isinstance(value[0], str)
        or not isinstance(value[1], str)
    ):
        raise LokiQueryError("Loki log value has unexpected format")

    return LogEntry(
        timestamp=_from_nanoseconds(value[0]),
        labels=dict(labels),
        line=value[1],
    )


def _to_nanoseconds(value: datetime) -> int:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return int(aware.timestamp() * 1_000_000_000)


def _from_nanoseconds(value: str) -> datetime:
    try:
        nanoseconds = int(value)
    except ValueError as exc:
        raise LokiQueryError("Loki timestamp is not an integer nanosecond value") from exc

    seconds, remainder_ns = divmod(nanoseconds, 1_000_000_000)
    return datetime.fromtimestamp(seconds + remainder_ns / 1_000_000_000, UTC)
