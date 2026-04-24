from functools import lru_cache

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings

# Дефолты как в docker-compose — пустые значения из Portainer не должны ломать прокси.
_DEFAULT_SERVICE_URLS: dict[str, str] = {
    "auth_service_url": "http://auth:1236",
    "tickets_service_url": "http://tickets:1235",
    "notifications_service_url": "http://notifications:1237",
    "inventory_service_url": "http://inventory:1238",
    "todos_service_url": "http://todos:1240",
    "time_tracking_service_url": "http://time_tracking:1241",
    "expenses_service_url": "http://expenses:1242",
    "projects_service_url": "http://projects:1243",
    "attendance_service_url": "http://attendance:1239",
    "vacation_service_url": "http://vacation:1244",
    "call_schedule_service_url": "http://call_schedule:1245",
}


class Settings(BaseSettings):
    database_url: str = ""
    media_path: str = "./media"
    service_name: str = "gateway"
    gateway_base_url: str = ""
    auth_service_url: str = ""
    tickets_service_url: str = ""
    notifications_service_url: str = ""
    inventory_service_url: str = ""
    time_tracking_service_url: str = ""
    expenses_service_url: str = ""
    projects_service_url: str = ""
    attendance_service_url: str = ""
    vacation_service_url: str = ""
    attendance_hikvision_allowed_ips: str = ""
    todos_service_url: str = ""
    call_schedule_service_url: str = ""
    frontend_url: str = ""
    admin_frontend_url: str = ""
    # CORS: широкий regex для частных сетей (RFC1918). В проде обычно отключают.
    cors_allow_private_network: bool = False
    # Общий секрет для backend WebSocket (tickets, notifications); gateway подставляет в query.
    ws_internal_secret: str = ""
    # HSTS только если gateway отдаёт ответы по HTTPS (иначе браузер игнорирует).
    security_hsts_enabled: bool = False
    # Опционально, например: default-src 'none'; frame-ancestors 'none'
    security_csp: str = ""
    # Тот же секрет, что у auth — для проверки OAuth state на /api/v1/auth/azure/callback
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    # Как у auth — Max-Age HttpOnly-cookie после OAuth (секунды).
    jwt_expire_minutes: int = Field(default=1440, validation_alias="JWT_EXPIRE_MINUTES")
    # Совпадает с auth AUTH_SESSION_COOKIE_NAME — для прокси и verify_bearer с cookie.
    auth_session_cookie_name: str = "kl_access_token"
    auth_set_session_cookie: bool = Field(default=False, validation_alias="AUTH_SET_SESSION_COOKIE")
    auth_session_cookie_secure: bool = Field(default=True, validation_alias="AUTH_SESSION_COOKIE_SECURE")
    auth_session_cookie_samesite: str = Field(default="lax", validation_alias="AUTH_SESSION_COOKIE_SAMESITE")

    @field_validator(*tuple(_DEFAULT_SERVICE_URLS.keys()), mode="before")
    @classmethod
    def _default_microservice_urls_if_empty(cls, v: object, info: ValidationInfo) -> object:
        key = info.field_name or ""
        default = _DEFAULT_SERVICE_URLS.get(key)
        if default is None:
            return v
        if v is None or (isinstance(v, str) and not v.strip()):
            return default
        return v

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
