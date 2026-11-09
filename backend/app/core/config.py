"""Application settings, read from environment variables (see .env.dev.example)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = Field(default="development", description="development or production")
    app_version: str = "0.2.0"
    log_level: str = "INFO"

    # Neo4j
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "change-me-dev-only"
    neo4j_database: str = "neo4j"

    # LLM provider. Only "ollama" is implemented.
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://host.docker.internal:11434"
    llm_chat_model: str = "qwen2.5:7b-instruct"
    llm_embed_model: str = "nomic-embed-text"
    llm_timeout_seconds: float = 120.0
    llm_num_ctx: int = 8192  # context window; larger values use more VRAM
    llm_keep_alive: str = "5m"  # how long Ollama keeps the model loaded after a request

    # Retrieval. The vector index dimension MUST match the embedding model (768 for nomic-embed-text).
    embed_dimensions: int = 768
    retrieval_k: int = 4
    # nomic-embed-text was trained with these prefixes; they improve retrieval quality.
    query_prefix: str = "search_query: "
    document_prefix: str = "search_document: "

    # Browser origins allowed to call the API directly (the Next.js proxy does not need this).
    cors_origins: str = "http://localhost:3000"

    # Seconds to wait for dependency checks.
    health_timeout_seconds: float = 3.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
