import json

import pytest

from src.llm import (
    LLMConfigError,
    LLMHTTPError,
    LLMQuotaError,
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


GROQ_PROVIDER = Provider(
    name="groq",
    base_url="https://api.groq.com/openai/v1",
    api_key="test-groq-key",
    model="openai/gpt-oss-120b",
)
OPENROUTER_PROVIDER = Provider(
    name="openrouter",
    base_url="https://openrouter.ai/api/v1",
    api_key="test-openrouter-key",
    model="openrouter/free",
)


# --- provider factory -------------------------------------------------------


def test_factory_selects_by_llm_provider_env(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("GEMINI_API_KEY", "k")

    monkeypatch.setenv("LLM_PROVIDER", "groq")
    assert create_provider().name == "groq"
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    assert create_provider().name == "openrouter"
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    assert create_provider().name == "gemini"
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    assert isinstance(create_provider(), MockProvider)


def test_factory_explicit_arg_wins_over_env(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    assert create_provider(name="mock").name == "mock"


def test_factory_defaults_to_mock_with_no_env(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert isinstance(create_provider(), MockProvider)


def test_factory_unknown_provider_raises_value_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    with pytest.raises(ValueError, match="unknown provider"):
        create_provider()
    with pytest.raises(ValueError, match="unknown provider"):
        create_provider(name="nonsense")


def test_build_provider_missing_key_friendly_error(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(LLMConfigError, match="GROQ_API_KEY"):
        build_provider("groq")
    with pytest.raises(LLMConfigError, match="OPENROUTER_API_KEY"):
        build_provider("openrouter")
    with pytest.raises(LLMConfigError, match="GEMINI_API_KEY"):
        build_provider("gemini")


def test_build_provider_explicit_key_overrides_env(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "env-key")
    p = build_provider("groq", api_key="explicit-key")
    assert p.api_key == "explicit-key"


def test_build_provider_defaults_per_env(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    monkeypatch.setenv("GEMINI_API_KEY", "ge")

    groq = build_provider("groq")
    assert groq.base_url == "https://api.groq.com/openai/v1"
    assert groq.model == "openai/gpt-oss-120b"
    assert groq.api_key == "g"

    router = build_provider("openrouter")
    assert router.base_url == "https://openrouter.ai/api/v1"
    assert router.model == "openrouter/free"
    assert router.api_key == "o"

    gemini = build_provider("gemini")
    assert gemini.base_url == "https://generativelanguage.googleapis.com"
    assert gemini.model == "gemini-3.6-flash"
    assert gemini.api_key == "ge"


def test_build_provider_overrides(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    p = build_provider("groq", model="custom-model", base_url="https://x.example/v1")
    assert p.model == "custom-model"
    assert p.base_url == "https://x.example/v1"


# --- MockProvider -----------------------------------------------------------


def test_mock_provider_returns_canned_plan_json():
    out = MockProvider().chat([{"role": "user", "content": "any request"}])
    plan = json.loads(out)
    assert "steps" in plan
    assert plan["steps"] and all(
        {"id", "capability", "input"} <= set(s) for s in plan["steps"]
    )


# --- openai-compat builder + parser (pure, no HTTP) -------------------------


def test_openai_compat_builder_shape():
    req = build_openai_compat_request(
        GROQ_PROVIDER,
        [{"role": "user", "content": "hi"}],
    )
    assert req["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert req["headers"]["Authorization"] == "Bearer test-groq-key"
    assert req["headers"]["Content-Type"] == "application/json"
    assert req["body"]["model"] == "openai/gpt-oss-120b"
    assert req["body"]["messages"] == [{"role": "user", "content": "hi"}]
    assert req["body"]["temperature"] == 0.2
    assert req["body"]["max_tokens"] == 1024
    assert req["body"]["response_format"] == {"type": "json_object"}


def test_openai_compat_builder_json_mode_off():
    req = build_openai_compat_request(
        OPENROUTER_PROVIDER,
        [{"role": "system", "content": "be brief"}],
        json_mode=False,
    )
    assert "response_format" not in req["body"]
    assert req["url"].startswith("https://openrouter.ai/api/v1")


def test_openai_compat_parse():
    content = '{"steps": []}'
    body = json.dumps({"choices": [{"message": {"content": content}}]})
    assert parse_openai_compat_response(body) == content


def test_openai_compat_parse_bad_json_raises():
    with pytest.raises(ValueError):
        parse_openai_compat_response("not json")


# --- gemini native builder + parser (pure, no HTTP) -------------------------


def test_gemini_builder_roles_and_system():
    req = build_gemini_request(
        key="gem-key",
        model="gemini-3.6-flash",
        messages=[
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
            {"role": "user", "content": "again"},
        ],
        system="you are a planner",
    )
    assert req["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-3.6-flash:generateContent"
    )
    assert req["headers"]["x-goog-api-key"] == "gem-key"
    assert req["headers"]["Content-Type"] == "application/json"
    assert req["body"]["systemInstruction"] == {"parts": [{"text": "you are a planner"}]}
    assert req["body"]["contents"] == [
        {"role": "user", "parts": [{"text": "hello"}]},
        {"role": "model", "parts": [{"text": "hi there"}]},
        {"role": "user", "parts": [{"text": "again"}]},
    ]
    assert req["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert req["body"]["generationConfig"]["temperature"] == 0.2
    assert req["body"]["generationConfig"]["maxOutputTokens"] == 1024


def test_gemini_builder_no_system_omits_instruction():
    req = build_gemini_request(
        key="gem-key", model="gemini-3.6-flash",
        messages=[{"role": "user", "content": "hi"}], system=None,
    )
    assert "systemInstruction" not in req["body"]


def test_gemini_parse():
    body = json.dumps(
        {"candidates": [{"content": {"parts": [{"text": '{"steps": []}'}]}}]}
    )
    assert parse_gemini_response(body) == '{"steps": []}'


def test_gemini_parse_missing_candidate_raises():
    with pytest.raises(ValueError):
        parse_gemini_response(json.dumps({"candidates": []}))


# --- retry_with_backoff -----------------------------------------------------


class _Raises:
    def __init__(self, status, times=1, headers=None):
        self.status = status
        self.remaining = times
        self.headers = headers or {}
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.remaining > 0:
            self.remaining -= 1
            raise LLMHTTPError(self.status, self.headers, f"boom {self.status}")
        return "ok"


class _Sleep:
    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)


def test_retry_success_first_try_no_sleep():
    sleep = _Sleep()
    r = _Raises(200, times=0)
    assert retry_with_backoff(r, sleep=sleep) == "ok"
    assert sleep.calls == []


def test_retry_400_raises_immediately():
    sleep = _Sleep()
    r = _Raises(400)
    with pytest.raises(LLMConfigError):
        retry_with_backoff(r, sleep=sleep)
    assert r.calls == 1
    assert sleep.calls == []


@pytest.mark.parametrize("status", [401, 402, 403])
def test_retry_auth_statuses_raise_immediately(status):
    sleep = _Sleep()
    r = _Raises(status)
    with pytest.raises(LLMConfigError):
        retry_with_backoff(r, sleep=sleep)
    assert r.calls == 1
    assert sleep.calls == []


def test_retry_429_retries_then_success():
    sleep = _Sleep()
    r = _Raises(429, times=2)
    assert retry_with_backoff(r, sleep=sleep) == "ok"
    assert r.calls == 3
    assert len(sleep.calls) == 2


def test_retry_429_exhausted_raises_quota_error():
    sleep = _Sleep()
    r = _Raises(429, times=99)
    with pytest.raises(LLMQuotaError):
        retry_with_backoff(r, sleep=sleep)
    assert r.calls == 3


def test_retry_5xx_retries_then_raises():
    sleep = _Sleep()
    r = _Raises(500, times=99)
    with pytest.raises(LLMHTTPError) as exc:
        retry_with_backoff(r, sleep=sleep)
    assert exc.value.status == 500
    assert r.calls == 3


def test_retry_backoff_math_no_jitter():
    sleep = _Sleep()
    r = _Raises(429, times=99)
    with pytest.raises(LLMQuotaError):
        retry_with_backoff(r, sleep=sleep, base=1.0, random=lambda: 0.0)
    assert sleep.calls == [1.0, 2.0]


def test_retry_backoff_math_honors_base_and_jitter():
    sleep = _Sleep()
    r = _Raises(429, times=99)
    with pytest.raises(LLMQuotaError):
        retry_with_backoff(r, sleep=sleep, base=0.5, random=lambda: 0.25)
    assert sleep.calls == [0.75, 1.25]


def test_retry_honors_retry_after_header():
    sleep = _Sleep()
    r = _Raises(429, times=99, headers={"Retry-After": "7"})
    with pytest.raises(LLMQuotaError):
        retry_with_backoff(r, sleep=sleep, base=1.0, random=lambda: 0.0)
    assert sleep.calls == [7.0, 7.0]


def test_retry_bad_retry_after_falls_back_to_backoff():
    sleep = _Sleep()
    r = _Raises(429, times=99, headers={"Retry-After": "not-a-date"})
    with pytest.raises(LLMQuotaError):
        retry_with_backoff(r, sleep=sleep, base=1.0, random=lambda: 0.0)
    assert sleep.calls == [1.0, 2.0]
