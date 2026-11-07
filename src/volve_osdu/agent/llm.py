"""LLM access: an OpenAI-compatible client behind a disk cache, with a trace of every call.

Provider-agnostic on purpose: LLM_BASE_URL, LLM_API_KEY and LLM_MODEL select any endpoint that
speaks the OpenAI chat-completions protocol (Azure AI Foundry, Gemini, Groq, OpenRouter, Ollama...).
Every response is cached under .cache/llm/<sha256>.json, keyed by model + messages + parameters,
so evaluation re-runs are reproducible and cost nothing.
"""

import hashlib
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from volve_osdu.config import ROOT

logger = logging.getLogger(__name__)
CACHE_DIR = ROOT / ".cache" / "llm"
Messages = list[dict[str, str]]


@dataclass(frozen=True)
class LLMResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float


class ChatBackend(Protocol):
    model: str

    def chat(self, messages: Messages, temperature: float) -> LLMResponse: ...


class OpenAICompatible:
    """Calls /chat/completions on any OpenAI-compatible server."""

    def __init__(self, base_url: str, api_key: str, model: str, json_mode: bool = True) -> None:
        from openai import OpenAI  # imported lazily: tests and the rules system never need it

        self.model = model
        self.json_mode = json_mode
        self._client = OpenAI(base_url=base_url, api_key=api_key, max_retries=5, timeout=120)

    def chat(self, messages: Messages, temperature: float) -> LLMResponse:
        start = time.perf_counter()
        extra: dict[str, Any] = (
            {"response_format": {"type": "json_object"}} if self.json_mode else {}
        )
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            **extra,
        )
        usage = response.usage
        return LLMResponse(
            text=response.choices[0].message.content or "",
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            latency_s=round(time.perf_counter() - start, 3),
        )


class FakeBackend:
    """Deterministic stand-in for tests: `respond(messages)` returns the reply text."""

    def __init__(self, respond: Callable[[Messages], str], model: str = "fake") -> None:
        self.model = model
        self.respond = respond
        self.calls = 0

    def chat(self, messages: Messages, temperature: float) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            self.respond(messages), prompt_tokens=0, completion_tokens=0, latency_s=0.0
        )


@dataclass
class CachedLLM:
    """The only way agent code talks to a model. Records one trace entry per call."""

    backend: ChatBackend
    cache_dir: Path = CACHE_DIR
    temperature: float = 0.0
    trace: list[dict[str, Any]] = field(default_factory=list)
    api_calls: int = 0

    @property
    def model(self) -> str:
        return self.backend.model

    def key(self, messages: Messages) -> str:
        payload = {"model": self.model, "messages": messages, "temperature": self.temperature}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def complete(self, messages: Messages, *, node: str, prompt_version: str) -> str:
        key = self.key(messages)
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            cached = json.loads(path.read_text(encoding="utf-8"))
            response = LLMResponse(**cached["response"])
            hit = True
        else:
            response = self.backend.chat(messages, self.temperature)
            self.api_calls += 1
            hit = False
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            tmp.write_text(
                json.dumps(
                    {"model": self.model, "messages": messages, "response": response.__dict__},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            tmp.replace(path)  # atomic: a crash never leaves a half-written cache entry
        self.trace.append(
            {
                "node": node,
                "model": self.model,
                "prompt_version": prompt_version,
                "cache_key": key,
                "cached": hit,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "latency_s": 0.0 if hit else response.latency_s,
            }
        )
        return response.text


def from_env() -> CachedLLM:
    """Build the client from LLM_BASE_URL / LLM_API_KEY / LLM_MODEL (see .env.example)."""
    _load_dotenv(ROOT / ".env")
    missing = [v for v in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL") if not os.environ.get(v)]
    if missing:
        raise RuntimeError(f"set {', '.join(missing)} in .env (see .env.example)")
    backend = OpenAICompatible(
        base_url=os.environ["LLM_BASE_URL"],
        api_key=os.environ["LLM_API_KEY"],
        model=os.environ["LLM_MODEL"],
        json_mode=os.environ.get("LLM_JSON_MODE", "true").lower() != "false",
    )
    return CachedLLM(backend)


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader (KEY=VALUE lines). Real environment variables take precedence."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
