"""Batch behavior tested entirely offline."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_project.batch import atomic_save, parse_all
from ai_project.cli import main
from ai_project.config import Settings
from ai_project.providers import GenerationResult, ProviderError
from ai_project.service import AIService


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts/v1.txt").write_text("system", encoding="utf-8")
    (tmp_path / "data/tickets.json").write_text(
        json.dumps(
            [
                {"id": 8, "text": "first"},
                {"id": 2, "text": "second"},
                {"id": 5, "text": "third"},
            ]
        ),
        encoding="utf-8",
    )
    return tmp_path


def generation() -> GenerationResult:
    return GenerationResult(
        json.dumps(
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
        ),
        "returned/model",
        {"total_tokens": 30},
    )


def test_order_failure_continuation_and_metadata(project: Path) -> None:
    provider = MagicMock()
    provider.generate.side_effect = [generation(), ProviderError("HTTP 429 secret"), generation()]
    output = project / "results/run.json"
    settings = Settings(provider="openrouter", model="configured/model", api_key="secret")
    result = parse_all(AIService(provider), settings, project, output)
    assert json.loads(output.read_text(encoding="utf-8")) == result
    assert [entry["ticket_id"] for entry in result["results"]] == [8, 2, 5]
    assert [entry["status"] for entry in result["results"]] == ["success", "error", "success"]
    assert result["results"][0]["usage"] == {"total_tokens": 30}
    assert result["results"][0]["output"]["category"] == "authentication"
    assert result["results"][1]["model"] == "configured/model"
    assert result["results"][1]["usage"] is None
    assert "429" in result["results"][1]["error"]
    assert "secret" not in output.read_text(encoding="utf-8")
    assert result["metadata"]["configured_model"] == "configured/model"
    assert result["metadata"]["prompt_version"] == "v1"
    assert result["completed"] is True
    assert provider.generate.call_count == 3


def test_progress_survives_interrupt(project: Path) -> None:
    provider = MagicMock()
    provider.generate.side_effect = [generation(), KeyboardInterrupt()]
    output = project / "run.json"
    with pytest.raises(KeyboardInterrupt):
        parse_all(AIService(provider), Settings(), project, output)
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["completed"] is False
    assert len(saved["results"]) == 1
    assert saved["results"][0]["ticket_id"] == 8


def test_validation_errors_are_sanitized(project: Path) -> None:
    provider = MagicMock()
    provider.generate.side_effect = [GenerationResult("secret", "m"), generation(), generation()]
    output = project / "run.json"
    result = parse_all(AIService(provider), Settings(), project, output)
    assert result["results"][0]["error"] == "Returned JSON failed HRSupportTicket validation."
    assert "secret" not in output.read_text(encoding="utf-8")


def test_no_clobber_and_explicit_overwrite(project: Path) -> None:
    output = project / "run.json"
    output.write_text("previous", encoding="utf-8")
    provider = MagicMock()
    provider.generate.return_value = generation()
    with pytest.raises(FileExistsError):
        parse_all(AIService(provider), Settings(), project, output)
    provider.generate.assert_not_called()
    assert output.read_text(encoding="utf-8") == "previous"
    assert parse_all(AIService(provider), Settings(), project, output, overwrite=True)["completed"]


def test_atomic_replace_failure_preserves_previous(project: Path) -> None:
    output = project / "run.json"
    atomic_save(output, {"old": True}, replace=False)
    with patch("ai_project.batch.os.replace", side_effect=OSError("disk failure")):
        with pytest.raises(OSError):
            atomic_save(output, {"new": True}, replace=True)
    assert json.loads(output.read_text(encoding="utf-8")) == {"old": True}
    assert not list(project.glob("*.tmp"))


def test_initial_publication_no_clobber(project: Path) -> None:
    output = project / "run.json"
    atomic_save(output, {"old": True}, replace=False)
    with pytest.raises(FileExistsError):
        atomic_save(output, {"new": True}, replace=False)
    assert json.loads(output.read_text(encoding="utf-8")) == {"old": True}


def test_protected_dataset(project: Path) -> None:
    with pytest.raises(ValueError, match="datasets or prompts"):
        parse_all(MagicMock(), Settings(), project, project / "data/tickets.json", overwrite=True)


def test_cli_requires_output() -> None:
    with pytest.raises(SystemExit) as error:
        main(["parse-all", "--prompt-version", "v1"])
    assert error.value.code == 2


def test_cli_with_mocked_provider(project: Path) -> None:
    provider = MagicMock()
    provider.generate.return_value = generation()
    with (
        patch("ai_project.cli.Settings.openrouter_from_env", return_value=Settings()),
        patch(
            "ai_project.cli.create_provider",
            return_value=provider,
        ),
    ):
        assert (
            main(
                [
                    "parse-all",
                    "--prompt-version",
                    "v1",
                    "--output",
                    str(project / "out.json"),
                    "--project-root",
                    str(project),
                ]
            )
            == 0
        )
