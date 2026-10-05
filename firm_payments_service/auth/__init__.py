from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader

from firm_payments_service.config import Settings

settings = Settings()


def require_operational_key(
    key: Annotated[
        str | None, Depends(APIKeyHeader(name="X-API-Key", auto_error=False))
    ],
) -> None:
    if key is None or not compare_digest(
        key.encode(), settings.operational_api_key.get_secret_value().encode()
    ):
        raise HTTPException(status_code=401, detail="Invalid API key")
