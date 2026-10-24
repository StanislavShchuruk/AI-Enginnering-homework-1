"""Implement AIProvider to connect a hosted API or a local model."""

import time
from dataclasses import dataclass
from typing import Any, Protocol

from openai import APIConnectionError, APIStatusError, APITimeoutError, DefaultHttpxClient, OpenAI

from ai_project.config import Settings
from ai_project.models import HRSupportTicket


@dataclass(frozen=True)
class GenerationResult:
    text: str
    model: str
    usage: dict[str, int | None] | None = None


class ProviderError(RuntimeError):
    """Safe error for CLI display without credentials or response bodies."""


class AIProvider(Protocol):
    def generate(self, prompt: str, *, system_prompt: str | None = None) -> GenerationResult:
        """Generate a response to a nonempty prompt."""
        ...


class MockProvider:
    """Offline placeholder; does not perform real AI inference."""

    def generate(self, prompt: str, *, system_prompt: str | None = None) -> GenerationResult:
        return GenerationResult(f"[mock] You said: {prompt}", "mock")


class _ChatProvider:
    """Shared SDK request/retry handling; service owns Pydantic validation."""

    name: str
    base_url: str

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.api_key = settings.api_key

    def request_options(self) -> dict[str, Any]:
        return {}

    def client_options(self) -> dict[str, Any]:
        return {}

    def generate(self, prompt: str, *, system_prompt: str | None = None) -> GenerationResult:
        if not system_prompt:
            raise ValueError(f"{self.name} ticket parsing requires a system prompt.")
        with OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.settings.timeout,
            max_retries=0,
            **self.client_options(),
        ) as client:
            for attempt in range(self.settings.max_retries + 1):
                try:
                    response = client.chat.completions.create(
                        model=self.settings.model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=self.settings.temperature,
                        top_p=self.settings.top_p,
                        response_format={
                            "type": "json_schema",
                            "json_schema": {
                                "name": "hr_support_ticket",
                                "strict": True,
                                "schema": HRSupportTicket.model_json_schema(),
                            },
                        },
                        **self.request_options(),
                    )
                    break
                except (APITimeoutError, APIConnectionError, APIStatusError) as exc:
                    status = getattr(exc, "status_code", None)
                    transient = isinstance(exc, (APITimeoutError, APIConnectionError)) or (
                        status == 429 or (status is not None and 500 <= status <= 599)
                    )
                    if transient and attempt < self.settings.max_retries:
                        time.sleep(min(2**attempt, 8))
                        continue
                    kind = f"HTTP {status}" if status is not None else type(exc).__name__
                    hint = (
                        " Check model Structured Outputs support and request parameters."
                        if status == 400
                        else ""
                    )
                    raise ProviderError(
                        f"{self.name} request failed ({kind}) after {attempt + 1} attempt(s).{hint}"
                    ) from exc
        if not response.choices:
            raise ProviderError(f"{self.name} returned no choices.")
        choice = response.choices[0]
        if choice.message.refusal:
            raise ProviderError(f"{self.name} refused the request.")
        if choice.finish_reason != "stop":
            raise ProviderError(f"Incomplete {self.name} response ({choice.finish_reason}).")
        if not choice.message.content:
            raise ProviderError(f"{self.name} returned empty content.")
        usage = None
        if getattr(response, "usage", None) is not None:
            usage = {
                "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
                "completion_tokens": getattr(response.usage, "completion_tokens", None),
                "total_tokens": getattr(response.usage, "total_tokens", None),
            }
        return GenerationResult(choice.message.content, response.model, usage)


class OpenRouterProvider(_ChatProvider):
    name = "OpenRouter"
    base_url = "https://openrouter.ai/api/v1"

    def __init__(self, settings: Settings) -> None:
        if settings.provider == "ollama":
            raise ValueError("Ollama settings cannot be used with OpenRouterProvider.")
        super().__init__(settings)

    def request_options(self) -> dict[str, Any]:
        return {"extra_body": {"provider": {"require_parameters": True}}}


class OllamaProvider(_ChatProvider):
    name = "Ollama"

    def __init__(self, settings: Settings) -> None:
        if settings.provider != "ollama" or not settings.model:
            raise ValueError("Ollama requires Ollama settings and a nonempty model name.")
        super().__init__(settings)
        self.base_url = settings.base_url.rstrip("/")
        if not self.base_url.endswith("/v1"):
            self.base_url += "/v1"
        self.api_key = "ollama"  # SDK placeholder, not a credential; local Ollama ignores it.

    def request_options(self) -> dict[str, Any]:
        return {"reasoning_effort": "none"}

    def client_options(self) -> dict[str, Any]:
        # Do not use environment proxies or follow redirects away from the local server.
        return {"http_client": DefaultHttpxClient(trust_env=False, follow_redirects=False)}


def create_provider(settings: Settings) -> AIProvider:
    if settings.provider == "ollama":
        return OllamaProvider(settings)
    if settings.provider == "openrouter":
        return OpenRouterProvider(settings)
    if settings.provider != "mock":
        raise ValueError(f"Unsupported AI_PROVIDER: {settings.provider!r}")
    return MockProvider()
