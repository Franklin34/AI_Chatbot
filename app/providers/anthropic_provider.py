from collections.abc import AsyncIterator

import anthropic

from .base import LLMError, Message

RETRYABLE = {429, 500, 502, 503, 529}


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        self.model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def stream(
        self, messages: list[Message], system: str, max_tokens: int
    ) -> AsyncIterator[str]:
        try:
            async with self._client.messages.stream(
                model=self.model, max_tokens=max_tokens, system=system, messages=messages
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except anthropic.AuthenticationError as e:
            raise LLMError("Invalid ANTHROPIC_API_KEY.") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("Could not reach the Anthropic API.", retryable=True) from e
        except anthropic.APIStatusError as e:
            if e.status_code in RETRYABLE:
                raise LLMError(
                    "The model is busy or rate limited. Please try again shortly.", retryable=True
                ) from e
            raise LLMError(f"LLM error: {e.message}") from e
