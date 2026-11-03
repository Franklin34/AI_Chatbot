from collections.abc import AsyncIterator

from google import genai
from google.genai import errors, types

from .base import LLMError, Message

RETRYABLE = {429, 500, 502, 503, 504}


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str):
        self.model = model
        self._client = genai.Client(api_key=api_key).aio

    async def stream(
        self, messages: list[Message], system: str, max_tokens: int
    ) -> AsyncIterator[str]:
        # Gemini calls the assistant role "model".
        contents = [
            types.Content(
                role="model" if m["role"] == "assistant" else "user",
                parts=[types.Part(text=m["content"])],
            )
            for m in messages
        ]
        try:
            chunks = await self._client.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system, max_output_tokens=max_tokens
                ),
            )
            async for chunk in chunks:
                if chunk.text:
                    yield chunk.text
        except errors.APIError as e:
            raise _translate(e) from e


def _translate(e: errors.APIError) -> LLMError:
    message = str(e.message or "")
    if e.code in (400, 401, 403) and "API key" in message:
        return LLMError("Invalid GEMINI_API_KEY.")
    if e.code in RETRYABLE:
        return LLMError(
            "The model is busy or rate limited. Please try again shortly.", retryable=True
        )
    return LLMError(f"LLM error: {message}")
