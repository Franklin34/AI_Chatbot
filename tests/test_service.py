import asyncio

import pytest

from app.providers import LLMError
from app.service import stream_with_retry
from app.store import ConversationStore

from .conftest import FakeProvider


def collect(provider, max_retries=3):
    async def run():
        return [
            c
            async for c in stream_with_retry(
                provider, [{"role": "user", "content": "x"}], "sys", 100, max_retries, base_delay=0
            )
        ]

    return asyncio.run(run())


def test_retries_transient_errors_then_succeeds():
    async def flaky(call_number, messages):
        if call_number < 3:
            raise LLMError("busy", retryable=True)
        yield "ok"

    provider = FakeProvider(flaky)
    assert collect(provider) == ["ok"]
    assert len(provider.calls) == 3


def test_gives_up_after_max_retries():
    async def always_busy(call_number, messages):
        raise LLMError("busy", retryable=True)
        yield  # pragma: no cover

    provider = FakeProvider(always_busy)
    with pytest.raises(LLMError):
        collect(provider, max_retries=2)
    assert len(provider.calls) == 3  # first try + 2 retries


def test_non_retryable_errors_fail_immediately():
    async def bad_key(call_number, messages):
        raise LLMError("bad key")
        yield  # pragma: no cover

    provider = FakeProvider(bad_key)
    with pytest.raises(LLMError):
        collect(provider)
    assert len(provider.calls) == 1


def test_never_retries_after_output_has_started():
    async def dies_midway(call_number, messages):
        yield "partial"
        raise LLMError("busy", retryable=True)

    provider = FakeProvider(dies_midway)
    with pytest.raises(LLMError):
        collect(provider)
    assert len(provider.calls) == 1


def test_store_window_always_starts_with_a_user_turn():
    store = ConversationStore()
    for role, text in [("user", "1"), ("assistant", "2"), ("user", "3"), ("assistant", "4")]:
        store.append("c", role, text)
    assert [m["content"] for m in store.window("c", 3)] == ["3", "4"]


def test_store_evicts_least_recently_used_conversation():
    store = ConversationStore(max_conversations=2)
    store.append("a", "user", "1")
    store.append("b", "user", "1")
    store.append("a", "assistant", "2")  # touch "a"
    store.append("c", "user", "1")
    assert store.get("b") is None and store.get("a") is not None


def test_store_blocks_concurrent_replies_per_conversation():
    store = ConversationStore()
    assert store.acquire("a") is True
    assert store.acquire("a") is False
    store.release("a")
    assert store.acquire("a") is True
