"""
FastAPI Configuration Management
Uses Pydantic settings to load from .env file
"""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    APP_NAME: str = "T1D Glucose Forecasting Backend"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database (asyncpg driver for async/await support)
    DATABASE_URL: str = "postgresql+asyncpg://t1d_app:password@localhost:5432/t1d_glucose"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_POOL_RECYCLE: int = 3600

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Logging
    LOG_LEVEL: str = "INFO"

    # CORS
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3001",
        "http://localhost:8080",
        "http://192.168.2.120:5173",
    ]

    class Config:
        """Pydantic config."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


# Global settings instance
settings = Settings()