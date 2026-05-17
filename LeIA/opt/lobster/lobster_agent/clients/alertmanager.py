from datetime import datetime
from typing import Any, Literal

import httpx
import structlog
from pydantic import BaseModel, Field

QueryParams = dict[str, str | int | float | bool | None]

log = structlog.get_logger()


class AlertmanagerError(RuntimeError):
    pass


class AlertmanagerTimeoutError(AlertmanagerError):
    pass


class AlertmanagerHTTPError(AlertmanagerError):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


class AlertmanagerAlert(BaseModel):
    fingerprint: str
    status: Literal["active", "suppressed", "unprocessed"]
    labels: dict[str, str]
    annotations: dict[str, str]
    starts_at: datetime = Field(alias="startsAt")
    ends_at: datetime | None = Field(alias="endsAt", default=None)
    generator_url: str | None = Field(alias="generatorURL", default=None)
    severity: str | None = None


class AlertmanagerSilence(BaseModel):
    id: str
    matchers: list[dict[str, str | bool]]
    starts_at: datetime = Field(alias="startsAt")
    ends_at: datetime = Field(alias="endsAt")
    created_by: str = Field(alias="createdBy")
    comment: str
    status: dict[str, str]


class AlertmanagerStatus(BaseModel):
    cluster_status: str
    version: str
    uptime: datetime


class AlertmanagerClient:
    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )

    async def list_active_alerts(
        self,
        label_filters: dict[str, str] | None = None,
    ) -> list[AlertmanagerAlert]:
        payload = await self._get_json(
            "/api/v2/alerts",
            params={"active": True, "silenced": False, "inhibited": False},
        )
        alerts = _parse_alerts(payload)
        if label_filters is None:
            return alerts
        return [
            alert
            for alert in alerts
            if all(alert.labels.get(key) == value for key, value in label_filters.items())
        ]

    async def get_alert_by_fingerprint(self, fingerprint: str) -> AlertmanagerAlert | None:
        payload = await self._get_json("/api/v2/alerts")
        for alert in _parse_alerts(payload):
            if alert.fingerprint == fingerprint:
                return alert
        return None

    async def list_silences(self, active_only: bool = True) -> list[AlertmanagerSilence]:
        payload = await self._get_json("/api/v2/silences")
        silences = _parse_silences(payload)
        if not active_only:
            return silences
        return [silence for silence in silences if silence.status.get("state") == "active"]

    async def get_status(self) -> AlertmanagerStatus:
        payload = await self._get_json("/api/v2/status")
        return _parse_status(payload)

    async def close(self) -> None:
        await self._client.aclose()

    async def _get_json(
        self,
        path: str,
        params: QueryParams | None = None,
    ) -> Any:
        try:
            response = await self._client.get(path, params=params)
        except httpx.TimeoutException as exc:
            log.warning("alertmanager.timeout", path=path, params=params)
            raise AlertmanagerTimeoutError(f"Alertmanager request timed out: {path}") from exc

        if not 200 <= response.status_code < 300:
            log.warning(
                "alertmanager.http_error",
                path=path,
                status_code=response.status_code,
                response=response.text,
            )
            raise AlertmanagerHTTPError(
                response.status_code,
                f"Alertmanager returned HTTP {response.status_code}: {response.text}",
            )

        try:
            return response.json()
        except ValueError as exc:
            raise AlertmanagerError("Alertmanager returned invalid JSON") from exc


def _parse_alerts(payload: Any) -> list[AlertmanagerAlert]:
    if not isinstance(payload, list):
        raise AlertmanagerError("Alertmanager alerts response has unexpected format")
    return [_parse_alert(item) for item in payload]


def _parse_alert(item: object) -> AlertmanagerAlert:
    if not isinstance(item, dict):
        raise AlertmanagerError("Alertmanager alert has unexpected format")

    labels = _string_mapping(item.get("labels"))
    annotations = _string_mapping(item.get("annotations"))
    raw_status = item.get("status")
    state = "unprocessed"
    if isinstance(raw_status, dict):
        raw_state = raw_status.get("state")
        if raw_state in {"active", "suppressed", "unprocessed"}:
            state = raw_state

    raw_alert = dict(item)
    raw_alert["status"] = state
    raw_alert["labels"] = labels
    raw_alert["annotations"] = annotations
    raw_alert["severity"] = labels.get("severity")
    try:
        return AlertmanagerAlert.model_validate(raw_alert)
    except ValueError as exc:
        raise AlertmanagerError("Alertmanager alert has unexpected format") from exc


def _parse_silences(payload: Any) -> list[AlertmanagerSilence]:
    if not isinstance(payload, list):
        raise AlertmanagerError("Alertmanager silences response has unexpected format")
    try:
        return [AlertmanagerSilence.model_validate(item) for item in payload]
    except ValueError as exc:
        raise AlertmanagerError("Alertmanager silence has unexpected format") from exc


def _parse_status(payload: Any) -> AlertmanagerStatus:
    if not isinstance(payload, dict):
        raise AlertmanagerError("Alertmanager status response has unexpected format")
    cluster = payload.get("cluster")
    version_info = payload.get("versionInfo")
    uptime = payload.get("uptime")
    if not isinstance(cluster, dict) or not isinstance(version_info, dict):
        raise AlertmanagerError("Alertmanager status response has unexpected format")
    status = cluster.get("status")
    version = version_info.get("version")
    if not isinstance(status, str) or not isinstance(version, str):
        raise AlertmanagerError("Alertmanager status response has unexpected format")
    return AlertmanagerStatus.model_validate(
        {"cluster_status": status, "version": version, "uptime": uptime}
    )


def _string_mapping(value: object | None) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        key: item for key, item in value.items() if isinstance(key, str) and isinstance(item, str)
    }
