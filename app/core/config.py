from enum import Enum
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.development",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    APP_NAME: str = "TravelPlannerAI"
    APP_VERSION: str = "1.0.0"
    API_PREFIX: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # JWT
    JWT_SECRET_KEY: str = "dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/travel_planner"
    DATABASE_SYNC_URL: str = "postgresql://postgres:postgres@localhost:5432/travel_planner"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Neo4j
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j_password"
    NEO4J_DATABASE: str = "neo4j"

    # LLM
    OPENAI_API_KEY: str = "your-openai-api-key"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TEMPERATURE: float = 0.7

    # Langfuse
    LANGFUSE_PUBLIC_KEY: str = "your-langfuse-public-key"
    LANGFUSE_SECRET_KEY: str = "your-langfuse-secret-key"
    LANGFUSE_HOST: str = "http://localhost:3000"

    # Mem0
    MEM0_COLLECTION_NAME: str = "travel_planner_memory"

    # Weather API
    WEATHER_API_KEY: str = "your-weather-api-key"
    WEATHER_API_URL: str = "https://api.openweathermap.org/data/2.5"

    # Rate Limiting
    RATE_LIMIT_DEFAULT: str = "100/minute"
    RATE_LIMIT_AUTH: str = "10/minute"
    RATE_LIMIT_CHAT: str = "30/minute"

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | List[str]) -> List[str]:
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == Environment.DEVELOPMENT

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == Environment.PRODUCTION

    @property
    def rate_limit_endpoints(self) -> dict:
        return {
            "default": [self.RATE_LIMIT_DEFAULT],
            "auth": [self.RATE_LIMIT_AUTH],
            "chat": [self.RATE_LIMIT_CHAT],
        }


settings = Settings()
