"""Local-provider tests use dummy responses and synthetic project files only."""

import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError
from pydantic import ValidationError

from ai_project.cli import main
from ai_project.config import Settings
from ai_project.models import HRSupportTicket
from ai_project.providers import OllamaProvider, OpenRouterProvider, ProviderError, create_provider
from ai_project.service import AIService


def content() -> str:
    return json.dumps(
        {
            "summary": "Login issue",
            "category": "authentication",
            "priority": "medium",
            "application": None,
            "language": "en",
            "requires_support": True,
            "details": {"error_code": None, "error_message": None},
            "suggested_actions": [],
        }
    )


@pytest.fixture
def sdk() -> Iterator[MagicMock]:
    with (
        patch("ai_project.providers.OpenAI") as constructor,
        patch("ai_project.providers.DefaultHttpxClient"),
    ):
        constructor.return_value.__enter__.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason="stop",
                        message=SimpleNamespace(
                            content=content(), refusal=None, reasoning_content="private reasoning"
                        ),
                    )
                ],
                model="qwen3:8b-actual",
                usage=SimpleNamespace(prompt_tokens=20),
            )
        )
        yield constructor


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    (tmp_path / "prompts").mkdir()
    (tmp_path / "data/tickets.json").write_text(
        json.dumps([{"id": index, "text": "Cannot log in"} for index in range(1, 31)]),
        encoding="utf-8",
    )
    (tmp_path / "prompts/v1.txt").write_text("system v1", encoding="utf-8")
    return tmp_path


def test_defaults_do_not_load_secrets() -> None:
    with patch.dict("os.environ", {}, clear=True), patch("ai_project.config.load_dotenv") as loader:
        settings = Settings.ollama_from_env()
    loader.assert_not_called()
    assert settings.provider == "ollama" and settings.model == "qwen3:8b"
    assert settings.timeout == 120 and settings.temperature == 0 and settings.top_p == 1
    assert settings.base_url == "http://localhost:11434" and settings.api_key == ""


def test_custom_environment() -> None:
    with patch.dict(
        "os.environ",
        {
            "OLLAMA_BASE_URL": "http://127.0.0.1:12345/v1/",
            "OLLAMA_MODEL": "custom",
            "OLLAMA_TEMPERATURE": "0.3",
            "OLLAMA_TOP_P": "0.9",
            "OLLAMA_TIMEOUT_SECONDS": "60",
        },
        clear=True,
    ):
        settings = Settings.ollama_from_env()
    assert settings.temperature == 0.3 and settings.top_p == 0.9 and settings.timeout == 60
    assert settings.model == "custom"


@pytest.mark.parametrize(
    "url",
    [
        "https://openrouter.ai/api/v1",
        "http://example.com",
        "http://user:password@localhost:11434",
        "http://localhost:11434/api",
        "file:///tmp",
    ],
)
def test_nonlocal_or_invalid_endpoint_rejected(url: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        Settings(provider="ollama", base_url=url)


def test_request_schema_thinking_usage_and_endpoint(sdk: MagicMock, project: Path) -> None:
    settings = Settings(provider="ollama", model="qwen3:8b", timeout=120)
    result = AIService(create_provider(settings)).parse_ticket(1, project)
    assert result.ticket.summary == "Login issue"
    assert result.model == "qwen3:8b-actual"
    assert result.usage == {"prompt_tokens": 20, "completion_tokens": None, "total_tokens": None}
    assert result.elapsed_seconds >= 0
    kwargs = sdk.call_args.kwargs
    assert kwargs["base_url"] == "http://localhost:11434/v1"
    assert kwargs["api_key"] == "ollama" and kwargs["timeout"] == 120
    request = sdk.return_value.__enter__.return_value.chat.completions.create.call_args.kwargs
    assert request["reasoning_effort"] == "none"
    assert "extra_body" not in request
    assert request["messages"] == [
        {"role": "system", "content": "system v1"},
        {"role": "user", "content": "Cannot log in"},
    ]
    assert (
        request["response_format"]["json_schema"]["schema"] == HRSupportTicket.model_json_schema()
    )
    assert request["response_format"]["json_schema"]["strict"] is True


def test_missing_usage(sdk: MagicMock) -> None:
    response = sdk.return_value.__enter__.return_value.chat.completions.create.return_value
    del response.usage
    result = create_provider(Settings(provider="ollama")).generate("ticket", system_prompt="system")
    assert result.usage is None


@pytest.mark.parametrize("error_type", [APITimeoutError, APIConnectionError])
def test_local_connection_errors(sdk: MagicMock, error_type: type[APIConnectionError]) -> None:
    create = sdk.return_value.__enter__.return_value.chat.completions.create
    create.side_effect = error_type(request=httpx.Request("POST", "http://localhost:11434/v1"))
    with pytest.raises(ProviderError, match="Ollama"):
        create_provider(Settings(provider="ollama", max_retries=0)).generate("x", system_prompt="s")
    assert create.call_count == 1


def test_model_not_found_error(sdk: MagicMock) -> None:
    create = sdk.return_value.__enter__.return_value.chat.completions.create
    create.side_effect = APIStatusError(
        "secret body",
        response=httpx.Response(404, request=httpx.Request("POST", "http://localhost:11434/v1")),
        body=None,
    )
    with pytest.raises(ProviderError, match="Ollama.*HTTP 404") as error:
        create_provider(Settings(provider="ollama")).generate("x", system_prompt="s")
    assert "secret body" not in str(error.value)
    assert create.call_count == 1


def test_reasoning_in_content_is_not_repaired(sdk: MagicMock, project: Path) -> None:
    response = sdk.return_value.__enter__.return_value.chat.completions.create.return_value
    response.choices[0].message.content = "<think>reasoning</think>" + content()
    with pytest.raises(ValidationError):
        AIService(create_provider(Settings(provider="ollama"))).parse_ticket(1, project)


def test_provider_routing_cannot_cross() -> None:
    local = Settings(provider="ollama")
    assert isinstance(create_provider(local), OllamaProvider)
    assert isinstance(create_provider(Settings(provider="openrouter")), OpenRouterProvider)
    with pytest.raises(ValueError):
        OpenRouterProvider(local)
    with pytest.raises(ValueError):
        OllamaProvider(Settings(provider="openrouter"))


def test_batch_local_failure_continues(sdk: MagicMock, project: Path) -> None:
    from ai_project.batch import parse_all

    create = sdk.return_value.__enter__.return_value.chat.completions.create
    successful = create.return_value
    create.side_effect = [ProviderError("Ollama HTTP 500 private body")] + [successful] * 29
    settings = Settings(provider="ollama", model="qwen3:8b", max_retries=0)
    result = parse_all(
        AIService(create_provider(settings)), settings, project, project / "run.json"
    )
    assert result["completed"] is True
    assert len(result["results"]) == 30
    assert result["results"][0]["error"] == "Ollama request failed (HTTP 500)."
    assert result["results"][1]["status"] == "success"
    assert "private body" not in json.dumps(result)


@pytest.mark.parametrize("command", ["parse-ticket", "parse-all"])
def test_explicit_hosted_switch(sdk: MagicMock, project: Path, command: str) -> None:
    args = [command, "--provider", "openrouter", "--project-root", str(project)]
    args += (
        ["--ticket-id", "1"]
        if command == "parse-ticket"
        else ["--output", str(project / "hosted.json")]
    )
    with (
        patch(
            "ai_project.cli.Settings.openrouter_from_env",
            return_value=Settings(provider="openrouter", model="hosted/model", api_key="dummy"),
        ),
        patch(
            "ai_project.cli.Settings.ollama_from_env", side_effect=AssertionError("Wrong provider")
        ),
    ):
        assert main(args) == 0
    assert sdk.call_args.kwargs["base_url"] == "https://openrouter.ai/api/v1"


@pytest.mark.parametrize("command", ["parse-ticket", "parse-all"])
def test_cli_local_switch(sdk: MagicMock, project: Path, command: str, capsys) -> None:
    output = project / "run.json"
    args = [
        command,
        "--provider",
        "ollama",
        "--prompt-version",
        "v1",
        "--project-root",
        str(project),
    ]
    args += ["--ticket-id", "1"] if command == "parse-ticket" else ["--output", str(output)]
    with (
        patch.dict("os.environ", {}, clear=True),
        patch(
            "ai_project.cli.Settings.openrouter_from_env",
            side_effect=AssertionError("Wrong provider"),
        ),
    ):
        assert main(args) == 0
    if command == "parse-all":
        result = json.loads(output.read_text(encoding="utf-8"))
        assert result["metadata"]["provider"] == "ollama"
        assert len(result["results"]) == 30
        assert result["results"][0]["provider"] == "ollama"
        assert result["results"][0]["model"] == "qwen3:8b-actual"
        assert result["results"][0]["temperature"] == 0
    else:
        assert json.loads(capsys.readouterr().out)["model"] == "qwen3:8b-actual"
