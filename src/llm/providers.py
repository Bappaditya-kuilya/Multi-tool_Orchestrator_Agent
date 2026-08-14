"""LLM provider abstraction — stdlib only.

# ponytail: stdlib client — swap to httpx only if streaming/SSE becomes a requirement

Covers Groq / OpenRouter / Mistral / Cerebras through one OpenAI-compatible
code path, plus Gemini's native REST API.  The suite stays network-free: the
pure request builders, response parsers, and the retry decision table are
unit-tested directly; the HTTP send itself is left untested (Task 22/23 demos
exercise it live).
"""

from __future__ import annotations

import json
import os
import random as _random
import time as _time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Optional


class LLMConfigError(Exception):
    """Unrecoverable configuration problem (missing/invalid key, bad request)."""


class LLMQuotaError(Exception):
    """Rate limit or quota exhausted after retries."""


class LLMHTTPError(Exception):
    """Server-side failure (429 or 5xx) raised after retries are exhausted."""

    def __init__(self, status: int, headers: dict[str, str], message: str = ""):
        self.status = status
        self.headers = headers
        self.message = message
        super().__init__(f"HTTP {status}: {message}")


PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "env_key": "GROQ_API_KEY",
        "model": "openai/gpt-oss-120b",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "env_key": "OPENROUTER_API_KEY",
        "model": "openrouter/free",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com",
        "env_key": "GEMINI_API_KEY",
        "model": "gemini-3.6-flash",
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "env_key": "MISTRAL_API_KEY",
        "model": "open-mistral-nemo",
    },
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "env_key": "CEREBRAS_API_KEY",
        "model": "llama-3.3-70b",
    },
}

OPENAI_COMPAT_TIMEOUT_S = 30
GEMINI_TIMEOUT_S = 30


@dataclass
class Provider:
    name: str
    base_url: str
    api_key: str
    model: str


def build_provider(
    name: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Provider:
    """Build a :class:`Provider` with env-driven defaults per provider."""
    if name not in PROVIDER_DEFAULTS:
        raise ValueError(f"unknown provider: {name!r} (expected one of {sorted(PROVIDER_DEFAULTS)})")
    defaults = PROVIDER_DEFAULTS[name]
    if api_key is None:
        api_key = os.environ.get(defaults["env_key"])
    if not api_key:
        raise LLMConfigError(
            f"missing API key for provider {name!r}: set {defaults['env_key']} "
            f"or pass api_key= explicitly (or use LLM_PROVIDER=mock for the offline default)"
        )
    return Provider(
        name=name,
        base_url=base_url or defaults["base_url"],
        api_key=api_key,
        model=model or defaults["model"],
    )


MOCK_PLAN_JSON: str = json.dumps(
    {
        "steps": [
            {"id": "s1", "capability": "calculator", "input": {"expression": "1+1"}},
            {"id": "s2", "capability": "weather", "input": {"location": "London"}},
        ]
    }
)


class MockProvider:
    """Offline provider: returns a canned, schema-shaped plan JSON. No network."""

    name = "mock"

    def __init__(self):
        self.base_url = ""
        self.api_key = ""
        self.model = "mock-plan"

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        return MOCK_PLAN_JSON


def create_provider(
    name: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Provider | MockProvider:
    """Provider factory: explicit arg wins over the ``LLM_PROVIDER`` env var.

    Defaults to :class:`MockProvider` when neither is set — the agent must
    work with zero API keys.
    """
    if name is None:
        name = os.environ.get("LLM_PROVIDER", "mock")
    if name == "mock":
        return MockProvider()
    return build_provider(name, api_key=api_key, model=model, base_url=base_url)


# --- OpenAI-compatible path (Groq / OpenRouter / Mistral / Cerebras) --------


def build_openai_compat_request(
    cfg: Provider, messages: list[dict[str, str]], *, json_mode: bool = True
) -> dict[str, Any]:
    """Pure request-builder for POST {base}/chat/completions (unit-tested)."""
    body: dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1024,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    return {
        "url": f"{cfg.base_url.rstrip('/')}/chat/completions",
        "headers": {
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        },
        "body": body,
    }


def parse_openai_compat_response(body: str) -> str:
    """Pure response-parser: json body -> choices[0].message.content."""
    data = json.loads(body)
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"unexpected OpenAI-compatible response shape: {exc}") from exc


def chat_openai_compat(cfg: Provider, messages: list[dict[str, str]], *, json_mode: bool = True) -> str:
    """POST an OpenAI-compatible chat completion and return the content string."""

    def _send() -> str:
        req = build_openai_compat_request(cfg, messages, json_mode=json_mode)
        request = urllib.request.Request(
            req["url"], data=json.dumps(req["body"]).encode(), headers=req["headers"], method="POST"
        )
        with urllib.request.urlopen(request, timeout=OPENAI_COMPAT_TIMEOUT_S) as resp:
            return parse_openai_compat_response(resp.read().decode())

    return retry_with_backoff(_send, sleep=_time.sleep)


# --- Gemini native ----------------------------------------------------------


def build_gemini_request(
    key: str, model: str, messages: list[dict[str, str]], system: Optional[str] = None
) -> dict[str, Any]:
    """Pure request-builder for POST models/{model}:generateContent (unit-tested)."""
    contents = []
    for msg in messages:
        role = msg.get("role", "user")
        contents.append({"role": "model" if role == "assistant" else "user", "parts": [{"text": msg["content"]}]})
    body: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2,
            "maxOutputTokens": 1024,
        },
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    return {
        "url": f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "headers": {"x-goog-api-key": key, "Content-Type": "application/json"},
        "body": body,
    }


def parse_gemini_response(body: str) -> str:
    """Pure response-parser: json body -> candidates[0].content.parts[0].text."""
    data = json.loads(body)
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"unexpected Gemini response shape: {exc}") from exc


def chat_gemini_native(
    key: str, model: str, messages: list[dict[str, str]], system: Optional[str] = None
) -> str:
    """POST a Gemini generateContent request and return the content string."""

    def _send() -> str:
        req = build_gemini_request(key, model, messages, system=system)
        request = urllib.request.Request(
            req["url"], data=json.dumps(req["body"]).encode(), headers=req["headers"], method="POST"
        )
        with urllib.request.urlopen(request, timeout=GEMINI_TIMEOUT_S) as resp:
            return parse_gemini_response(resp.read().decode())

    return retry_with_backoff(_send, sleep=_time.sleep)


# --- retry policy -----------------------------------------------------------

_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
_INSTANT_FAIL_STATUSES = frozenset({400, 401, 402, 403})


def retry_with_backoff(
    fn: Callable[[], Any],
    *,
    attempts: int = 3,
    base: float = 1.0,
    sleep: Callable[[float], Any] = _time.sleep,
    random: Callable[[], float] = _random.random,
) -> Any:
    """Run ``fn`` with retries: 429/5xx retry up to ``attempts``, 4xx raise now.

    Retry delay honors a ``Retry-After`` header (seconds) when the error
    carries one, else ``base * 2**attempt + jitter``.  ``sleep``/``random``
    are injectable so the backoff math is unit-testable with no real waiting.
    """
    last_error: Optional[LLMHTTPError] = None
    for attempt in range(attempts):
        try:
            return fn()
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read().decode(errors="replace")
            error = LLMHTTPError(status, dict(exc.headers or {}), body)
            last_error = _decide(status, error, attempt, base, sleep, random, attempts)
        except LLMHTTPError as exc:
            last_error = _decide(exc.status, exc, attempt, base, sleep, random, attempts)
    raise last_error  # type: ignore[misc]


def _decide(
    status: int,
    error: LLMHTTPError,
    attempt: int,
    base: float,
    sleep: Callable[[float], Any],
    random: Callable[[], float],
    attempts: int,
) -> LLMHTTPError:
    if status in _INSTANT_FAIL_STATUSES:
        raise _friendly_config_error(status)
    if status == 429:
        if attempt == attempts - 1:
            raise LLMQuotaError(
                f"rate limit exceeded after {attempts} attempts (HTTP 429); "
                "retry later or switch provider (LLM_PROVIDER=mock for offline)"
            )
        sleep(_retry_delay(error.headers, base, attempt, random))
    elif status in _RETRYABLE_STATUSES:
        if attempt == attempts - 1:
            raise error
        sleep(_retry_delay(error.headers, base, attempt, random))
    else:
        raise LLMHTTPError(status, error.headers, error.message)
    return error


def _friendly_config_error(status: int) -> LLMConfigError:
    if status in (401, 403):
        return LLMConfigError("API key rejected (HTTP 401/403): check the key is valid and not revoked")
    if status == 402:
        return LLMConfigError("payment required (HTTP 402): this provider needs billing enabled")
    return LLMConfigError(
        "bad request (HTTP 400): check the model name, message roles, and payload shape"
    )


def _retry_delay(
    headers: dict[str, str], base: float, attempt: int, random: Callable[[], float]
) -> float:
    retry_after = headers.get("Retry-After") or headers.get("retry-after")
    if retry_after is not None:
        try:
            return float(retry_after)
        except (TypeError, ValueError):
            pass  # unparseable (e.g. an HTTP-date): fall back to backoff math
    return base * 2**attempt + random()
