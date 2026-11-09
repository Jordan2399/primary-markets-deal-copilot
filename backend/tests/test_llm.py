"""LLM layer: Ollama provider (with a mocked HTTP server) and JSON output with retry."""

import json

import httpx
import pytest
from pydantic import BaseModel

from app.llm.base import LLMError, LLMOutputError, LLMUnavailableError
from app.llm.fake import FakeLLM, hash_embedding
from app.llm.json_output import chat_json
from app.llm.ollama import OllamaProvider


def provider(handler: httpx.MockTransport) -> OllamaProvider:
    return OllamaProvider("http://ollama.test", "chat-model", "embed-model", transport=handler)


async def test_chat_returns_content_and_sends_schema() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "hello"}})

    llm = provider(httpx.MockTransport(handler))
    text = await llm.chat([{"role": "user", "content": "hi"}], json_schema={"type": "object"})
    assert text == "hello"
    assert seen["model"] == "chat-model"
    assert seen["stream"] is False
    assert seen["format"] == {"type": "object"}
    assert seen["options"]["temperature"] == 0.0  # type: ignore[index]
    await llm.aclose()


async def test_missing_model_gives_a_helpful_message() -> None:
    llm = provider(httpx.MockTransport(lambda r: httpx.Response(404, json={"error": "not found"})))
    with pytest.raises(LLMError, match="ollama pull chat-model"):
        await llm.chat([{"role": "user", "content": "hi"}])


async def test_unreachable_server_is_reported_as_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    llm = provider(httpx.MockTransport(handler))
    with pytest.raises(LLMUnavailableError):
        await llm.chat([{"role": "user", "content": "hi"}])


async def test_stream_yields_pieces_until_done() -> None:
    lines = [
        {"message": {"content": "Hel"}, "done": False},
        {"message": {"content": "lo"}, "done": False},
        {"message": {"content": ""}, "done": True},
    ]
    body = "\n".join(json.dumps(line) for line in lines).encode()
    llm = provider(httpx.MockTransport(lambda r: httpx.Response(200, content=body)))
    pieces = [p async for p in llm.stream([{"role": "user", "content": "hi"}])]
    assert pieces == ["Hel", "lo"]


async def test_stream_error_line_raises() -> None:
    body = json.dumps({"error": "model crashed"}).encode()
    llm = provider(httpx.MockTransport(lambda r: httpx.Response(200, content=body)))
    with pytest.raises(LLMError, match="model crashed"):
        [p async for p in llm.stream([{"role": "user", "content": "hi"}])]


async def test_embed_returns_vectors_and_checks_count() -> None:
    llm = provider(
        httpx.MockTransport(
            lambda r: httpx.Response(200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]})
        )
    )
    assert await llm.embed(["a", "b"]) == [[0.1, 0.2], [0.3, 0.4]]
    with pytest.raises(LLMError, match="different number"):
        await llm.embed(["only one"])
    assert await llm.embed([]) == []


class Answer(BaseModel):
    value: int


async def test_chat_json_retries_once_with_the_error() -> None:
    llm = FakeLLM(chat_responses=["not json", '{"value": 7}'])
    result = await chat_json(llm, [{"role": "user", "content": "q"}], Answer)
    assert result.value == 7
    assert len(llm.chat_calls) == 2
    retry_prompt = llm.chat_calls[1][-1]["content"]
    assert "not valid" in retry_prompt


async def test_chat_json_gives_up_after_the_retry() -> None:
    llm = FakeLLM(chat_responses=["nope", '{"value": "x"}'])
    with pytest.raises(LLMOutputError):
        await chat_json(llm, [{"role": "user", "content": "q"}], Answer)
    assert len(llm.chat_calls) == 2


def test_hash_embedding_is_normalised_deterministic_and_lexical() -> None:
    a = hash_embedding("allocation and scale back of orders")
    b = hash_embedding("allocation and scale back of orders")
    c = hash_embedding("settlement instructions and closing")
    assert a == b
    assert len(a) == 768
    assert abs(sum(x * x for x in a) - 1.0) < 1e-9
    similar = sum(
        x * y for x, y in zip(a, hash_embedding("how does scale back allocation work"), strict=True)
    )
    unrelated = sum(x * y for x, y in zip(a, c, strict=True))
    assert similar > unrelated
