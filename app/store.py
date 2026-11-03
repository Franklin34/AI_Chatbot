from collections import OrderedDict

from .providers import Message


class ConversationStore:
    """In-memory conversation history with LRU eviction.

    Single-process only. Replace with Redis/Postgres behind the same interface
    to scale horizontally.
    """

    def __init__(self, max_conversations: int = 1000):
        self._max = max_conversations
        self._data: OrderedDict[str, list[Message]] = OrderedDict()
        self._busy: set[str] = set()

    def get(self, conversation_id: str) -> list[Message] | None:
        messages = self._data.get(conversation_id)
        return list(messages) if messages is not None else None

    def window(self, conversation_id: str, limit: int) -> list[Message]:
        """Most recent `limit` messages, always starting on a user turn."""
        messages = self._data.get(conversation_id, [])[-limit:]
        while messages and messages[0]["role"] != "user":
            messages = messages[1:]
        return list(messages)

    def append(self, conversation_id: str, role: str, content: str) -> None:
        messages = self._data.setdefault(conversation_id, [])
        messages.append({"role": role, "content": content})  # type: ignore[typeddict-item]
        self._data.move_to_end(conversation_id)
        while len(self._data) > self._max:
            oldest = next((k for k in self._data if k not in self._busy), None)
            if oldest is None:
                break
            del self._data[oldest]

    def pop_last(self, conversation_id: str) -> None:
        messages = self._data.get(conversation_id)
        if messages:
            messages.pop()
        if not messages:
            self._data.pop(conversation_id, None)

    def reset(self, conversation_id: str) -> None:
        self._data.pop(conversation_id, None)

    # A conversation can only generate one reply at a time (e.g. two browser tabs).
    def acquire(self, conversation_id: str) -> bool:
        if conversation_id in self._busy:
            return False
        self._busy.add(conversation_id)
        return True

    def release(self, conversation_id: str) -> None:
        self._busy.discard(conversation_id)
