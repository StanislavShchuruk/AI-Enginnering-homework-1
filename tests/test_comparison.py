"""Offline cost arithmetic and comparison CLI regression tests."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from test_evaluation import batch, entry, gold, ticket

from ai_project.cli import main
from ai_project.comparison import compare_runs
from ai_project.costs import Electricity, TokenPrices, estimate_cost
from ai_project.evaluation import evaluate

PRICES = {"offline": TokenPrices(input_usd_per_million=2.0, output_usd_per_million=4.0)}


def run(provider: str = "openrouter", **changes: Any) -> dict[str, Any]:
    return batch(
        entry(usage={"prompt_tokens": 100, "completion_tokens": 50}, **changes),
        metadata={
            "provider": provider,
            "configured_model": "offline",
            "prompt_version": "v1",
            "temperature": 0.0,
            "top_p": 1.0,
        },
    )


def test_hosted_cost_includes_recorded_failures() -> None:
    predictions = run()
    predictions["results"].append(
        entry(2, status="error", output=None, usage={"prompt_tokens": 200, "completion_tokens": 0})
    )
    predictions["total_tickets"] = 2
    cost = estimate_cost(predictions, PRICES, Electricity())
    assert cost["api_usd_per_1000"] == pytest.approx(0.4)
    assert cost["electricity_usd_per_1000"] is None


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        {"total_tokens": 150},
        {"prompt_tokens": 100, "completion_tokens": None},
        {"prompt_tokens": True, "completion_tokens": 50},
        {"prompt_tokens": -1, "completion_tokens": 50},
        {"prompt_tokens": 1.5, "completion_tokens": 50},
    ],
)
def test_missing_or_invalid_usage_is_not_free(usage: Any) -> None:
    predictions = run(status="error", output=None)
    predictions["results"][0]["usage"] = usage
    assert estimate_cost(predictions, PRICES, Electricity())["api_usd_per_1000"] is None


def test_prices_missing_and_explicit_zero() -> None:
    assert estimate_cost(run(), {}, Electricity())["api_usd_per_1000"] is None
    prices = {"offline": TokenPrices(input_usd_per_million=0, output_usd_per_million=0)}
    assert estimate_cost(run(), prices, Electricity())["api_usd_per_1000"] == 0


def test_local_electricity_includes_failures() -> None:
    predictions = run("ollama", elapsed_seconds=1800)
    predictions["results"].append(entry(2, status="error", elapsed_seconds=1800))
    predictions["total_tickets"] = 2
    cost = estimate_cost(predictions, {}, Electricity(power_watts=200, usd_per_kwh=0.25))
    assert cost["api_usd_per_1000"] == 0
    assert cost["electricity_usd_per_1000"] == pytest.approx(25)


@pytest.mark.parametrize(
    "settings", [Electricity(), Electricity(power_watts=100), Electricity(usd_per_kwh=0.25)]
)
def test_local_missing_configuration(settings: Electricity) -> None:
    cost = estimate_cost(run("ollama"), {}, settings)
    assert cost["api_usd_per_1000"] == 0
    assert cost["electricity_usd_per_1000"] is None


@pytest.mark.parametrize("elapsed", [None, True, -1, "10", float("nan"), float("inf")])
def test_local_invalid_time(elapsed: Any) -> None:
    cost = estimate_cost(
        run("ollama", elapsed_seconds=elapsed), {}, Electricity(power_watts=100, usd_per_kwh=0.25)
    )
    assert cost["electricity_usd_per_1000"] is None


@pytest.mark.parametrize("provider", ["openrouter", "ollama"])
@pytest.mark.parametrize("case", ["empty", "incomplete", "count", "malformed", "provider"])
def test_partial_or_unusable_records_have_no_cost_estimate(provider: str, case: str) -> None:
    predictions = run(provider)
    if case == "empty":
        predictions.update(results=[], total_tickets=0)
    elif case == "incomplete":
        predictions["completed"] = False
    elif case == "count":
        predictions["total_tickets"] = 2
    elif case == "malformed":
        predictions["results"] = [None]
    else:
        predictions["results"][0]["provider"] = "different"
    cost = estimate_cost(predictions, PRICES, Electricity(power_watts=100, usd_per_kwh=0.25))
    key = "api_usd_per_1000" if provider == "openrouter" else "electricity_usd_per_1000"
    assert cost[key] is None


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True, "2"])
def test_invalid_cost_configuration(value: Any) -> None:
    with pytest.raises(ValidationError):
        TokenPrices(input_usd_per_million=value, output_usd_per_million=1.0)
    with pytest.raises(ValidationError):
        Electricity(power_watts=value)
    with pytest.raises(ValidationError):
        Electricity(usd_per_kwh=value)


def test_comparison_reuses_evaluation_and_reports_settings() -> None:
    first = run()
    second = run("ollama", output=ticket(priority="high"))
    report = compare_runs(
        [("a|b.json", first), ("local.json", second)], gold(1), PRICES, Electricity()
    )
    expected = evaluate(second, gold(1))
    correct = sum(s["correct"] for s in expected["fields"].values())
    assert f"{correct}/7 (85.71%)" in report
    assert "7/7 (100.00%)" in report
    assert "| priority | 1/1 (100.00%) | 0/1 (0.00%) |" in report
    assert "a&#124;b.json" in report
    assert '"v1" | 0.0 | 1.0' in report
    assert "$0.400000" in report and "$0.000000" in report and "N/A" in report
    assert "not actual billed charges" in report
    assert "summed elapsed seconds" in report
    assert "## Methodology and limitations" in report


def test_comparison_issues_and_missing_metadata() -> None:
    predictions = run()
    predictions["metadata"] = {}
    predictions["completed"] = False
    report = compare_runs([("run", predictions)], gold(1), {}, Electricity())
    assert "Unknown provider" in report
    assert "Batch is incomplete" in report
    assert "N/A" in report


def test_compare_cli_offline_and_protects_files(tmp_path: Path) -> None:
    predictions = tmp_path / "predictions.json"
    second = tmp_path / "local.json"
    golden = tmp_path / "golden.json"
    pricing = tmp_path / "pricing.json"
    output = tmp_path / "comparison.md"
    predictions.write_text(json.dumps(run()), encoding="utf-8")
    second.write_text(json.dumps(run("ollama")), encoding="utf-8")
    golden.write_text(json.dumps(gold(1)), encoding="utf-8")
    pricing.write_text(json.dumps({k: v.model_dump() for k, v in PRICES.items()}), encoding="utf-8")
    originals = {p: p.read_bytes() for p in (predictions, second, golden, pricing)}
    args = [
        "compare",
        "--predictions",
        str(predictions),
        str(second),
        "--golden",
        str(golden),
        "--pricing",
        str(pricing),
        "--power-watts",
        "100",
        "--electricity-usd-per-kwh",
        "0.25",
        "--output",
        str(output),
    ]
    with (
        patch("ai_project.cli.create_provider", side_effect=AssertionError("No models")),
        patch("ai_project.cli.Settings.from_env", side_effect=AssertionError("No environment")),
    ):
        assert main(args) == 0
        content = output.read_bytes()
        with pytest.raises(SystemExit):
            main(args)
        assert output.read_bytes() == content
    assert "# Offline run comparison" in output.read_text(encoding="utf-8")
    for path, original in originals.items():
        assert path.read_bytes() == original


@pytest.mark.parametrize("problem", ["pricing", "batch", "golden", "suffix", "power"])
def test_compare_invalid_input_does_not_create_report(tmp_path: Path, problem: str) -> None:
    predictions = tmp_path / "predictions.json"
    golden = tmp_path / "golden.json"
    pricing = tmp_path / "pricing.json"
    output = tmp_path / ("report.json" if problem == "suffix" else "report.md")
    predictions.write_text(json.dumps(run()) if problem != "batch" else "{}", encoding="utf-8")
    golden.write_text(json.dumps(gold(1)) if problem != "golden" else "[]", encoding="utf-8")
    pricing.write_text("{}" if problem != "pricing" else '{"m": {}}', encoding="utf-8")
    args = [
        "compare",
        "--predictions",
        str(predictions),
        "--golden",
        str(golden),
        "--pricing",
        str(pricing),
        "--output",
        str(output),
    ]
    if problem == "power":
        args += ["--power-watts", "-1"]
    with pytest.raises(SystemExit):
        main(args)
    assert not output.exists()


def test_zero_power_and_no_latency_samples() -> None:
    predictions = run("ollama", status="error", elapsed_seconds=10)
    cost = estimate_cost(predictions, {}, Electricity(power_watts=0, usd_per_kwh=0.25))
    assert cost["electricity_usd_per_1000"] == 0
    report = compare_runs([("failed", predictions)], gold(1, 2), {}, Electricity())
    assert "0/14 (0.00%)" in report
    assert "0/1 (0.00%) | N/A | N/A" in report


def test_compare_cli_without_cost_configuration(tmp_path: Path) -> None:
    predictions = tmp_path / "run.json"
    golden = tmp_path / "golden.json"
    output = tmp_path / "report.md"
    predictions.write_text(json.dumps(run()), encoding="utf-8")
    golden.write_text(json.dumps(gold(1)), encoding="utf-8")
    with (
        patch("ai_project.config.load_dotenv", side_effect=AssertionError("No .env")),
        patch("ai_project.cli.create_provider", side_effect=AssertionError("No models")),
    ):
        assert (
            main(
                [
                    "compare",
                    "--predictions",
                    str(predictions),
                    "--golden",
                    str(golden),
                    "--output",
                    str(output),
                ]
            )
            == 0
        )
    report = output.read_text(encoding="utf-8")
    assert "No token prices configured" in report
    assert "No explicit pricing" in report


@pytest.mark.parametrize("override", [False, True])
def test_compare_shared_pricing_and_energy_overrides(tmp_path: Path, override: bool) -> None:
    hosted = tmp_path / "hosted.json"
    local = tmp_path / "local.json"
    golden = tmp_path / "golden.json"
    pricing = tmp_path / "pricing.json"
    output = tmp_path / "comparison.md"
    hosted.write_text(json.dumps(run()), encoding="utf-8")
    local.write_text(json.dumps(run("ollama")), encoding="utf-8")
    golden.write_text(json.dumps(gold(1)), encoding="utf-8")
    pricing.write_text(json.dumps({
        "models": {k: v.model_dump() for k, v in PRICES.items()},
        "power_watts": 500, "usd_per_kwh": 0.09557,
    }), encoding="utf-8")
    args = ["compare", "--predictions", str(hosted), str(local), "--golden", str(golden),
            "--pricing", str(pricing), "--output", str(output)]
    if override:
        args += ["--power-watts", "0", "--electricity-usd-per-kwh", "0.25"]
    with patch("ai_project.cli.compare_runs", wraps=compare_runs) as comparison:
        assert main(args) == 0
    electricity = comparison.call_args.args[3]
    assert electricity.power_watts == (0 if override else 500)
    assert electricity.usd_per_kwh == (0.25 if override else 0.09557)
    report = output.read_text(encoding="utf-8")
    assert "$0.400000" in report
    expected = estimate_cost(run("ollama"), PRICES, electricity)["electricity_usd_per_1000"]
    assert f"${expected:.6f}" in report
