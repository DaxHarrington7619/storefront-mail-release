from typing import Any

from storefront_mail.release_workflow import ExchangeInput, ReleaseInput, configure_storefront_mail


class RecordingClient:
    def __init__(self) -> None:
        self.writes: list[dict[str, Any]] = []

    def get_dns_domain(self, domain: str) -> dict[str, str]:
        assert domain == "mail.river-market.test"
        return {"zone_id": "zone_storefront_42"}

    def upsert_mx_record(self, **record: Any) -> dict[str, bool]:
        self.writes.append(record)
        return {"updated": True}

    def list_sending_domains(self) -> list[dict[str, str]]:
        return [{"domain": "mail.river-market.test"}]


def test_release_orders_mx_and_reports_storefront_readiness() -> None:
    client = RecordingClient()
    request = ReleaseInput(
        domain="mail.river-market.test",
        operation_id="checkout-release-1042",
        exchanges=[
            ExchangeInput(host="backup.mx.test", priority=20),
            ExchangeInput(host="primary.mx.test", priority=10),
        ],
    )

    result = configure_storefront_mail(request, client)

    assert [write["content"] for write in client.writes] == [
        "primary.mx.test",
        "backup.mx.test",
    ]
    assert {write["zone_id"] for write in client.writes} == {"zone_storefront_42"}
    assert result["event"]["primary_exchange"] == "primary.mx.test"
    assert result["diagnostics"]["sending_domain_configured"] is True
