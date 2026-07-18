"""Central LLM client: one place for client construction, retries, and
profile-driven request shaping (reasoning effort).

Retry policy: transient failures (rate limits, 5xx, timeouts, connection
drops) back off exponentially with jitter for `max_attempts` tries, then
raise LLMError. Non-transient failures (auth, bad request) raise LLMError
immediately — retrying them only burns time.
"""
from __future__ import annotations

import os
import random
import time

import openai
from openai import OpenAI

from yt_distill.core.errors import LLMError, ModelConfigError

TRANSIENT = (
    openai.RateLimitError,
    openai.InternalServerError,
    openai.APITimeoutError,
    openai.APIConnectionError,
)


def make_client(profile) -> OpenAI:
    api_key = os.environ.get(profile.api_key_env)
    if not api_key:
        raise ModelConfigError(
            f"missing API key: set {profile.api_key_env} for profile {profile.name}")
    return OpenAI(base_url=profile.base_url, api_key=api_key)


def chat_completion(profile, *, client=None, max_attempts: int = 3, **create_kwargs):
    client = client or make_client(profile)
    create_kwargs.setdefault("model", profile.model)
    effort = getattr(profile, "reasoning_effort", None)
    if effort:
        extra = dict(create_kwargs.get("extra_body") or {})
        extra["reasoning"] = {"effort": effort}
        create_kwargs["extra_body"] = extra

    last: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return client.chat.completions.create(**create_kwargs)
        except TRANSIENT as exc:
            last = exc
            if attempt == max_attempts:
                break
            delay = (2 ** (attempt - 1)) * (0.5 + random.random())
            print(f"[llm] transient {type(exc).__name__}, retry {attempt}/{max_attempts - 1} in {delay:.1f}s")
            time.sleep(delay)
        except openai.OpenAIError as exc:
            raise LLMError(f"LLM call failed ({type(exc).__name__}): {exc}") from exc
    raise LLMError(
        f"LLM call failed after {max_attempts} attempts ({type(last).__name__}): {last}") from last
