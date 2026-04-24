"""Конфиг: Microsoft Graph (client credentials) + почтовый ящик, без БД."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "call_schedule"
    auth_service_url: str = "http://auth:1236"

    # Shared mailbox (UPN) — календари и события этого ящика
    call_schedule_mailbox: str = "info@kostalegal.com"

    # Azure App Registration: только application permissions (client credentials)
    microsoft_tenant_id: str = ""
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""

    @field_validator("auth_service_url", mode="before")
    @classmethod
    def _auth_url(cls, v: object) -> object:
        if v is None or (isinstance(v, str) and not str(v).strip()):
            return "http://auth:1236"
        return v

    @field_validator("call_schedule_mailbox", "microsoft_tenant_id", "microsoft_client_id", mode="before")
    @classmethod
    def _strip(cls, v: object) -> str:
        return (v or "").strip() if v is not None else ""

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
