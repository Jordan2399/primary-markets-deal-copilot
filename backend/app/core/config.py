"""Application settings, read from environment variables (see .env.example)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = Field(default="development", description="development or production")
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    # Neo4j
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "change-me-dev-only"

    # LLM provider. Only "ollama" is implemented on day 0.
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://host.docker.internal:11434"
    llm_chat_model: str = "qwen2.5:7b-instruct"
    llm_embed_model: str = "nomic-embed-text"

    # Browser origins allowed to call the API (comma separated).
    cors_origins: str = "http://localhost:3000"

    # Seconds to wait for dependency checks.
    health_timeout_seconds: float = 3.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
