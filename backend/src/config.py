"""
Application configuration using pydantic-settings.
All config is loaded from environment variables or .env file.
"""

from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    """Central configuration for the application."""

    # ── Database (Supabase PostgreSQL) ──────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/learning_rec"

    # ── Redis ───────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379"

    # ── Anthropic Claude API ────────────────────────────────────
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
    CLAUDE_MAX_TOKENS: int = 1024

    # ── JWT Auth ────────────────────────────────────────────────
    JWT_SECRET: str = "change-this-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 1440  # 24 hours

    # ── App ─────────────────────────────────────────────────────
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    FRONTEND_URL: str = "http://localhost:5173"

    # ── CORS ────────────────────────────────────────────────────
    CORS_ORIGINS: str = '["http://localhost:5173","http://localhost:3000"]'

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from JSON string to list."""
        return json.loads(self.CORS_ORIGINS)

    # ── Engine ──────────────────────────────────────────────────
    TFIDF_MAX_FEATURES: int = 5000
    RECOMMENDATION_TOP_N: int = 10
    SIMILARITY_CACHE_TTL: int = 3600  # 1 hour

    # ── Re-ranking weights ──────────────────────────────────────
    WEIGHT_LIKE_INCREMENT: float = 0.2
    WEIGHT_SKIP_DECREMENT: float = 0.3
    WEIGHT_COMPLETE_INCREMENT: float = 0.5
    WEIGHT_SAVE_INCREMENT: float = 0.15
    WEIGHT_MIN: float = 0.1
    WEIGHT_MAX: float = 3.0

    # ── Production ──────────────────────────────────────────────
    FRONTEND_DIST_PATH: str = ""

    @property
    def is_production(self) -> bool:
        """Check if the app is running in production mode."""
        return self.APP_ENV.lower() in ("production", "prod")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


# Singleton instance
settings = Settings()

# FIX [SECURITY] — prevent shipping with default JWT secret in production.
# The default value "change-this-in-production" is a placeholder that would
# allow anyone to forge valid JWTs.
if settings.is_production and settings.JWT_SECRET == "change-this-in-production":
    raise RuntimeError(
        "CRITICAL: JWT_SECRET must be changed from its default value "
        "before running in production. Set it via the JWT_SECRET env var."
    )
