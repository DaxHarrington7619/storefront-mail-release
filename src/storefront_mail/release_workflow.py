from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import InfraiError


@dataclass(frozen=True)
class ExchangeInput:
    host: str
    priority: int


@dataclass(frozen=True)
class ReleaseInput:
    domain: str
    operation_id: str
    exchanges: list[ExchangeInput]


def configure_storefront_mail(request: ReleaseInput, client: Any) -> dict[str, Any]:
    try:
        domain_data = client.get_dns_domain(request.domain)
    except InfraiError as exc:
        if exc.status_code != 404:
            raise
        domain_data = client.add_dns_domain(request.domain, request.operation_id)

    zone_id = str(domain_data["zone_id"])
    ordered = sorted(request.exchanges, key=lambda exchange: exchange.priority)
    for exchange in ordered:
        client.upsert_mx_record(
            zone_id=zone_id,
            name=request.domain,
            content=exchange.host,
            priority=exchange.priority,
            operation_id=request.operation_id,
        )

    sending_domains = client.list_sending_domains()
    configured = any(item.get("domain") == request.domain for item in sending_domains)
    return {
        "state": "released",
        "event": {
            "name": "mail-routing-configured",
            "domain": request.domain,
            "primary_exchange": ordered[0].host,
        },
        "diagnostics": {
            "zone_id": zone_id,
            "mx_records_written": len(ordered),
            "sending_domain_configured": configured,
        },
    }
