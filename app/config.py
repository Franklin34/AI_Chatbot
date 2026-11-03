from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MODELS = {
    "gemini": "gemini-3.8-flash",
    "anthropic": "claude-sonnet-5-5",
    "openai": "gpt-4o-mini",
}


class Settings(BaseSettings):
    """All runtime configuration, loaded from environment variables / `.env`."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    provider: Literal["gemini", "anthropic", "openai"] = "gemini"
    model: str | None = None  # falls back to DEFAULT_MODELS[provider]
    system_prompt: str = (
        "You are a friendly, concise assistant. Answer clearly, use Markdown "
        "when it helps, and ask a clarifying question when a request is ambiguous."
    )
    max_tokens: int = Field(2048, ge=1)
    max_retries: int = Field(3, ge=0, le=6)

    # Conversation handling
    max_history_messages: int = Field(40, ge=2)
    max_message_chars: int = Field(8000, ge=1)
    max_conversations: int = Field(1000, ge=1)

    # Abuse protection (0 disables)
    rate_limit_per_minute: int = Field(30, ge=0)

    # Credentials
    gemini_api_key: str | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = None  # Groq, OpenRouter, Ollama, Azure, ...

    log_level: str = "INFO"

    @property
    def resolved_model(self) -> str:
        return self.model or DEFAULT_MODELS[self.provider]

    @property
    def api_key(self) -> str | None:
        return {
            "gemini": self.gemini_api_key,
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
        }[self.provider]

    @property
    def configured(self) -> bool:
        # A custom OpenAI-compatible endpoint (e.g. local Ollama) may need no key.
        if self.provider == "openai" and self.openai_base_url:
            return True
        return bool(self.api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
