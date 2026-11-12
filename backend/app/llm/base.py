"""The LLM provider interface.

The rest of the application depends only on `LLMProvider`. Ollama is the default
implementation. To add OpenAI or Claude later, write another class with the same four
methods and register it in `factory.py`; no other file changes.
"""

from collections.abc import AsyncIterator
from typing import Any, Literal, Protocol, TypedDict

from app.core.errors import UpstreamError


class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMError(UpstreamError):
    """The model server answered with an error."""

    code = "llm_error"


class LLMUnavailableError(LLMError):
    """The model server could not be reached or timed out."""

    code = "llm_unavailable"


class LLMOutputError(LLMError):
    """The model answered, but not in the format we asked for."""

    code = "llm_bad_output"


class LLMProvider(Protocol):
    name: str
    model: str

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.0,
        json_schema: dict[str, Any] | None = None,
    ) -> str: ...

    def stream(
        self, messages: list[ChatMessage], *, temperature: float = 0.2
    ) -> AsyncIterator[str]: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def aclose(self) -> None: ...
