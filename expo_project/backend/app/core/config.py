from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), extra="ignore")

    app_name: str = "Enterprise Analytics Platform"
    api_v1_prefix: str = "/api/v1"

    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 8

    encryption_key: str = ""

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"

    # MongoDB Atlas connection string — stores user login credentials
    mongo_url: str = ""

    # Optional bootstrap user for enterprise onboarding
    super_admin_email: str = ""
    super_admin_password: str = ""
    super_admin_full_name: str = "Platform Super Admin"


settings = Settings()
