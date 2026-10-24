"""Offline tests: SDK calls are always mocked and use dummy credentials."""

import json
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
from ai_project.providers import GenerationResult, OpenRouterProvider, ProviderError
from ai_project.service import AIService


def valid_output() -> str:
    return json.dumps(
        {
            "summary": "Cannot log in",
            "category": "authentication",
            "priority": "medium",
            "application": None,
            "language": "en",
            "requires_support": True,
            "details": {"error_code": None, "error_message": None},
            "suggested_actions": [],
        }
    )


def response(content: str | None = None, finish: str = "stop", refusal: str | None = None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=valid_output() if content is None else content, refusal=refusal
                ),
                finish_reason=finish,
            )
        ],
        model="test/model",
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30),
    )


@pytest.fixture
def sdk():
    with patch("ai_project.providers.OpenAI") as constructor:
        client = constructor.return_value.__enter__.return_value
        client.chat.completions.create.return_value = response()
        yield constructor, client.chat.completions.create


def test_request_contract_and_metadata(sdk) -> None:
    constructor, create = sdk
    settings = Settings(provider="openrouter", model="test/model", api_key="dummy")
    result = OpenRouterProvider(settings).generate("ticket", system_prompt="system")
    assert result.model == "test/model"
    assert result.usage == {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
    assert constructor.call_args.kwargs == {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key": "dummy",
        "timeout": 30.0,
        "max_retries": 0,
    }
    request = create.call_args.kwargs
    assert request["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "ticket"},
    ]
    assert request["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "hr_support_ticket",
            "strict": True,
            "schema": HRSupportTicket.model_json_schema(),
        },
    }
    assert request["extra_body"] == {"provider": {"require_parameters": True}}
    assert request["temperature"] == 0 and request["top_p"] == 1


def status_error(code: int) -> APIStatusError:
    return APIStatusError(
        "private response body",
        response=httpx.Response(code, request=httpx.Request("POST", "https://example.test")),
        body=None,
    )


@pytest.mark.parametrize("code", [429, 500, 503, 599])
def test_transient_status_retry(sdk, code: int) -> None:
    _, create = sdk
    create.side_effect = [status_error(code), response()]
    with patch("ai_project.providers.time.sleep"):
        OpenRouterProvider(Settings(api_key="dummy")).generate("ticket", system_prompt="system")
    assert create.call_count == 2


@pytest.mark.parametrize("code", [400, 401, 403, 404, 408, 422])
def test_permanent_errors_not_retried(sdk, code: int) -> None:
    _, create = sdk
    create.side_effect = status_error(code)
    with pytest.raises(ProviderError, match=f"HTTP {code}") as error:
        OpenRouterProvider(Settings(api_key="dummy")).generate("ticket", system_prompt="system")
    assert "private response body" not in str(error.value)
    assert create.call_count == 1


@pytest.mark.parametrize("error_type", [APIConnectionError, APITimeoutError])
def test_network_retries_bounded(sdk, error_type) -> None:
    _, create = sdk
    create.side_effect = error_type(request=httpx.Request("POST", "https://example.test"))
    with patch("ai_project.providers.time.sleep"), pytest.raises(ProviderError):
        OpenRouterProvider(Settings(api_key="dummy", max_retries=2)).generate(
            "ticket", system_prompt="system"
        )
    assert create.call_count == 3


@pytest.mark.parametrize(
    "finish,refusal,content",
    [
        ("length", None, "{}"),
        ("content_filter", None, "{}"),
        ("stop", "refused", "{}"),
        ("stop", None, ""),
    ],
)
def test_unusable_responses(sdk, finish, refusal, content) -> None:
    _, create = sdk
    create.return_value = response(content, finish, refusal)
    with pytest.raises(ProviderError):
        OpenRouterProvider(Settings(api_key="dummy")).generate("ticket", system_prompt="system")
    assert create.call_count == 1


def test_no_choices_and_optional_usage(sdk) -> None:
    _, create = sdk
    value = response()
    value.usage = None
    create.return_value = value
    provider = OpenRouterProvider(Settings(api_key="dummy"))
    assert provider.generate("ticket", system_prompt="system").usage is None
    value.choices = []
    with pytest.raises(ProviderError, match="no choices"):
        provider.generate("ticket", system_prompt="system")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    (tmp_path / "prompts").mkdir()
    (tmp_path / "data/tickets.json").write_text(
        json.dumps([{"id": 1, "text": "Cannot log in"}]), encoding="utf-8"
    )
    (tmp_path / "prompts/v1.txt").write_text("system v1", encoding="utf-8")
    return tmp_path


def test_service_loads_and_validates(project: Path) -> None:
    provider = MagicMock()
    provider.generate.return_value = GenerationResult(valid_output(), "test/model")
    result = AIService(provider).parse_ticket(1, project)
    assert result.ticket.category == "authentication"
    assert result.elapsed_seconds >= 0
    provider.generate.assert_called_once_with("Cannot log in", system_prompt="system v1")


def test_service_supports_existing_prompt_location(project: Path) -> None:
    (project / "docs").mkdir()
    (project / "prompts").rename(project / "docs/prompts")
    provider = MagicMock()
    provider.generate.return_value = GenerationResult(valid_output(), "test/model")
    AIService(provider).parse_ticket(1, project)
    provider.generate.assert_called_once_with("Cannot log in", system_prompt="system v1")


@pytest.mark.parametrize("content", ["not json", "{}"])
def test_invalid_model_output_not_repaired(project: Path, content: str) -> None:
    provider = MagicMock()
    provider.generate.return_value = GenerationResult(content, "test/model")
    with pytest.raises(ValidationError):
        AIService(provider).parse_ticket(1, project)
    assert provider.generate.call_count == 1


def test_missing_ticket_no_request(project: Path) -> None:
    provider = MagicMock()
    with pytest.raises(ValueError, match="found 0"):
        AIService(provider).parse_ticket(999, project)
    provider.generate.assert_not_called()


def test_config_from_dummy_environment() -> None:
    with patch.dict(
        "os.environ",
        {
            "OPENROUTER_API_KEY": "dummy-secret",
            "OPENROUTER_MODEL": "test/model",
            "OPENROUTER_TEMPERATURE": "0.3",
            "OPENROUTER_TOP_P": "0.9",
            "OPENROUTER_TIMEOUT_SECONDS": "15",
            "OPENROUTER_MAX_RETRIES": "1",
        },
        clear=True,
    ):
        settings = Settings.openrouter_from_env()
    assert settings.temperature == 0.3 and settings.top_p == 0.9
    assert settings.timeout == 15 and settings.max_retries == 1
    assert "dummy-secret" not in repr(settings)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"temperature": -1},
        {"temperature": float("nan")},
        {"top_p": 0},
        {"timeout": 0},
        {"max_retries": 6},
    ],
)
def test_invalid_config(kwargs) -> None:
    with pytest.raises(ValueError):
        Settings(**kwargs)


def test_missing_credentials() -> None:
    with (
        patch.dict("os.environ", {}, clear=True),
        pytest.raises(ValueError, match="Set OPENROUTER"),
    ):
        Settings.openrouter_from_env()


def test_cli_json(project: Path, sdk, capsys) -> None:
    with patch(
        "ai_project.cli.Settings.openrouter_from_env",
        return_value=Settings(provider="openrouter", model="test/model", api_key="dummy"),
    ):
        assert (
            main(
                [
                    "parse-ticket",
                    "--ticket-id",
                    "1",
                    "--prompt-version",
                    "v1",
                    "--project-root",
                    str(project),
                ]
            )
            == 0
        )
    output = json.loads(capsys.readouterr().out)
    assert output["ticket"]["category"] == "authentication"
    assert output["model"] == "test/model"
    assert output["usage"]["total_tokens"] == 30


def test_cli_invalid_output_safe_error(project: Path, sdk, capsys) -> None:
    _, create = sdk
    create.return_value = response("not-json-private-content")
    with (
        patch(
            "ai_project.cli.Settings.openrouter_from_env",
            return_value=Settings(provider="openrouter", model="test/model", api_key="dummy"),
        ),
        pytest.raises(SystemExit) as error,
    ):
        main(["parse-ticket", "--ticket-id", "1", "--project-root", str(project)])
    assert error.value.code == 1
    stderr = capsys.readouterr().err
    assert "validation" in stderr
    assert "private-content" not in stderr
    assert create.call_count == 1


def test_missing_prompt_no_request(project: Path) -> None:
    (project / "prompts/v1.txt").unlink()
    provider = MagicMock()
    with pytest.raises(FileNotFoundError):
        AIService(provider).parse_ticket(1, project)
    provider.generate.assert_not_called()


def test_zero_retries(sdk) -> None:
    _, create = sdk
    create.side_effect = status_error(429)
    with patch("ai_project.providers.time.sleep") as sleep, pytest.raises(ProviderError):
        OpenRouterProvider(Settings(api_key="dummy", max_retries=0)).generate(
            "ticket", system_prompt="system"
        )
    assert create.call_count == 1
    sleep.assert_not_called()
