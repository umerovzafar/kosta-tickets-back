from decimal import Decimal

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    media_path: str = "./media"
    service_name: str = "expenses"
    auth_service_url: str = "http://auth:1236"

    @field_validator("auth_service_url", mode="before")
    @classmethod
    def _default_auth_url_if_empty(cls, v: object) -> object:
        if v is None or (isinstance(v, str) and not v.strip()):
            return "http://auth:1236"
        return v
    max_upload_mb: int = 25
    # Если задано — submit и create с суммой выше лимита получают ошибку (доп. согласование)
    expense_amount_limit_uzs: Decimal | None = None

    model_config = {"env_file": ".env", "extra": "ignore"}

    @field_validator("expense_amount_limit_uzs", mode="before")
    @classmethod
    def empty_limit(cls, v):
        if v is None or v == "":
            return None
        return v


def get_settings() -> Settings:
    return Settings()
