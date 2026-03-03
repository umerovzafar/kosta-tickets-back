from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    media_path: str = "./media"
    service_name: str = "gateway"
    gateway_base_url: str = ""
    auth_service_url: str = ""
    tickets_service_url: str = ""
    notifications_service_url: str = ""
    inventory_service_url: str = ""
    frontend_url: str = ""
    admin_frontend_url: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


def get_settings() -> Settings:
    return Settings()
