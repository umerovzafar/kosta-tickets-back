from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    media_path: str = "./media"
    service_name: str = "gateway"
    gateway_base_url: str = ""
    auth_service_url: str = "http://auth:1236"  # для Docker; при локальном запуске задать в .env
    tickets_service_url: str = ""
    notifications_service_url: str = ""
    inventory_service_url: str = ""
    time_tracking_service_url: str = ""
    expenses_service_url: str = ""

    @field_validator("expenses_service_url", mode="before")
    @classmethod
    def _default_expenses_url_if_empty(cls, v: object) -> object:
        # Portainer/stack часто передаёт пустую строку — тогда подставляем URL из docker-compose
        if v is None or (isinstance(v, str) and not v.strip()):
            return "http://expenses:1242"
        return v

    attendance_service_url: str = ""
    attendance_hikvision_allowed_ips: str = ""
    todos_service_url: str = ""
    frontend_url: str = ""
    admin_frontend_url: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


def get_settings() -> Settings:
    return Settings()
