"""A deterministic fake provider for tests, CI and offline seeding.

`hash_embedding` turns text into a vector by hashing words into buckets. Texts that share
words get similar vectors, which is enough for tests to check that retrieval ranks the right
page first. It is NOT a real embedding model: use Ollama for the real seed.
"""

import hashlib
import math
import re
from collections.abc import AsyncIterator
from typing import Any

from app.llm.base import ChatMessage, LLMUnavailableError

_STOPWORDS = frozenset(
    "a an and are as at be by for from how in is it of on or that the this to was what when "
    "which who why with do does did can i we you search_query search_document".split()
)


def hash_embedding(text: str, dimensions: int = 768) -> list[float]:
    vector = [0.0] * dimensions
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if word in _STOPWORDS:
            continue
        digest = hashlib.sha256(word.encode()).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class FakeLLM:
    name = "fake"
    model = "fake-model"

    def __init__(
        self,
        chat_responses: list[str] | None = None,
        stream_text: str = "Fake answer. [S1]",
        *,
        fail: bool = False,
        dimensions: int = 768,
    ) -> None:
        self._chat_responses = list(chat_responses or [])
        self._stream_text = stream_text
        self._fail = fail
        self._dimensions = dimensions
        self.chat_calls: list[list[ChatMessage]] = []
        self.stream_calls: list[list[ChatMessage]] = []

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.0,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        self.chat_calls.append(messages)
        if self._fail:
            raise LLMUnavailableError("fake LLM is down")
        return self._chat_responses.pop(0) if self._chat_responses else "{}"

    async def stream(
        self, messages: list[ChatMessage], *, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        self.stream_calls.append(messages)
        if self._fail:
            raise LLMUnavailableError("fake LLM is down")
        for word in self._stream_text.split(" "):
            yield word + " "

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [hash_embedding(t, self._dimensions) for t in texts]

    async def aclose(self) -> None:
        return None
