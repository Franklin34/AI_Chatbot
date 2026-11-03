import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


class FakeProvider:
    """Deterministic stand-in for an LLM. `handler(call_number, messages)` yields chunks."""

    name = "fake"
    model = "fake-1"

    def __init__(self, handler=None):
        self.calls: list[tuple[list[dict], str]] = []
        self._handler = handler or self._echo

    @staticmethod
    async def _echo(call_number, messages):
        yield "echo: "
        yield messages[-1]["content"]

    async def stream(self, messages, system, max_tokens):
        self.calls.append(([dict(m) for m in messages], system))
        async for chunk in self._handler(len(self.calls), messages):
            yield chunk


def make_settings(**overrides) -> Settings:
    # _env_file=None keeps tests independent from the developer's real .env
    base = {"gemini_api_key": "test", "max_retries": 0, "rate_limit_per_minute": 0}
    return Settings(_env_file=None, **{**base, **overrides})


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for frame in filter(None, body.strip().split("\n\n")):
        event = next(x[7:] for x in frame.splitlines() if x.startswith("event: "))
        data = next(x[6:] for x in frame.splitlines() if x.startswith("data: "))
        events.append((event, json.loads(data)))
    return events


@pytest.fixture
def provider():
    return FakeProvider()


@pytest.fixture
def client(provider):
    return TestClient(create_app(make_settings(), provider))
