from collections.abc import AsyncIterator

import openai

from .base import LLMError, Message

RETRYABLE = {429, 500, 502, 503}


class OpenAICompatProvider:
    """OpenAI, plus anything exposing the same API (Groq, OpenRouter, Ollama, ...)."""

    name = "openai"

    def __init__(self, api_key: str | None, model: str, base_url: str | None = None):
        self.model = model
        # Local servers such as Ollama ignore the key but the SDK requires a value.
        self._client = openai.AsyncOpenAI(api_key=api_key or "not-needed", base_url=base_url)

    async def stream(
        self, messages: list[Message], system: str, max_tokens: int
    ) -> AsyncIterator[str]:
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, *messages],
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except openai.AuthenticationError as e:
            raise LLMError("Invalid OPENAI_API_KEY.") from e
        except openai.APIConnectionError as e:
            raise LLMError("Could not reach the LLM endpoint.", retryable=True) from e
        except openai.APIStatusError as e:
            if e.status_code in RETRYABLE:
                raise LLMError(
                    "The model is busy or rate limited. Please try again shortly.", retryable=True
                ) from e
            raise LLMError(f"LLM error: {e.message}") from e
