"""The test doubles must fail like the real client, or tests prove nothing about failures."""
import pytest

from screener.llm import LLMError
from tests.support.fakes import FakeLLM, ScriptedLLM


@pytest.mark.parametrize("llm", [FakeLLM(), ScriptedLLM()])
def test_an_exhausted_fake_raises_llm_error_like_the_real_client(llm):
    with pytest.raises(LLMError):
        llm.complete("system", "user")
    with pytest.raises(LLMError):
        llm.complete("system", "user", json_mode=True)


def test_a_queued_exception_is_raised_and_calls_are_recorded():
    llm = FakeLLM("ok", LLMError("429"))
    assert llm.complete("s", "u") == "ok"
    with pytest.raises(LLMError):
        llm.complete("s", "u")
    assert len(llm.calls) == 2
