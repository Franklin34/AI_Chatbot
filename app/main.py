import asyncio
import json
import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Settings, get_settings
from .providers import LLMError, LLMProvider, build_provider
from .ratelimit import RateLimiter
from .service import stream_with_retry
from .store import ConversationStore

STATIC_DIR = Path(__file__).parent / "static"
log = logging.getLogger("chatbot")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]{1,64}$")


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def create_app(settings: Settings | None = None, provider: LLMProvider | None = None) -> FastAPI:
    """App factory: dependencies are injectable so tests can run without a real LLM."""
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    provider = provider or build_provider(settings)
    store = ConversationStore(settings.max_conversations)
    limiter = RateLimiter(settings.rate_limit_per_minute)

    app = FastAPI(title="AI Chatbot", version="0.2.0")

    if provider is None:
        log.warning("No credentials for provider '%s'; chat is disabled.", settings.provider)
    else:
        log.info("Using %s / %s", provider.name, provider.model)

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok" if provider else "unconfigured",
            "provider": settings.provider,
            "model": settings.resolved_model,
        }

    @app.post("/api/chat")
    async def chat(req: ChatRequest, request: Request):
        client = request.client.host if request.client else "unknown"
        if not limiter.allow(client):
            raise HTTPException(429, "Too many requests. Please slow down.")
        if not req.message.strip():
            raise HTTPException(422, "Message cannot be empty.")
        if len(req.message) > settings.max_message_chars:
            raise HTTPException(
                413, f"Message too long (max {settings.max_message_chars} characters)."
            )

        conversation_id = req.conversation_id or str(uuid.uuid4())
        generator = _reply_stream(conversation_id, req.message)
        return StreamingResponse(
            generator,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def _reply_stream(conversation_id: str, message: str):
        if provider is None:
            key = f"{settings.provider.upper()}_API_KEY"
            yield sse("error", {"message": f"{key} is not set. Add it to .env and restart."})
            return
        if not store.acquire(conversation_id):
            yield sse("error", {"message": "This conversation is already generating a reply."})
            return

        store.append(conversation_id, "user", message)
        chunks: list[str] = []
        committed = False
        started = time.perf_counter()
        try:
            yield sse("start", {"conversation_id": conversation_id})
            history = store.window(conversation_id, settings.max_history_messages)
            async for chunk in stream_with_retry(
                provider,
                history,
                settings.system_prompt,
                settings.max_tokens,
                settings.max_retries,
            ):
                chunks.append(chunk)
                yield sse("token", {"text": chunk})

            reply = "".join(chunks)
            if not reply.strip():
                raise LLMError("The model returned an empty response. Please try again.")
            store.append(conversation_id, "assistant", reply)
            committed = True
            log.info(
                "reply conv=%s model=%s chars=%d latency=%.2fs",
                conversation_id[:8],
                provider.model,
                len(reply),
                time.perf_counter() - started,
            )
            yield sse("done", {})
        except LLMError as e:
            log.warning("llm error conv=%s: %s", conversation_id[:8], e.message)
            store.pop_last(conversation_id)  # drop the unanswered user turn
            yield sse("error", {"message": e.message})
        except (asyncio.CancelledError, GeneratorExit):
            # Client pressed "Stop" or disconnected: keep what was generated so
            # far so the history stays consistent with what the user saw.
            partial = "".join(chunks)
            if committed:
                pass
            elif partial.strip():
                store.append(conversation_id, "assistant", partial)
            else:
                store.pop_last(conversation_id)
            raise
        except Exception:
            log.exception("unexpected error conv=%s", conversation_id[:8])
            store.pop_last(conversation_id)
            yield sse("error", {"message": "Unexpected server error."})
        finally:
            store.release(conversation_id)

    @app.post("/api/reset/{conversation_id}")
    async def reset(conversation_id: str):
        store.reset(conversation_id)
        return {"ok": True}

    @app.get("/api/history/{conversation_id}")
    async def history(conversation_id: str):
        messages = store.get(conversation_id)
        if messages is None:
            raise HTTPException(404, "Conversation not found")
        return {"messages": messages}

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
