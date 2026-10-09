from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from .errors import InfraiError
from .infrai_client import InfraiClient
from .release_workflow import ExchangeInput, ReleaseInput, configure_storefront_mail


class MailExchange(BaseModel):
    host: str = Field(min_length=1)
    priority: int = Field(ge=0, le=65535)


class StorefrontMailRelease(BaseModel):
    domain: str = Field(min_length=3)
    operation_id: str = Field(min_length=8, max_length=100)
    exchanges: list[MailExchange] = Field(min_length=1)

    @field_validator("exchanges")
    @classmethod
    def priorities_must_be_unique(cls, exchanges: list[MailExchange]) -> list[MailExchange]:
        priorities = [exchange.priority for exchange in exchanges]
        if len(priorities) != len(set(priorities)):
            raise ValueError("MX priorities must be unique")
        return exchanges


class BuildEvent(BaseModel):
    name: Literal["mail-routing-configured"]
    domain: str
    primary_exchange: str


class ReleaseDiagnostics(BaseModel):
    zone_id: str
    mx_records_written: int
    sending_domain_configured: bool


class ReleaseResult(BaseModel):
    state: Literal["released"]
    event: BuildEvent
    diagnostics: ReleaseDiagnostics


def get_client() -> InfraiClient:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="INFRAI_API_KEY is required")
    return InfraiClient(api_key)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


service = FastAPI(title="Storefront mail release", lifespan=lifespan)


@service.post("/releases/mail-routing", response_model=ReleaseResult)
def release_mail_routing(
    request: StorefrontMailRelease,
    client: Annotated[InfraiClient, Depends(get_client)],
) -> ReleaseResult:
    try:
        workflow_input = ReleaseInput(
            domain=request.domain,
            operation_id=request.operation_id,
            exchanges=[ExchangeInput(item.host, item.priority) for item in request.exchanges],
        )
        return ReleaseResult.model_validate(configure_storefront_mail(workflow_input, client))
    except InfraiError as exc:
        status_code = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(
            status_code=status_code,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    finally:
        client.close()


def run() -> None:
    import uvicorn

    uvicorn.run("storefront_mail.release_service:service", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
