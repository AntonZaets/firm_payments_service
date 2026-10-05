from typing import Annotated, Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    operational_api_key: Annotated[SecretStr, Field(min_length=1)]
    database_url: str
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    reload: bool = False
    max_payments: Annotated[int, Field(ge=1)] = 1_000
    max_description_length: Annotated[int, Field(ge=1)] = 1_000
    serialization_attempts: Annotated[int, Field(ge=1)] = 3
    serialization_retry_delay_ms: Annotated[int, Field(ge=0)] = 50
    statement_timeout_ms: Annotated[int, Field(ge=1)] = 60_000
    lock_timeout_ms: Annotated[int, Field(ge=1)] = 60_000
    retry_after_seconds: Annotated[int, Field(ge=1)] = 1

    def __init__(self) -> None:
        # Settings are supplied by environment variables and .env.
        super().__init__()
