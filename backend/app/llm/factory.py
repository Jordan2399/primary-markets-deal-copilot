"""Choose the LLM provider from settings (LLM_PROVIDER)."""

from app.core.config import Settings
from app.llm.base import LLMProvider
from app.llm.ollama import OllamaProvider


def create_provider(settings: Settings) -> LLMProvider:
    provider = settings.llm_provider.lower()
    if provider == "ollama":
        return OllamaProvider(
            settings.ollama_base_url,
            settings.llm_chat_model,
            settings.llm_embed_model,
            timeout=settings.llm_timeout_seconds,
            num_ctx=settings.llm_num_ctx,
            keep_alive=settings.llm_keep_alive,
        )
    # Future scope: "openai" and "anthropic" providers implementing the LLMProvider protocol.
    raise ValueError(
        f"LLM_PROVIDER='{settings.llm_provider}' is not available yet. Only 'ollama' is implemented."
    )
