import asyncio
import logging
from collections.abc import AsyncIterator

from .providers import LLMError, LLMProvider, Message

log = logging.getLogger("chatbot")


async def stream_with_retry(
    provider: LLMProvider,
    messages: list[Message],
    system: str,
    max_tokens: int,
    max_retries: int,
    base_delay: float = 1.0,
) -> AsyncIterator[str]:
    """Stream a completion, retrying transient failures with exponential backoff.

    A retry is only safe before the first chunk reaches the caller; after that the
    user has already seen partial output, so the error is propagated instead.
    """
    attempt = 0
    while True:
        started = False
        try:
            async for chunk in provider.stream(messages, system, max_tokens):
                started = True
                yield chunk
            return
        except LLMError as e:
            if e.retryable and not started and attempt < max_retries:
                delay = base_delay * 2**attempt
                log.warning(
                    "transient LLM error, retry %d/%d in %.1fs", attempt + 1, max_retries, delay
                )
                await asyncio.sleep(delay)
                attempt += 1
                continue
            raise
