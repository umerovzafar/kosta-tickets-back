from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    service_name: str = "attendance"
    hikvision_device_ip: str = ""
    hikvision_device_port: int = 80
    hikvision_device_user: str = "admin"
    hikvision_device_password: str = ""
    hikvision_request_timeout: float = 60.0
    hikvision_device_ips: str = ""
    model_config = {"env_file": ".env", "extra": "ignore"}


def get_settings() -> Settings:
    return Settings()
