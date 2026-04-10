from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    media_path: str = "./media"
    service_name: str = "tickets"
    max_attachment_size_mb: int = 15
    # Если задан, WebSocket /ws/tickets принимает только с ?internal_key=... (gateway подставляет).
    ws_internal_secret: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
