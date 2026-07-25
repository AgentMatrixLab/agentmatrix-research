"""Thin client for the internal Quant API v2 service.

This module is intentionally small and side-effect free: it does not cache,
write files, or trigger admin pull jobs. It only proxies read requests through
the backend so the frontend never sees the API token.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://115.159.73.134:8765"


class QuantApiError(RuntimeError):
    """Raised when the Quant API returns an error or cannot be reached."""

    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


@dataclass(frozen=True, slots=True)
class QuantApiConfig:
    base_url: str = DEFAULT_BASE_URL
    token: str | None = None
    timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> "QuantApiConfig":
        return cls(
            base_url=(
                os.getenv("FACTOR_LAB_QUANT_API_BASE_URL")
                or os.getenv("QUANT_API_BASE_URL")
                or DEFAULT_BASE_URL
            ).rstrip("/"),
            token=os.getenv("FACTOR_LAB_QUANT_API_TOKEN") or os.getenv("QUANT_API_TOKEN"),
            timeout_seconds=int(os.getenv("FACTOR_LAB_QUANT_API_TIMEOUT", "30")),
        )

    @property
    def token_configured(self) -> bool:
        return bool(self.token)


class QuantApiClient:
    """Read-only HTTP client for Quant API v2."""

    def __init__(self, config: QuantApiConfig | None = None) -> None:
        self.config = config or QuantApiConfig.from_env()

    def status(self, *, check_remote: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "base_url": self.config.base_url,
            "token_configured": self.config.token_configured,
        }
        if check_remote:
            payload["remote_health"] = self.request_json("/health", require_token=False)
            if self.config.token_configured:
                payload["whoami"] = self.request_json("/whoami")
        return payload

    def sources(self) -> dict[str, Any]:
        return self.request_json("/sources")

    def ch_tables(self) -> dict[str, Any]:
        return self.request_json("/ch")

    def factor_monthly(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request_json("/factor_monthly", params=params)

    def factor_monthly_factors(self) -> dict[str, Any]:
        return self.request_json("/factor_monthly/factors")

    def factor_monthly_dates(self) -> dict[str, Any]:
        return self.request_json("/factor_monthly/dates")

    def factor_monthly_stats(self) -> dict[str, Any]:
        return self.request_json("/factor_monthly/stats")

    def factor_monthly_latest(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request_json("/factor_monthly/latest", params=params)

    def factor_ic(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request_json("/ch/factor_ic", params=params)

    def kline_1d(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request_json("/ch/ods_kline_1d", params=params)

    def request_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        require_token: bool = True,
    ) -> dict[str, Any]:
        if require_token and not self.config.token:
            raise QuantApiError("Quant API token is not configured", status_code=401)

        url = f"{self.config.base_url}{path}"
        clean_params = _clean_params(params)
        if clean_params:
            url = f"{url}?{urlencode(clean_params, doseq=True)}"

        headers = {"Accept": "application/json"}
        if require_token and self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"

        req = Request(url, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=self.config.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            raise _http_error(exc) from exc
        except URLError as exc:
            raise QuantApiError(f"Quant API is unreachable: {exc.reason}") from exc

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise QuantApiError("Quant API returned non-JSON response") from exc

        if not isinstance(parsed, dict):
            raise QuantApiError("Quant API returned an unexpected JSON shape", payload=parsed)
        return parsed


def _clean_params(params: dict[str, Any] | None) -> dict[str, Any]:
    if not params:
        return {}
    return {key: value for key, value in params.items() if value not in (None, "")}


def _http_error(exc: HTTPError) -> QuantApiError:
    raw = exc.read().decode("utf-8", errors="replace")
    payload: Any = raw
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        pass

    message = f"Quant API request failed with HTTP {exc.code}"
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("error")
        if detail:
            message = f"{message}: {detail}"
    return QuantApiError(message, status_code=exc.code, payload=payload)
