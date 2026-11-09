"""Ollama provider (local models).

Talks to Ollama's HTTP API:
  POST /api/chat   chat, optional JSON-schema constrained output ("format"), optional streaming
  POST /api/embed  embeddings for a list of texts
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.llm.base import ChatMessage, LLMError, LLMUnavailableError


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        embed_model: str,
        *,
        timeout: float = 120.0,
        num_ctx: int = 8192,
        keep_alive: str = "5m",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self.embed_model = embed_model
        self._num_ctx = num_ctx
        self._keep_alive = keep_alive
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout, connect=5.0),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _payload(
        self, messages: list[ChatMessage], temperature: float, stream: bool
    ) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "keep_alive": self._keep_alive,
            "options": {"temperature": temperature, "num_ctx": self._num_ctx},
        }

    @staticmethod
    def _error(status: int, body: str, model: str) -> LLMError:
        if status == 404:
            return LLMError(f"Ollama does not have the model '{model}'. Run: ollama pull {model}")
        return LLMError(f"Ollama returned HTTP {status}: {body[:200]}")

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.0,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        payload = self._payload(messages, temperature, stream=False)
        if json_schema is not None:
            payload["format"] = json_schema
        try:
            response = await self._client.post("/api/chat", json=payload)
        except httpx.TransportError as exc:
            raise LLMUnavailableError(f"Cannot reach Ollama: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise self._error(response.status_code, response.text, self.model)
        try:
            return str(response.json()["message"]["content"])
        except (KeyError, ValueError) as exc:
            raise LLMError("Ollama sent a reply in an unexpected format.") from exc

    async def stream(
        self, messages: list[ChatMessage], *, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        payload = self._payload(messages, temperature, stream=True)
        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode(errors="replace")
                    raise self._error(response.status_code, body, self.model)
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if "error" in data:
                        raise LLMError(str(data["error"])[:200])
                    piece = data.get("message", {}).get("content", "")
                    if piece:
                        yield str(piece)
                    if data.get("done"):
                        break
        except httpx.TransportError as exc:
            raise LLMUnavailableError(f"Cannot reach Ollama: {type(exc).__name__}") from exc

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = await self._client.post(
                "/api/embed",
                json={"model": self.embed_model, "input": texts, "keep_alive": self._keep_alive},
            )
        except httpx.TransportError as exc:
            raise LLMUnavailableError(f"Cannot reach Ollama: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise self._error(response.status_code, response.text, self.embed_model)
        try:
            vectors = response.json()["embeddings"]
        except (KeyError, ValueError) as exc:
            raise LLMError("Ollama sent embeddings in an unexpected format.") from exc
        if len(vectors) != len(texts):
            raise LLMError("Ollama returned a different number of embeddings than texts.")
        return [[float(x) for x in v] for v in vectors]
