import os
from pydantic import field_validator
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./autoref.db"

    # Google Gemini API
    gemini_api_key: str = ""

    # LLM provider: auto (Gemini, fallback OpenAI on 403), gemini, openai
    ai_provider: str = "auto"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "openai/gpt-oss-120b"

    # Job scraper (optional heavy deps — disable on Render free tier)
    enable_job_scraper: bool = True

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

    # Data Engineering resume (override in .env when Drive URL changes)
    resume_link_data_engineering: str = (
        "https://drive.google.com/file/d/1Cji1HuzTh1SVnTcfYGzAJN-BTxnUQYmL/view?usp=drive_link"
    )

    @field_validator("gemini_api_key", "openai_api_key", mode="before")
    @classmethod
    def strip_api_keys(cls, value):
        if isinstance(value, str):
            return value.strip().strip('"').strip("'")
        return value or ""

    class Config:
        env_file = (
            ".env",
            "backend/.env",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        )
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()

