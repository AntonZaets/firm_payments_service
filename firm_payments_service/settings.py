from typing import Annotated, Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    operational_api_key: Annotated[SecretStr, Field(min_length=1)]
    database_url: str
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    reload: bool = False

    def __init__(self) -> None:
        # Settings are supplied by environment variables and .env.
        super().__init__()
