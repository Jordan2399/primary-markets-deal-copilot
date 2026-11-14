"""Application settings, read from environment variables (see .env.dev.example)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All settings. Each field can be overridden by an environment variable of the same name."""

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
    # Term sheets: "gaps" = fixed rules read first and the model only fills what they missed;
    # "always" = the model reads every document and the rules fill its blanks.
    termsheet_model_mode: Literal["gaps", "always"] = "gaps"

    # Retrieval. The vector index dimension MUST match the embedding model (768 for nomic-embed-text).
    embed_dimensions: int = 768
    retrieval_k: int = 4
    # nomic-embed-text was trained with these prefixes; they improve retrieval quality.
    query_prefix: str = "search_query: "
    document_prefix: str = "search_document: "

    # Browser origins allowed to call the API directly (the Next.js proxy does not need this).
    cors_origins: str = "http://localhost:3000"

    # Authentication. "jwt" = sign in with a username and password and send a signed token.
    # "demo" = trust the X-Demo-Role / X-Demo-User headers; development and tests only.
    auth_mode: Literal["jwt", "demo"] = "jwt"
    jwt_secret: str = "dev-only-secret-change-me-dev-only-secret-0000"
    jwt_ttl_minutes: int = 480  # token lifetime: 8 hours, one working day
    # Password given to the seeded demo users (development only; see the seed).
    demo_user_password: str = ""

    # Seconds to wait for dependency checks.
    health_timeout_seconds: float = 3.0

    def check_safe_to_run(self) -> None:
        """Refuse to start a production deployment with demo-grade security settings."""
        # Development may use the defaults; only production is checked.
        if self.app_env != "production":
            return
        problems = []
        if self.auth_mode != "jwt":
            problems.append("AUTH_MODE must be 'jwt' in production")
        # A short or default secret would let anyone forge a token with any role.
        if len(self.jwt_secret) < 32 or self.jwt_secret.startswith("dev-only"):
            problems.append("JWT_SECRET must be a random value of at least 32 characters")
        if self.neo4j_password.startswith("change-me"):
            problems.append("NEO4J_PASSWORD must be changed")
        # Report all problems at once so they can be fixed in one go.
        if problems:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS_ORIGINS split on commas, trimmed, empty entries dropped."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """One shared Settings object (cached). Tests override this dependency."""
    return Settings()
