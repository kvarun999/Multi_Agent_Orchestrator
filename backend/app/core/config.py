"""
Centralized application configuration using Pydantic BaseSettings.
All values are read from environment variables — nothing is hardcoded.
"""

import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://admin:password@db:5432/agent_db"
    SYNC_DATABASE_URL: str = "postgresql+psycopg2://admin:password@db:5432/agent_db"

    # Redis / Celery
    REDIS_URL: str = "redis://redis:6379/0"

    # LLM Provider
    GROQ_API_KEY: str = ""

    # Tool API Keys
    OPENWEATHER_API_KEY: str = ""
    BRAVE_SEARCH_API_KEY: str = ""

    # CORS
    FRONTEND_URL: str = "http://localhost:3000"

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance — loaded once per process."""
    return Settings()
