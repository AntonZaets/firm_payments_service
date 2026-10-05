from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    operational_api_key: Annotated[SecretStr, Field(min_length=1)]
    database_url: str
    auth_enabled: bool = True
    auth_issuer: str | None = None
    auth_audience: str | None = None
    auth_jwks_url: str | None = None
    auth_jwks_timeout_seconds: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 30
    auth_token_profile: Literal["standard", "dex"] = "standard"
    auth_allow_http: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    reload: bool = False
    max_payments: Annotated[int, Field(ge=1)] = 1_000
    max_description_length: Annotated[int, Field(ge=1)] = 1_000
    serialization_attempts: Annotated[int, Field(ge=1)] = 3
    serialization_retry_delay_ms: Annotated[int, Field(ge=0)] = 50
    statement_timeout_ms: Annotated[int, Field(ge=1)] = 60_000
    lock_timeout_ms: Annotated[int, Field(ge=1)] = 60_000
    retry_after_seconds: Annotated[int, Field(ge=1)] = 1

    @model_validator(mode="after")
    def validate_auth(self) -> Settings:
        if self.auth_enabled:
            if not all(
                value and value.strip()
                for value in (self.auth_issuer, self.auth_audience, self.auth_jwks_url)
            ):
                raise ValueError("Enabled auth requires issuer, audience and JWKS URL")
            url = urlsplit(self.auth_jwks_url or "")
            schemes = {"https", "http"} if self.auth_allow_http else {"https"}
            if (
                url.scheme not in schemes
                or not url.hostname
                or url.username
                or url.password
                or url.fragment
            ):
                raise ValueError(
                    "JWKS URL requires HTTPS or explicit AUTH_ALLOW_HTTP=true"
                )
        return self

    def __init__(self) -> None:
        # Settings are supplied by environment variables and .env.
        super().__init__()
