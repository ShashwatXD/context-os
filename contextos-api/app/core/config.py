"""ContextOS Application Configuration.

Loads environment variables with type validation and provides defaults
tailored for both local zero-dependency testing and production PostgreSQL.
"""

from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "ContextOS API"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # Database
    # Default to local SQLite with aiosqlite for zero-friction standalone run & tests;
    # Can be overridden by DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/contextos
    DATABASE_URL: str = "sqlite+aiosqlite:///./contextos.db"
    DATABASE_ECHO: bool = False

    # Security & CORS
    SECRET_KEY: str = "contextos-insecure-dev-secret-key-32b"
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ]
    API_TOKEN: Optional[str] = "demo-contextos-token"

    # Ingestion & Matching Thresholds
    EXACT_MATCH_CONFIDENCE: float = 1.0
    CANONICAL_MATCH_CONFIDENCE: float = 0.90
    FUZZY_MATCH_MIN_CONFIDENCE: float = 0.70
    AUTO_LINK_THRESHOLD: float = 0.90  # Above this, automatically create relation
    REVIEW_THRESHOLD: float = 0.70     # Between review and auto_link, create Suggestion

    # MCP Server
    MCP_ENABLED: bool = True
    MCP_SERVER_NAME: str = "contextos-mcp"
    MCP_SERVER_PORT: int = 8001


settings = Settings()

