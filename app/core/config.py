"""
Application configuration and settings.
Loads from environment variables (.env file).
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """App settings with defaults."""
    
    # API
    PROJECT_NAME: str = "T1D Prediction API"
    VERSION: str = "0.1.0"
    DEBUG: bool = True
    
    # Database
    DATABASE_URL: str = "sqlite:///./t1d_prediction.db"
    # For async SQLite:
    DATABASE_URL_ASYNC: str = "sqlite+aiosqlite:///./t1d_prediction.db"
    
    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS
    ALLOWED_ORIGINS: list = ["http://localhost:19006", "http://localhost:3000"]
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()