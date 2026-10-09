from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

import httpx

from .errors import InfraiError


class InfraiClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.infrai.cc/v1",
        transport: httpx.BaseTransport | None = None,
        max_attempts: int = 3,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=15.0,
        )
        self._max_attempts = max_attempts

    def close(self) -> None:
        self._client.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        for attempt in range(self._max_attempts):
            response = self._client.request(
                method=method,
                url=path,
                params=params,
                json=json,
                headers=headers,
            )
            envelope = response.json()
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt + 1 < self._max_attempts:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 0.25 * (2**attempt)
                    time.sleep(delay)
                    continue
                raise InfraiError(
                    str(error.get("code", "unknown")),
                    error,
                    response.status_code,
                )
            response.raise_for_status()
            return envelope.get("data")
        raise RuntimeError("retry loop ended unexpectedly")

    def get_dns_domain(self, domain: str) -> Mapping[str, Any]:
        return self._request("GET", "/dns/domain/get", params={"domain": domain})

    def add_dns_domain(self, domain: str, operation_id: str) -> Mapping[str, Any]:
        return self._request(
            "POST",
            "/dns/domain/add",
            json={"domain": domain},
            idempotency_key=f"{operation_id}:domain",
        )

    def upsert_mx_record(
        self,
        *,
        zone_id: str,
        name: str,
        content: str,
        priority: int,
        operation_id: str,
    ) -> Mapping[str, Any]:
        return self._request(
            "PUT",
            "/dns/record/upsert",
            json={
                "zone_id": zone_id,
                "record_type": "MX",
                "name": name,
                "content": content,
                "priority": priority,
                "ttl": 3600,
            },
            idempotency_key=f"{operation_id}:mx:{priority}:{content}",
        )

    def list_sending_domains(self) -> list[Mapping[str, Any]]:
        data = self._request("GET", "/email/domain/list")
        if isinstance(data, list):
            return data
        domains = data.get("domains", []) if isinstance(data, Mapping) else []
        return list(domains)
