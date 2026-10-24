"""Application settings loaded from environment variables."""

import ipaddress
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    provider: str = "mock"
    model: str = "demo"
    api_key: str = field(default="", repr=False)
    temperature: float = 0.0
    top_p: float = 1.0
    timeout: float = 30.0
    max_retries: int = 2
    base_url: str = "http://localhost:11434"

    def __post_init__(self) -> None:
        if not math.isfinite(self.temperature) or not 0 <= self.temperature <= 2:
            raise ValueError("Temperature must be between 0 and 2.")
        if not math.isfinite(self.top_p) or not 0 < self.top_p <= 1:
            raise ValueError("top_p must be greater than 0 and at most 1.")
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("Timeout must be positive and finite.")
        if not 0 <= self.max_retries <= 5:
            raise ValueError("Retries must be between 0 and 5.")
        if self.provider == "ollama":
            url = urlsplit(self.base_url)
            host = url.hostname or ""
            try:
                local = host == "localhost" or ipaddress.ip_address(host).is_loopback
            except ValueError:
                local = False
            if (
                not local
                or url.scheme not in {"http", "https"}
                or url.username
                or url.password
                or url.query
                or url.fragment
                or url.path.rstrip("/") not in {"", "/v1"}
            ):
                raise ValueError("OLLAMA_BASE_URL must be a loopback HTTP(S) URL, optionally /v1.")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            provider=os.getenv("AI_PROVIDER", "mock"),
            model=os.getenv("AI_MODEL", "demo"),
        )

    @classmethod
    def openrouter_from_env(cls) -> "Settings":
        load_dotenv(Path.cwd() / ".env")
        key = os.getenv("OPENROUTER_API_KEY", "").strip()
        model = os.getenv("OPENROUTER_MODEL", "").strip()
        if not key or not model:
            raise ValueError("Set OPENROUTER_API_KEY and OPENROUTER_MODEL.")
        try:
            temperature = float(os.getenv("OPENROUTER_TEMPERATURE", "0"))
            top_p = float(os.getenv("OPENROUTER_TOP_P", "1"))
            timeout = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "30"))
            retries = int(os.getenv("OPENROUTER_MAX_RETRIES", "2"))
        except ValueError:
            raise ValueError("OpenRouter numeric settings must contain valid numbers.") from None
        return cls("openrouter", model, key, temperature, top_p, timeout, retries)

    @classmethod
    def ollama_from_env(cls) -> "Settings":
        load_dotenv(Path.cwd() / ".env")
        try:
            temperature = float(os.getenv("OLLAMA_TEMPERATURE", "0"))
            top_p = float(os.getenv("OLLAMA_TOP_P", "1"))
            timeout = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
        except ValueError:
            raise ValueError("Ollama numeric settings must contain valid numbers.") from None
        return cls(
            provider="ollama",
            model=os.getenv("OLLAMA_MODEL", "qwen3:8b").strip(),
            temperature=temperature,
            top_p=top_p,
            timeout=timeout,
            max_retries=0,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip(),
        )
