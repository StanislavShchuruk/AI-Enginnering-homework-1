"""Offline reproduction orchestration tests with synthetic data and mocked providers."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_project.cli import main
from ai_project.comparison import compare_runs
from ai_project.costs import Electricity, TokenPrices
from ai_project.evaluation import load_json
from ai_project.providers import GenerationResult
from ai_project.reproduction import (
    Experiment,
    PricingConfig,
    experiment_settings,
    load_experiments,
    reproduce,
)

ROOT = Path(__file__).resolve().parents[1]


def output() -> dict:
    return {
        "summary": "How to sign in", "category": "authentication", "priority": "low",
        "application": None, "language": "en", "requires_support": False,
        "details": {"error_code": None, "error_message": None}, "suggested_actions": [],
    }


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "experiments.json").write_bytes((ROOT / "experiments.json").read_bytes())
    write(tmp_path / "data/tickets.json", [{"id": i, "text": "How to sign in?"}
                                           for i in range(1, 41)])
    write(tmp_path / "data/golden_set.json", [{"id": i, "expected": output()}
                                              for i in range(1, 41)])
    write(tmp_path / "config/pricing.json", {"models": {"test/hosted": {
        "input_usd_per_million": 0.25, "output_usd_per_million": 1.5,
    }}, "power_watts": 500, "usd_per_kwh": 0.09557})
    write(tmp_path / "data/development_ids.json", list(range(1, 16)))
    write(tmp_path / "data/holdout_ids.json", list(range(16, 41)))
    (tmp_path / "docs/prompts").mkdir(parents=True)
    for version in ("v1", "v2"):
        (tmp_path / f"docs/prompts/{version}.txt").write_text(version, encoding="utf-8")
    (tmp_path / "docs/evaluation_report.md").write_text("Manual report", encoding="utf-8")
    return tmp_path


@pytest.fixture
def providers():
    provider = MagicMock()
    provider.generate.return_value = GenerationResult(json.dumps(output()), "test/model")
    with (
        patch("ai_project.reproduction.create_provider", return_value=provider) as factory,
        patch("ai_project.reproduction.dotenv_values", return_value={
            "OPENROUTER_API_KEY": "dummy", "OPENROUTER_MODEL": "test/hosted",
            "OLLAMA_MODEL": "test/local", "OLLAMA_BASE_URL": "http://127.0.0.1:11434/v1",
            "OPENROUTER_TIMEOUT_SECONDS": "11", "OLLAMA_TIMEOUT_SECONDS": "22",
        }) as dotenv,
        patch.dict(os.environ, {}, clear=True),
    ):
        yield provider, factory, dotenv


def test_matrix_order_and_validation(project: Path) -> None:
    experiments = load_experiments(project / "experiments.json", project)
    assert [(e.provider, e.prompt_version, e.temperature, e.top_p) for e in experiments] == [
        ("openrouter", "v1", 0, 1), ("ollama", "v1", 0, 1),
        ("openrouter", "v2", 0, 1), ("ollama", "v2", 0, 1),
        ("openrouter", "v1", .3, .9), ("ollama", "v1", .3, .9),
    ]
    raw = load_json(project / "experiments.json")
    cases = [[], {}, [raw[0], raw[0]]]
    for changes in [
        {"provider": "bad"}, {"prompt_version": "v3"}, {"temperature": True},
        {"temperature": -1}, {"top_p": 0}, {"top_p": float("nan")},
        {"output": "../oops.json"}, {"output": "docs/evaluation_report.md"},
        {"output": "results/nested/run.json"}, {"extra": 1},
    ]:
        cases.append([{**raw[0], **changes}])
    for case in cases:
        write(project / "bad.json", case)
        with pytest.raises(ValueError):
            load_experiments(project / "bad.json", project)


@pytest.mark.parametrize("provider", ["openrouter", "ollama"])
def test_explicit_settings_preserve_other_values(provider: str) -> None:
    experiment = Experiment(provider=provider, prompt_version="v1", temperature=.3,
                            top_p=.9, output="results/test.json")
    values = {"OPENROUTER_API_KEY": "dummy", "OPENROUTER_MODEL": "chosen/hosted",
              "OPENROUTER_TIMEOUT_SECONDS": "17", "OPENROUTER_MAX_RETRIES": "4",
              "OLLAMA_MODEL": "chosen:local", "OLLAMA_BASE_URL": "http://127.0.0.1:11434/v1",
              "OLLAMA_TIMEOUT_SECONDS": "19", f"{provider.upper()}_TEMPERATURE": "bad"}
    before = dict(values)
    settings = experiment_settings(experiment, values)
    assert settings.temperature == .3 and settings.top_p == .9
    assert settings.model == ("chosen/hosted" if provider == "openrouter" else "chosen:local")
    if provider == "openrouter":
        assert settings.api_key == "dummy" and settings.timeout == 17 and settings.max_retries == 4
    else:
        assert settings.base_url == "http://127.0.0.1:11434/v1" and settings.timeout == 19
    assert values == before


def test_execution_order_reports_skip_force_and_eval_only(project: Path, providers) -> None:
    provider, factory, dotenv = providers
    environment_before = dict(os.environ)
    reproduce(project)
    assert provider.generate.call_count == 240
    settings = [call.args[0] for call in factory.call_args_list]
    assert [(s.provider, s.temperature, s.top_p) for s in settings] == [
        ("openrouter", 0, 1), ("ollama", 0, 1), ("openrouter", 0, 1),
        ("ollama", 0, 1), ("openrouter", .3, .9), ("ollama", .3, .9),
    ]
    assert [call.kwargs["system_prompt"] for call in provider.generate.call_args_list] == (
        ["v1"] * 80 + ["v2"] * 80 + ["v1"] * 80
    )
    assert dict(os.environ) == environment_before
    report_dir = project / "results/reproduction"
    assert len(list(report_dir.glob("*.md"))) == 15
    assert "Golden records: 40" in (report_dir / "openrouter_v1_full.md").read_text()
    development = (report_dir / "openrouter_v1_development.md").read_text()
    holdout = (report_dir / "openrouter_v1_holdout.md").read_text()
    assert "Golden records: 15" in development and "Input predictions: 40" in development
    assert "entire prediction batch" in development
    assert "Golden records: 25" in holdout
    assert "Run 6" in (report_dir / "comparison.md").read_text()
    files = {p: p.read_bytes() for p in (project / "results").glob("*.json")}
    factory.reset_mock()
    dotenv.reset_mock()
    reproduce(project)
    factory.assert_not_called()
    dotenv.assert_not_called()
    (report_dir / "comparison.md").write_text("stale", encoding="utf-8")
    reproduce(project, eval_only=True)
    factory.assert_not_called()
    dotenv.assert_not_called()
    assert "Run 6" in (report_dir / "comparison.md").read_text()
    assert all(p.read_bytes() == content for p, content in files.items())
    reproduce(project, force=True)
    assert factory.call_count == 6
    assert (project / "docs/evaluation_report.md").read_text() == "Manual report"


def test_failed_inference_stops_workflow(project: Path, providers, capsys) -> None:
    provider, factory, _ = providers
    provider.generate.side_effect = RuntimeError("private provider body")
    with pytest.raises(ValueError, match="Experiment failed") as error:
        reproduce(project)
    assert "private provider body" not in str(error.value)
    assert factory.call_count == 1
    assert not (project / "results/reproduction/comparison.md").exists()
    assert "Reproduction complete" not in capsys.readouterr().out


@pytest.mark.parametrize("mode", [False, True])
def test_missing_or_invalid_predictions_fail_before_inference(
    project: Path, providers, mode
) -> None:
    _, factory, _ = providers
    if not mode:
        write(project / "results/openrouter_v1.json", {"results": [], "total_tickets": 0})
    with pytest.raises(ValueError, match="invalid saved predictions|Missing predictions"):
        reproduce(project, eval_only=mode)
    factory.assert_not_called()


def test_invalid_split_and_output_destination(project: Path, providers) -> None:
    _, factory, _ = providers
    write(project / "data/holdout_ids.json", list(range(15, 40)))
    with pytest.raises(ValueError, match="overlap"):
        reproduce(project)
    factory.assert_not_called()
    write(project / "data/holdout_ids.json", list(range(16, 41)))
    (project / "results/reproduction/comparison.md").mkdir(parents=True)
    with pytest.raises(ValueError, match="report destination"):
        reproduce(project)
    factory.assert_not_called()


def test_cli_success_and_errors(project: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(project)
    with patch("ai_project.cli.reproduce") as workflow:
        assert main(["reproduce", "--eval-only"]) == 0
        workflow.assert_called_once_with(project, eval_only=True, force=False)
    with pytest.raises(SystemExit) as error:
        main(["reproduce", "--eval-only", "--force"])
    assert error.value.code == 2
    with patch("ai_project.cli.reproduce", side_effect=ValueError("bad configuration")):
        with pytest.raises(SystemExit) as error:
            main(["reproduce"])
    assert error.value.code == 1
    assert "Reproduction failed: bad configuration" in capsys.readouterr().err


@pytest.mark.parametrize("change", ["identity", "metadata", "failed", "incomplete", "timing"])
def test_invalid_cached_batches_rejected(project: Path, providers, change: str) -> None:
    _, factory, dotenv = providers
    from ai_project.reproduction import validate_predictions

    experiment = load_experiments(project / "experiments.json", project)[0]
    payload = {
        "metadata": {"provider": "openrouter", "configured_model": "test/model",
                     "prompt_version": "v1", "temperature": 0, "top_p": 1},
        "total_tickets": 40, "completed": True,
        "results": [{"ticket_id": i, "status": "success", "output": output(),
                     "elapsed_seconds": 1} for i in range(1, 41)],
    }
    if change == "identity":
        payload["results"][0]["ticket_id"] = {}
    elif change == "metadata":
        payload["metadata"]["prompt_version"] = "v2"
    elif change == "failed":
        payload["results"][0]["status"] = "error"
    elif change == "incomplete":
        payload["completed"] = False
    else:
        payload["results"][0]["elapsed_seconds"] = -1
    with pytest.raises(ValueError):
        validate_predictions(payload, experiment, load_json(project / "data/golden_set.json"),
                             set(range(1, 41)))
    write(project / experiment.output, payload)
    with pytest.raises(ValueError, match="invalid saved predictions"):
        reproduce(project, eval_only=True)
    factory.assert_not_called()
    dotenv.assert_not_called()


def test_preflight_prompts_and_settings(project: Path, providers) -> None:
    _, factory, dotenv = providers
    prompt = project / "docs/prompts/v2.txt"
    prompt.write_text(" ", encoding="utf-8")
    with pytest.raises(ValueError, match="Empty prompt"):
        reproduce(project)
    factory.assert_not_called()
    dotenv.assert_not_called()
    prompt.write_text("v2", encoding="utf-8")
    dotenv.return_value = {}
    with pytest.raises(ValueError, match="OPENROUTER"):
        reproduce(project)
    factory.assert_not_called()


def test_process_settings_precede_file_settings(project: Path, providers) -> None:
    _, factory, _ = providers
    with patch.dict(os.environ, {"OPENROUTER_MODEL": "process/model",
                                 "OPENROUTER_TEMPERATURE": "1.9"}):
        reproduce(project)
    hosted = [call.args[0] for call in factory.call_args_list
              if call.args[0].provider == "openrouter"]
    assert [settings.model for settings in hosted] == ["process/model"] * 3
    assert [settings.temperature for settings in hosted] == [0, 0, .3]



@pytest.mark.parametrize("eval_only", [False, True])
def test_pricing_loaded_relative_to_project_root(
    project: Path, providers, monkeypatch, eval_only: bool
) -> None:
    provider, factory, dotenv = providers
    provider.generate.return_value = GenerationResult(
        json.dumps(output()), "test/model", {"prompt_tokens": 10, "completion_tokens": 20}
    )
    if eval_only:
        reproduce(project)
        factory.reset_mock()
        dotenv.reset_mock()
    # A different working directory must not affect pricing resolution.
    monkeypatch.chdir(project.parent)
    write(project / "config/pricing.json", {"models": {"test/hosted": {
        "input_usd_per_million": 2.0, "output_usd_per_million": 6.0,
    }}, "power_watts": 500, "usd_per_kwh": 0.09557})
    with patch("ai_project.reproduction.compare_runs", wraps=compare_runs) as comparison:
        reproduce(project, eval_only=eval_only)
    comparison.assert_called_once()
    prices = comparison.call_args.args[2]
    assert prices == {"test/hosted": TokenPrices(
        input_usd_per_million=2.0, output_usd_per_million=6.0,
    )}
    electricity = comparison.call_args.args[3]
    assert electricity.power_watts == 500 and electricity.usd_per_kwh == 0.09557
    assert isinstance(electricity, Electricity)
    report = (project / "results/reproduction/comparison.md").read_text(encoding="utf-8")
    assert 'test/hosted' in report and 'input $2/1M tokens; output $6/1M tokens.' in report
    assert '$0.140000' in report
    local = load_json(project / "results/ollama_qwen3_8b_v1.json")
    seconds = sum(record["elapsed_seconds"] for record in local["results"])
    expected = 0.5 * seconds / 3600 * 0.09557 * 1000 / 40
    assert f"${expected:.6f}" in report
    if eval_only:
        factory.assert_not_called()
        dotenv.assert_not_called()


@pytest.mark.parametrize("eval_only", [False, True])
@pytest.mark.parametrize("content", [
    None, "{broken", "[]", "null",
    '{"model": {"input_usd_per_million": -1, "output_usd_per_million": 1}}',
    '{"model": {"input_usd_per_million": "1", "output_usd_per_million": 1}}',
    '{"model": {"input_usd_per_million": true, "output_usd_per_million": 1}}',
    '{"model": {"input_usd_per_million": NaN, "output_usd_per_million": 1}}',
    '{"model": {"input_usd_per_million": 1}}',
    '{"model": {"input_usd_per_million": 1, "output_usd_per_million": 1, "extra": 1}}',
])
def test_bad_pricing_stops_before_providers_or_outputs(
    project: Path, providers, monkeypatch, capsys, eval_only: bool, content: str | None
) -> None:
    _, factory, dotenv = providers
    path = project / "config/pricing.json"
    if content is None:
        path.unlink()
    else:
        if content.startswith('{"model":'):
            content = '{"models":' + content + '}'
        path.write_text(content, encoding="utf-8")
    monkeypatch.chdir(project)
    with pytest.raises(SystemExit) as error:
        main(["reproduce", *(["--eval-only"] if eval_only else [])])
    assert error.value.code == 1
    captured = capsys.readouterr()
    assert "Cannot load config/pricing.json" in captured.err
    assert "Reproduction complete" not in captured.out
    factory.assert_not_called()
    dotenv.assert_not_called()
    assert not (project / "results").exists()


@pytest.mark.parametrize("field", ["power_watts", "usd_per_kwh"])
@pytest.mark.parametrize("value", [-1, True, "500", float("nan"), float("inf")])
@pytest.mark.parametrize("eval_only", [False, True])
def test_invalid_electricity_stops_before_inference(
    project: Path, providers, field: str, value: object, eval_only: bool
) -> None:
    _, factory, dotenv = providers
    config = load_json(project / "config/pricing.json")
    config[field] = value
    write(project / "config/pricing.json", config)
    with pytest.raises(ValueError, match="Cannot load config/pricing.json"):
        reproduce(project, eval_only=eval_only)
    factory.assert_not_called()
    dotenv.assert_not_called()
    assert not (project / "results").exists()


@pytest.mark.parametrize("config", [{}, {"models": []}, {"models": {}, "extra": 1}])
def test_invalid_pricing_structure(config: dict) -> None:
    with pytest.raises(ValueError):
        PricingConfig.model_validate(config)


@pytest.mark.parametrize("energy", [{}, {"power_watts": None, "usd_per_kwh": None}])
def test_optional_electricity_settings(energy: dict) -> None:
    pricing = PricingConfig.model_validate({"models": {}, **energy})
    assert pricing.models == {}
    assert pricing.power_watts is None and pricing.usd_per_kwh is None
