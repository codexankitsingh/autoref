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

    # User Profile (single-user MVP)
    user_name: str = ""
    user_email: str = ""
    user_profile: str = ""  # Pre-stored resume/profile text for AI context

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
