"""Model access. Any OpenAI-compatible endpoint; the default is an open-weights model served
locally by LM Studio, so learner records never leave the machine."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from langchain_openai import ChatOpenAI

from ..config import get_settings


@dataclass
class Usage:
    """Running totals for one agent run, so the cost of a run is known and reported."""
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    by_step: list[dict] = field(default_factory=list)

    def add(self, step: str, message, seconds: float) -> None:
        meta = getattr(message, "usage_metadata", None) or {}
        self.calls += 1
        self.input_tokens += int(meta.get("input_tokens", 0))
        self.output_tokens += int(meta.get("output_tokens", 0))
        self.seconds += seconds
        self.by_step.append({"step": step, "seconds": round(seconds, 2),
                             "input_tokens": int(meta.get("input_tokens", 0)),
                             "output_tokens": int(meta.get("output_tokens", 0))})

    def as_dict(self) -> dict:
        return {"calls": self.calls, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens, "seconds": round(self.seconds, 1)}


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    cloud: bool
    key_env: str | None = None
    models_url: str | None = None


# `local` is the default and the only one the evaluation results come from: an open-weights model on
# this machine. The two cloud providers are optional, for comparing. With them, documents leave the machine.
PROVIDERS: dict[str, Provider] = {
    "local": Provider("local", "On this computer (open weights)", cloud=False),
    "openai": Provider("openai", "OpenAI (cloud)", cloud=True, key_env="OPENAI_API_KEY",
                       models_url="https://api.openai.com/v1/models"),
    "anthropic": Provider("anthropic", "Claude (cloud)", cloud=True, key_env="ANTHROPIC_API_KEY",
                          models_url="https://api.anthropic.com/v1/models?limit=100"),
}
CLAUDE_FALLBACK = ["claude-fable-5-2", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]
_NOT_CHAT = ("audio", "realtime", "tts", "transcribe", "image", "embedding", "moderation", "search", "instruct", "whisper", "dall-e")

# Keys typed into the teacher app live here, in memory, until the app stops. They are never written to the
# database, the audit log, a run record or a file, and no endpoint returns them.
_session_keys: dict[str, str] = {}


def _cloud(provider: str) -> Provider:
    found = PROVIDERS.get(provider)
    if found is None or not found.cloud:
        raise ValueError(f"Unknown cloud provider '{provider}'. Use one of: openai, anthropic.")
    return found


def set_key(provider: str, key: str) -> None:
    """Keep a provider key for this session only."""
    _cloud(provider)
    key = (key or "").strip()
    if not 20 <= len(key) <= 400 or any(ch.isspace() for ch in key):
        raise ValueError("That does not look like an API key.")
    _session_keys[provider] = key


def forget_key(provider: str) -> None:
    _cloud(provider)
    _session_keys.pop(provider, None)


def _key(provider: str) -> str | None:
    return _session_keys.get(provider) or os.environ.get(PROVIDERS[provider].key_env or "") or None


def key_source(provider: str) -> str | None:
    """Where the key for a cloud provider comes from, without revealing it."""
    if provider in _session_keys:
        return "typed in this session"
    return f"the {PROVIDERS[provider].key_env} environment variable" if _key(provider) else None


def scrub(text: str) -> str:
    """Remove any known key from text before it is stored or shown."""
    for provider in PROVIDERS.values():
        key = _key(provider.id) if provider.cloud else None
        if key:
            text = text.replace(key, "[key hidden]")
    return text


def list_models(provider: str = "local", timeout: float = 3.0) -> list[str]:
    """Chat models a provider offers. For `local` this is what the endpoint serves (LM Studio lists what
    is downloaded). Models that are not for chat are left out. Raises when the provider cannot be reached."""
    import httpx

    if provider == "local":
        settings = get_settings()
        url, headers = f"{settings.llm_base_url.rstrip('/')}/models", {"Authorization": f"Bearer {settings.llm_api_key}"}
    else:
        found, key = _cloud(provider), _key(provider)
        if not key:
            raise RuntimeError(f"No key for {found.label}.")
        url = found.models_url
        headers = ({"x-api-key": key, "anthropic-version": "2023-06-01"} if provider == "anthropic"
                   else {"Authorization": f"Bearer {key}"})
    response = httpx.get(url, timeout=timeout, headers=headers)
    response.raise_for_status()
    ids = [str(item.get("id")) for item in response.json().get("data", []) if item.get("id")]
    if provider == "openai":
        ids = [i for i in ids if i.startswith(("gpt-", "chatgpt-", "o1", "o3", "o4"))]
    return sorted(i for i in ids if not any(word in i.lower() for word in _NOT_CHAT))


def chat_model(which: str = "local", model: str | None = None):
    """The chat model for a run. `local` is the open-weights model. `openai` and `anthropic` are optional
    cloud models and need a key. `frontier` is any other OpenAI-compatible endpoint set in the environment."""
    s = get_settings()
    if which == "frontier":
        if not (s.frontier_base_url and s.frontier_model):
            raise RuntimeError("No frontier model configured (ATHAR_FRONTIER_BASE_URL, ATHAR_FRONTIER_MODEL).")
        return ChatOpenAI(model=model or s.frontier_model, base_url=s.frontier_base_url,
                          api_key=s.frontier_api_key or "none", temperature=0, timeout=300, max_retries=1)
    if which in ("openai", "anthropic"):
        found, key = _cloud(which), _key(which)
        if not key:
            raise RuntimeError(f"No key for {found.label}. Add one on the Agent page, or set {found.key_env}.")
        if not model:
            raise RuntimeError(f"Choose a model for {found.label}.")
        if which == "openai":
            return ChatOpenAI(model=model, api_key=key, timeout=300, max_retries=1)
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, anthropic_api_key=key, max_tokens=4096, default_request_timeout=300, max_retries=1)
    if which != "local":
        raise RuntimeError(f"Unknown model provider '{which}'.")
    # Small local models spend most of their time in "thinking" mode. The agent's tasks are
    # narrow (read a document, pick a tool, word a sentence), so thinking is off by default.
    # Measured on qwen3.5-9b: about 70 s per call with thinking, under 1 s without.
    reasoning = os.environ.get("ATHAR_LLM_REASONING", "none")
    extra = {"reasoning_effort": reasoning} if reasoning != "default" else None
    return ChatOpenAI(model=model or s.llm_model, base_url=s.llm_base_url, api_key=s.llm_api_key,
                      temperature=0, timeout=600, max_retries=1, extra_body=extra)


def structured(llm, schema):
    """A model that must answer in the shape of `schema`. OpenAI-compatible endpoints use their JSON
    schema mode; Claude uses a tool call, which is its own way of doing the same thing."""
    if type(llm).__name__ == "ChatAnthropic":
        return llm.with_structured_output(schema, include_raw=True)
    return llm.with_structured_output(schema, method="json_schema", include_raw=True)


def text_of(message) -> str:
    """The plain text of a model reply. Some providers return a list of parts instead of one string."""
    content = getattr(message, "content", "") or ""
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)


async def timed_invoke(llm, messages, usage: Usage, step: str):
    """Invoke a model and add the call to the run's usage totals."""
    started = time.perf_counter()
    message = await llm.ainvoke(messages)
    usage.add(step, message, time.perf_counter() - started)
    return message
