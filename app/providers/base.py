from collections.abc import AsyncIterator
from typing import Literal, Protocol, TypedDict


class Message(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class LLMError(Exception):
    """Provider-agnostic failure with a message that is safe to show to end users."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.retryable = retryable


class LLMProvider(Protocol):
    """Anything that can turn a conversation into a stream of text chunks.

    Implementations must translate vendor SDK exceptions into `LLMError`.
    """

    name: str
    model: str

    def stream(
        self, messages: list[Message], system: str, max_tokens: int
    ) -> AsyncIterator[str]: ...
