from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    service_name: str = "todos"
    # Auth: проверка пользователя по токену (GET /users/me)
    auth_service_url: str = ""
    # Microsoft Graph (календарь Outlook)
    microsoft_client_id: str = ""
    microsoft_tenant_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_redirect_uri: str = ""
    # Куда редиректить пользователя после успешного/неуспешного OAuth календаря
    calendar_connected_redirect_url: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}

    @field_validator(
        "microsoft_client_id",
        "microsoft_tenant_id",
        "microsoft_client_secret",
        "calendar_connected_redirect_url",
        mode="before",
    )
    @classmethod
    def strip_str(cls, v: str) -> str:
        return (v or "").strip()

    @field_validator("microsoft_redirect_uri", mode="before")
    @classmethod
    def normalize_redirect_uri(cls, v: str) -> str:
        # Убираем пробелы, переносы и лишнее, чтобы не склеилось с другой переменной
        return (v or "").strip().replace("\n", "").replace("\r", "").split()[0]


def get_settings() -> Settings:
    return Settings()
