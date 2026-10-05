from secrets import compare_digest
from typing import Annotated, Any, cast
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

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


def authenticate_payment(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(HTTPBearer(auto_error=False)),
    ],
    config: Annotated[Settings, Depends(Settings)],
) -> UUID | None:
    if not config.auth_enabled:
        return None
    try:
        if credentials is None:
            raise ValueError("Missing bearer token")
        profile = config.auth_token_profile
        algorithm = "ES256" if profile == "standard" else "RS256"
        token = credentials.credentials
        if jwt.get_unverified_header(token).get("alg") != algorithm:
            raise ValueError("Unsupported signing algorithm")
        client = jwt.PyJWKClient(
            config.auth_jwks_url or "",
            timeout=config.auth_jwks_timeout_seconds,
            cache_jwk_set=False,
            cache_keys=False,
        )
        key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=[algorithm],
            issuer=config.auth_issuer,
            audience=config.auth_audience,
            options={"require": ["exp", "iss", "aud"]},
        )
        payer = claims.get("payer_firm_uuid")
        if profile == "dex":
            identity = claims.get("federated_claims")
            if not isinstance(identity, dict):
                raise ValueError("Missing Dex identity")
            identity = cast(dict[str, Any], identity)
            if identity.get("connector_id") != "local":
                raise ValueError("Invalid Dex connector")
            payer = identity.get("user_id")
        if not isinstance(payer, str):
            raise ValueError("Missing payer UUID")
        return UUID(payer)
    except jwt.PyJWTError, ValueError, TypeError, OSError, OverflowError:
        raise HTTPException(
            status_code=401,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


def authorize_payer(identity: UUID | None, payer_firm_uuid: str) -> None:
    if identity is not None and identity != UUID(payer_firm_uuid):
        raise HTTPException(status_code=403, detail="Payer is not authorized")
