from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "telegram_bot"
    telegram_bot_token: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


def get_settings() -> Settings:
    return Settings()
