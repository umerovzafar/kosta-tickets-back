from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = ""
    service_name: str = "time_tracking"
    expenses_service_url: str = "http://expenses:1242"
    auth_service_url: str = Field(default="", validation_alias=AliasChoices("AUTH_SERVICE_URL"))
    time_tracking_allow_business_data_reset: bool = Field(
        default=False,
        validation_alias=AliasChoices("TIME_TRACKING_ALLOW_BUSINESS_DATA_RESET"),
    )

    @field_validator("auth_service_url", mode="before")
    @classmethod
    def _default_auth_url_if_empty(cls, v: object) -> object:
        if v is None or (isinstance(v, str) and not str(v).strip()):
            return "http://auth:1236"
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
