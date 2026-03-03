from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""
    auth_redirect_uri: str = ""
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080
    frontend_url: str = ""
    admin_frontend_url: str = ""
    admin_username: str = "admin"
    admin_password: str = "admin123"
    service_name: str = "auth"

    model_config = {"env_file": ".env", "extra": "ignore"}


def get_settings() -> Settings:
    return Settings()
