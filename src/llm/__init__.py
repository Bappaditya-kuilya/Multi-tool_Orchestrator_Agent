"""Free-LLM provider layer: stdlib-only OpenAI-compatible + Gemini clients.

Offline default is :class:`MockProvider` (zero API keys); the suite is
network-free — only the pure request builders / parsers / decision tables
are unit-tested here, HTTP send paths are exercised by the Task 22/23 demos.
"""

from src.llm.providers import (
    LLMConfigError,
    LLMHTTPError,
    LLMQuotaError,
    MOCK_PLAN_JSON,
    MockProvider,
    Provider,
    build_gemini_request,
    build_openai_compat_request,
    build_provider,
    chat_gemini_native,
    chat_openai_compat,
    create_provider,
    parse_gemini_response,
    parse_openai_compat_response,
    retry_with_backoff,
)

__all__ = [
    "LLMConfigError",
    "LLMHTTPError",
    "LLMQuotaError",
    "MOCK_PLAN_JSON",
    "MockProvider",
    "Provider",
    "build_gemini_request",
    "build_openai_compat_request",
    "build_provider",
    "chat_gemini_native",
    "chat_openai_compat",
    "create_provider",
    "parse_gemini_response",
    "parse_openai_compat_response",
    "retry_with_backoff",
]
