"""Structured output: ask for JSON that matches a Pydantic model, validate it, retry once.

A 7B model sometimes returns almost-right JSON. Passing the schema to Ollama's `format`
option makes that rare; validating with Pydantic and retrying once with the error message
makes it safe. If the second attempt also fails we raise `LLMOutputError` and the caller
decides what to do (the Copilot falls back to keyword routing).
"""

from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.llm.base import ChatMessage, LLMOutputError, LLMProvider

M = TypeVar("M", bound=BaseModel)


async def chat_json(
    llm: LLMProvider, messages: list[ChatMessage], model_cls: type[M], *, retries: int = 1
) -> M:
    schema = model_cls.model_json_schema()
    conversation = list(messages)
    last_error = ""
    for _attempt in range(retries + 1):
        raw = await llm.chat(conversation, temperature=0.0, json_schema=schema)
        try:
            return model_cls.model_validate_json(raw)
        except ValidationError as exc:
            last_error = str(exc)[:300]
            conversation = [
                *messages,
                {"role": "assistant", "content": raw[:500]},
                {
                    "role": "user",
                    "content": (
                        "That reply was not valid. Reply with ONLY JSON matching the schema. "
                        f"Problem: {last_error}"
                    ),
                },
            ]
    raise LLMOutputError(f"The model did not return valid JSON: {last_error}")
