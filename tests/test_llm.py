"""Central LLM client: retry policy + reasoning_effort wiring."""
import pytest

import openai
import httpx

from yt_distill.core import llm
from yt_distill.core.errors import LLMError
from yt_distill.core.models import resolve


def _fake_request():
    return httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")


def _rate_limit():
    return openai.RateLimitError(
        "429", response=httpx.Response(429, request=_fake_request()), body=None)


class FlakyClient:
    """Fails n times with the given error, then returns a sentinel."""
    def __init__(self, fails, error_factory):
        self.calls = 0
        self._fails, self._factory = fails, error_factory
        self.kwargs = None
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.kwargs = kwargs
        self.calls += 1
        if self.calls <= self._fails:
            raise self._factory()
        return {"ok": True}


@pytest.fixture(autouse=True)
def _no_sleep(mocker):
    mocker.patch("yt_distill.core.llm.time.sleep")


def test_transient_error_retried_then_succeeds():
    c = FlakyClient(fails=2, error_factory=_rate_limit)
    prof = resolve("gemini-3.5-flash")
    out = llm.chat_completion(prof, client=c, messages=[])
    assert out == {"ok": True}
    assert c.calls == 3


def test_attempts_exhausted_raises_llmerror():
    c = FlakyClient(fails=5, error_factory=_rate_limit)
    prof = resolve("gemini-3.5-flash")
    with pytest.raises(LLMError):
        llm.chat_completion(prof, client=c, messages=[])
    assert c.calls == 3  # default max_attempts


def test_non_transient_raises_immediately():
    def auth_err():
        return openai.AuthenticationError(
            "401", response=httpx.Response(401, request=_fake_request()), body=None)
    c = FlakyClient(fails=5, error_factory=auth_err)
    prof = resolve("gemini-3.5-flash")
    with pytest.raises(LLMError):
        llm.chat_completion(prof, client=c, messages=[])
    assert c.calls == 1


def test_reasoning_effort_wired_into_extra_body():
    c = FlakyClient(fails=0, error_factory=_rate_limit)
    prof = resolve("gemini-3.5-flash-high")
    llm.chat_completion(prof, client=c, messages=[])
    assert c.kwargs["extra_body"]["reasoning"] == {"effort": "high"}
    assert c.kwargs["model"] == prof.model


def test_no_reasoning_effort_no_extra_body_key():
    c = FlakyClient(fails=0, error_factory=_rate_limit)
    prof = resolve("gemini-3.5-flash")
    llm.chat_completion(prof, client=c, messages=[])
    assert "reasoning" not in (c.kwargs.get("extra_body") or {})
