from datetime import datetime
from typing import Any

import httpx
import structlog

QueryParams = dict[str, str | int | float | bool | None]

log = structlog.get_logger()


class PrometheusError(RuntimeError):
    pass


class PrometheusQueryError(PrometheusError):
    pass


class PrometheusTimeoutError(PrometheusQueryError):
    pass


class PrometheusHTTPError(PrometheusQueryError):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


class PrometheusClient:
    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )

    async def instant_query(self, query: str) -> list[dict[str, object]]:
        payload = await self._get_json("/api/v1/query", params={"query": query})
        return _extract_result(payload)

    async def range_query(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str,
    ) -> list[dict[str, object]]:
        payload = await self._get_json(
            "/api/v1/query_range",
            params={
                "query": query,
                "start": start.timestamp(),
                "end": end.timestamp(),
                "step": step,
            },
        )
        return _extract_result(payload)

    async def list_labels(self) -> list[str]:
        payload = await self._get_json("/api/v1/labels")
        data = _extract_data(payload)
        if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
            raise PrometheusQueryError("Prometheus labels response has unexpected format")
        return data

    async def list_series(self, match: str) -> list[dict[str, object]]:
        payload = await self._get_json("/api/v1/series", params={"match[]": match})
        data = _extract_data(payload)
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise PrometheusQueryError("Prometheus series response has unexpected format")
        return [dict(item) for item in data]

    async def close(self) -> None:
        await self._client.aclose()

    async def _get_json(
        self,
        path: str,
        params: QueryParams | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self._client.get(path, params=params)
        except httpx.TimeoutException as exc:
            log.warning("prometheus.timeout", path=path, params=params)
            raise PrometheusTimeoutError(f"Prometheus request timed out: {path}") from exc

        if not 200 <= response.status_code < 300:
            log.warning(
                "prometheus.http_error",
                path=path,
                status_code=response.status_code,
                response=response.text,
            )
            raise PrometheusHTTPError(
                response.status_code,
                f"Prometheus returned HTTP {response.status_code}: {response.text}",
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise PrometheusQueryError("Prometheus returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise PrometheusQueryError("Prometheus response has unexpected format")
        if payload.get("status") == "error":
            message = payload.get("error") or payload.get("errorType") or "unknown error"
            raise PrometheusQueryError(f"Prometheus query failed: {message}")
        return payload


def _extract_data(payload: dict[str, Any]) -> object:
    if "data" not in payload:
        raise PrometheusQueryError("Prometheus response missing data")
    return payload["data"]


def _extract_result(payload: dict[str, Any]) -> list[dict[str, object]]:
    data = _extract_data(payload)
    if not isinstance(data, dict):
        raise PrometheusQueryError("Prometheus data response has unexpected format")

    result = data.get("result")
    if not isinstance(result, list) or not all(isinstance(item, dict) for item in result):
        raise PrometheusQueryError("Prometheus result response has unexpected format")

    return [dict(item) for item in result]
