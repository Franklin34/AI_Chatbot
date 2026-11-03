from ..config import Settings
from .base import LLMError, LLMProvider, Message

__all__ = ["LLMError", "LLMProvider", "Message", "build_provider"]


def build_provider(settings: Settings) -> LLMProvider | None:
    """Create the configured provider, or None when credentials are missing.

    SDKs are imported lazily so only the selected provider's dependency is loaded.
    """
    if not settings.configured:
        return None
    model = settings.resolved_model
    if settings.provider == "gemini":
        from .gemini import GeminiProvider

        return GeminiProvider(settings.gemini_api_key, model)
    if settings.provider == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(settings.anthropic_api_key, model)
    from .openai_compat import OpenAICompatProvider

    return OpenAICompatProvider(settings.openai_api_key, model, settings.openai_base_url)
