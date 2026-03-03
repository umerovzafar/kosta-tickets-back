from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    media_path: str = "./media"
    service_name: str = "tickets"
    max_attachment_size_mb: int = 15

    model_config = {"env_file": ".env", "extra": "ignore"}


def get_settings() -> Settings:
    return Settings()
