from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    service_name: str = "time_tracking"
    expenses_service_url: str = "http://expenses:1242"
    # Проверка JWT на /users/me (обязательно при работе через API)
    auth_service_url: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
