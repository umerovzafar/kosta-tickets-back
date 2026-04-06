from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки сервиса проектов."""

    database_url: str = ""
    service_name: str = "projects"

    model_config = {"env_file": ".env", "extra": "ignore"}


def get_settings() -> Settings:
    return Settings()
