from types import SimpleNamespace

import httpx
import openai
import pytest

from tests.support.tables import table

from screener.llm import LLMError
from screener.gemini import GeminiClient, from_env


class FakeSDK:
    def __init__(self, content="hola", error=None):
        self.calls = []
        self._content, self._error = content, error
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        message = SimpleNamespace(content=self._content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def client(sdk):
    return GeminiClient(model="test-model", sdk=sdk)


def test_plain_completion_sends_system_and_user_messages():
    sdk = FakeSDK("¿Cómo te llamas?")
    assert client(sdk).complete("be brief", "ask name") == "¿Cómo te llamas?"
    call = sdk.calls[0]
    assert call["model"] == "test-model"
    assert call["messages"] == [{"role": "system", "content": "be brief"}, {"role": "user", "content": "ask name"}]
    assert "response_format" not in call


def test_json_mode_requests_a_json_object():
    sdk = FakeSDK("{}")
    client(sdk).complete("s", "u", json_mode=True)
    assert sdk.calls[0]["response_format"] == {"type": "json_object"}


@table("error", [
    openai.APIConnectionError(request=httpx.Request("POST", "http://x")),
    openai.APITimeoutError(request=httpx.Request("POST", "http://x")),
    openai.RateLimitError("429", response=httpx.Response(429, request=httpx.Request("POST", "http://x")), body=None),
    openai.NotFoundError("no such model", response=httpx.Response(404, request=httpx.Request("POST", "http://x")), body=None),
])
def test_sdk_failures_become_llm_errors(error):
    with pytest.raises(LLMError):
        client(FakeSDK(error=error)).complete("s", "u")


@table("content", [None, ""])
def test_an_empty_answer_is_an_llm_error(content):
    with pytest.raises(LLMError):
        client(FakeSDK(content=content)).complete("s", "u")


def test_a_missing_api_key_gives_a_clear_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        from_env(load_dotenv_file=False)


def test_the_model_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("LLM_MODEL", "my-model")
    assert from_env(load_dotenv_file=False).model == "my-model"


def test_a_response_without_choices_is_an_llm_error():
    sdk = FakeSDK()
    sdk.chat.completions.create = lambda **kw: SimpleNamespace(choices=[])
    with pytest.raises(LLMError):
        client(sdk).complete("s", "u")


def test_the_default_model_is_the_lite_one_that_fits_the_free_tier(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert from_env(load_dotenv_file=False).model == "gemini-3.5-flash-lite"
