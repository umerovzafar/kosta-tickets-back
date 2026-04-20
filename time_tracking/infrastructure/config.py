from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    service_name: str = "time_tracking"
    expenses_service_url: str = "http://expenses:1242"
    # Курсы ЦБ РУз (UZS — база котировок)
    fx_cbu_base_url: str = "https://cbu.uz"
    fx_fallback_days: int = 5
    fx_http_timeout_sec: float = 20.0
    """Если true — при недоступности ЦБ запись сохраняется, billable помечается CBU_UNAVAILABLE (сумма 0 в отчётах)."""
    fx_soft_fail: bool = True

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
