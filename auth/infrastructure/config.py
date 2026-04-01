from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = ""
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""
    # И AUTH_REDIRECT_URI, и AZURE_REDIRECT_URI (как в .env.example и docker-compose)
    auth_redirect_uri: str = Field(
        default="",
        validation_alias=AliasChoices("AUTH_REDIRECT_URI", "AZURE_REDIRECT_URI"),
    )
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080
    frontend_url: str = ""
    admin_frontend_url: str = ""
    admin_username: str = "admin"
    admin_password: str = ""
    # Одноразовая первичная настройка: POST /auth/admin-bootstrap с телом {"secret": "..."}.
    # После генерации пароль хранится в БД (bcrypt); env ADMIN_PASSWORD для входа не нужен.
    admin_bootstrap_secret: str = Field(
        default="",
        validation_alias=AliasChoices("ADMIN_BOOTSTRAP_SECRET", "admin_bootstrap_secret"),
    )
    service_name: str = "auth"


def get_settings() -> Settings:
    return Settings()


def validate_production_secrets(settings: Settings) -> None:
    """Проверка обязательных секретов при старте. Вызывает RuntimeError при небезопасной конфигурации."""
    if not (settings.jwt_secret or "").strip():
        raise RuntimeError(
            "JWT_SECRET is required. Set JWT_SECRET in environment (e.g. in .env or docker-compose)."
        )
