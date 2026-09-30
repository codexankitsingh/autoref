from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./autoref.db"

    # Google Gemini API
    gemini_api_key: str = ""

    # Gmail OAuth2
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/gmail/callback"

    # Google Sheets
    google_sheets_credentials_path: str = "./credentials.json"

    # App
    app_secret_key: str = "change-this-in-production"
    frontend_url: str = "http://localhost:3000"

    # JWT Authentication
    jwt_secret_key: str = "change-this-jwt-secret-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440  # 24 hours
    jwt_refresh_token_expire_days: int = 7

    # Admin email — first registered user OR this email gets auto-approved as admin
    admin_email: str = ""

    # Resume links (override in .env when Drive URLs change)
    resume_link_data_engineering: str = (
        "https://drive.google.com/file/d/1Cji1HuzTh1SVnTcfYGzAJN-BTxnUQYmL/view?usp=drive_link"
    )
    resume_link_backend_sde: str = (
        "https://drive.google.com/file/d/1J1pLwgjVvm0VnI2Dd3CM5_66snSCk3uv/view?usp=sharing"
    )
    resume_link_fintech: str = (
        "https://drive.google.com/file/d/1CXlPUQJgoJ_STt8eWmTpvj_FVbyv9ZhK/view?usp=sharing"
    )
    resume_link_systems: str = (
        "https://drive.google.com/file/d/1K61zy3JA7inlXdAZ6aaZD8ETl61qJ38u/view?usp=sharing"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()

