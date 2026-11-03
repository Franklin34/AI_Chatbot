from fastapi.testclient import TestClient

from app.main import create_app
from app.providers import LLMError

from .conftest import FakeProvider, make_settings, parse_sse


def chat(client, message, conversation_id=None):
    res = client.post("/api/chat", json={"message": message, "conversation_id": conversation_id})
    return res, parse_sse(res.text) if res.status_code == 200 else []


def test_health(client):
    body = client.get("/api/health").json()
    assert body == {"status": "ok", "provider": "gemini", "model": "gemini-3.8-flash"}


def test_streams_tokens_then_done(client):
    _, events = chat(client, "hi")
    kinds = [e for e, _ in events]
    assert kinds[0] == "start" and kinds[-1] == "done"
    assert "".join(d["text"] for e, d in events if e == "token") == "echo: hi"


def test_conversation_context_is_sent_to_the_model(client, provider):
    _, events = chat(client, "first")
    conv = events[0][1]["conversation_id"]
    chat(client, "second", conv)

    second_call_messages, _ = provider.calls[1]
    assert [m["content"] for m in second_call_messages] == ["first", "echo: first", "second"]


def test_system_prompt_is_passed(provider):
    client = TestClient(create_app(make_settings(system_prompt="Be a pirate."), provider))
    chat(client, "hi")
    assert provider.calls[0][1] == "Be a pirate."


def test_reset_clears_history(client):
    _, events = chat(client, "hi")
    conv = events[0][1]["conversation_id"]
    assert client.get(f"/api/history/{conv}").status_code == 200

    client.post(f"/api/reset/{conv}")
    assert client.get(f"/api/history/{conv}").status_code == 404


def test_llm_error_is_reported_and_history_stays_clean():
    async def failing(call_number, messages):
        raise LLMError("boom")
        yield  # pragma: no cover

    client = TestClient(create_app(make_settings(), FakeProvider(failing)))
    _, events = chat(client, "hi", "conv-1")

    assert events[-1] == ("error", {"message": "boom"})
    assert client.get("/api/history/conv-1").status_code == 404


def test_empty_model_reply_is_an_error():
    async def silent(call_number, messages):
        return
        yield  # pragma: no cover

    client = TestClient(create_app(make_settings(), FakeProvider(silent)))
    _, events = chat(client, "hi")
    assert events[-1][0] == "error"


def test_history_is_trimmed_to_the_configured_window(provider):
    client = TestClient(create_app(make_settings(max_history_messages=2), provider))
    conv = "conv-trim"
    for text in ("a", "b", "c"):
        chat(client, text, conv)

    sent, _ = provider.calls[-1]
    assert [m["content"] for m in sent] == ["c"]  # window of 2 starts on a user turn


def test_missing_api_key_gives_actionable_error(provider):
    client = TestClient(create_app(make_settings(gemini_api_key=None)))
    _, events = chat(client, "hi")
    assert events == [
        ("error", {"message": "GEMINI_API_KEY is not set. Add it to .env and restart."})
    ]
    assert client.get("/api/health").json()["status"] == "unconfigured"


def test_input_validation(client):
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
    assert client.post("/api/chat", json={"message": "   "}).status_code == 422
    assert (
        client.post("/api/chat", json={"message": "x", "conversation_id": "../etc"}).status_code
        == 422
    )

    small = TestClient(create_app(make_settings(max_message_chars=5), FakeProvider()))
    assert small.post("/api/chat", json={"message": "too long"}).status_code == 413


def test_rate_limit(provider):
    client = TestClient(create_app(make_settings(rate_limit_per_minute=2), provider))
    codes = [client.post("/api/chat", json={"message": "hi"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
