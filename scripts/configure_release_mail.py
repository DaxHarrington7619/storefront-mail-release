from __future__ import annotations

import json
import os

from storefront_mail.infrai_client import InfraiClient
from storefront_mail.release_service import StorefrontMailRelease
from storefront_mail.release_workflow import ExchangeInput, ReleaseInput, configure_storefront_mail


def main() -> None:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise SystemExit("Set INFRAI_API_KEY before running this script")

    request = StorefrontMailRelease.model_validate(
        {
            "domain": "mail.example-store.com",
            "operation_id": "checkout-release-2026-09-18",
            "exchanges": [
                {"host": "mx2.mailhost.example", "priority": 20},
                {"host": "mx1.mailhost.example", "priority": 10},
            ],
        }
    )
    client = InfraiClient(api_key)
    try:
        workflow_input = ReleaseInput(
            domain=request.domain,
            operation_id=request.operation_id,
            exchanges=[ExchangeInput(item.host, item.priority) for item in request.exchanges],
        )
        result = configure_storefront_mail(workflow_input, client)
        print(json.dumps(result, indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    main()
