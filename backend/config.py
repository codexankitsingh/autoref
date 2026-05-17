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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()

