"""Task 9B checks use saved inputs and mocked providers only."""

import csv
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from ai_project.cli import main
from ai_project.providers import GenerationResult, ProviderError
from ai_project.rag_judge import (
    PROMPT_PATH,
    JudgeProvider,
    JudgeVerdict,
    evaluate_judge,
    judge_request,
    load_inputs,
    markdown,
    summarize,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def inputs():
    return load_inputs(
        ROOT / "results/rag_baseline.json",
        ROOT / "evals/rag_cases.json",
        ROOT / "evals/rag_human_labels.csv",
    )


def verdict(count=1, completeness="pass", support="pass"):
    return {
        "completeness": completeness,
        "completeness_reason": "Expected facts checked.",
        "faithfulness": support if count else "n/a",
        "faithfulness_reason": "Cited passages checked." if count else "No claims.",
        "claim_verdicts": [
            {"claim_index": i + 1, "support": support, "reason": "S1 supports this wording."}
            for i in range(count)
        ],
    }


def provider_for_saved_answers():
    def generate(request, *, system_prompt):
        data = json.loads(request)
        return GenerationResult(
            json.dumps(verdict(len(data["candidate_answer"]["claims"]))),
            "mock-judge",
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

    return Mock(generate=Mock(side_effect=generate))


def test_real_inputs_and_no_human_leakage(inputs):
    baseline, cases, humans = inputs
    assert len(humans) == 10
    assert humans["N01"]["Faithfulness"] == "n/a"
    saved = baseline["cases"][0]
    payload = json.loads(judge_request(cases[saved["id"]], saved["generation"]))
    assert set(payload) == {"question", "candidate_answer", "excerpts", "expectations"}
    assert payload["excerpts"] == json.loads(saved["generation"]["generation_request"])["excerpts"]
    assert payload["candidate_answer"] == saved["generation"]["answer"]
    assert payload["expectations"]["required_facts"][0]["qualifications"]
    for human in humans.values():
        if human["Reason"]:
            assert human["Reason"] not in json.dumps(payload)


@pytest.mark.parametrize("mutation", ["hash", "duplicate", "question", "context", "citation"])
def test_reject_tampered_baseline(tmp_path, mutation):
    baseline = json.loads((ROOT / "results/rag_baseline.json").read_text(encoding="utf-8"))
    if mutation == "hash":
        baseline["cases_sha256"] = "0" * 64
    elif mutation == "duplicate":
        baseline["cases"][1]["id"] = baseline["cases"][0]["id"]
    elif mutation == "question":
        baseline["cases"][0]["question"] = "Different question"
    elif mutation == "context":
        baseline["cases"][0]["generation"]["sources"][0]["text"] = "Changed excerpt"
    else:
        baseline["cases"][0]["generation"]["answer"]["claims"][0]["source_ids"] = ["unknown"]
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline), encoding="utf-8")
    with pytest.raises(ValueError):
        load_inputs(path, ROOT / "evals/rag_cases.json", ROOT / "evals/rag_human_labels.csv")


@pytest.mark.parametrize(
    "mutation", ["whitespace", "invalid_id", "invalid_answer", "duplicate", "score", "missing"]
)
def test_csv_validation(tmp_path, mutation):
    with (ROOT / "evals/rag_human_labels.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    if mutation == "whitespace":
        rows[0] = [f" {header} " for header in rows[0]]
    elif mutation == "invalid_id":
        rows[1][0] = "UNKNOWN"
    elif mutation == "invalid_answer":
        rows[1][0] = "R09"
    elif mutation == "duplicate":
        rows[2][0] = rows[1][0]
    elif mutation == "score":
        rows[1][1] = "maybe"
    else:
        rows.pop()
    path = tmp_path / "human.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerows(rows)
    args = (ROOT / "results/rag_baseline.json", ROOT / "evals/rag_cases.json", path)
    if mutation == "whitespace":
        assert len(load_inputs(*args)[2]) == 10
    else:
        with pytest.raises(ValueError):
            load_inputs(*args)


@pytest.mark.parametrize(
    "change",
    [
        {"completeness": "n/a"},
        {"faithfulness": "n/a"},
        {"faithfulness": "fail"},
        {"completeness_reason": " "},
        {"faithfulness_reason": ""},
        {"extra": True},
        {"claim_verdicts": [{"claim_index": 2, "support": "pass", "reason": "Evidence"}]},
    ],
)
def test_strict_verdict(change):
    with pytest.raises(ValidationError):
        JudgeVerdict.model_validate({**verdict(), **change})


def test_no_claims_and_failed_claim():
    assert JudgeVerdict.model_validate(verdict(0)).faithfulness == "n/a"
    assert JudgeVerdict.model_validate(verdict(1, support="fail")).faithfulness == "fail"


def test_judge_all_valid_and_preserve_baseline_error(inputs):
    baseline, cases, humans = inputs
    before = json.dumps(baseline)
    provider = provider_for_saved_answers()
    rows = evaluate_judge(baseline, cases, humans, provider, "rubric")
    assert provider.generate.call_count == 19
    assert json.dumps(baseline) == before
    assert (
        next(r for r in rows if r["id"] == "R09")["outcome"] == "baseline_response_validation_error"
    )
    s = summarize(rows)
    assert s["total_cases"] == 20
    assert s["subsets"]["calibration"]["cases"] == 10
    assert s["subsets"]["judge_only"]["cases"] == 9
    assert s["subsets"]["baseline_error"]["cases"] == 1
    assert s["subsets"]["judge_only"]["outcomes"]["judged"] == 9
    assert s["agreement"]["completeness"]["denominator"] == 10
    assert s["agreement"]["completeness"]["matches"] == 6
    assert s["agreement"]["faithfulness"]["denominator"] == 9
    assert s["agreement"]["faithfulness"]["matches"] == 7
    assert s["human_faithfulness_na"] == ["N01"]
    r07 = next(d for d in s["disagreements"] if d["id"] == "R07")
    assert r07["human_reason"] == humans["R07"]["Reason"]
    assert r07["judge_reason"] == "Expected facts checked."
    assert rows[0]["model"] == "mock-judge"
    assert rows[0]["usage"]["total_tokens"] == 15


@pytest.mark.parametrize("response", ["not json", json.dumps(verdict(0)), json.dumps(verdict(2))])
def test_schema_errors_not_failures(inputs, response):
    baseline, cases, humans = inputs
    baseline["cases"] = baseline["cases"][:1]
    provider = Mock(generate=Mock(return_value=GenerationResult(response, "mock")))
    rows = evaluate_judge(baseline, cases, humans, provider, "rubric")
    assert rows[0]["outcome"] == "judge_schema_error"
    assert "verdict" not in rows[0]
    assert rows[0]["raw_response"] == response
    s = summarize(rows)
    assert s["agreement"]["completeness"]["denominator"] == 0
    assert s["agreement"]["completeness"]["judge_errors_excluded"] == 1


def test_provider_error_and_continue(inputs):
    baseline, cases, humans = inputs
    provider = provider_for_saved_answers()
    generate = provider.generate.side_effect
    call = 0

    def sometimes_fail(request, *, system_prompt):
        nonlocal call
        call += 1
        if call == 1:
            raise ProviderError("private provider detail")
        return generate(request, system_prompt=system_prompt)

    provider.generate.side_effect = sometimes_fail
    rows = evaluate_judge(baseline, cases, humans, provider, "rubric")
    assert rows[0]["outcome"] == "judge_provider_error"
    assert "private provider detail" not in json.dumps(rows)
    assert len(rows) == 20
    assert summarize(rows)["agreement"]["completeness"]["denominator"] == 9


def test_validate_only_never_creates_provider():
    with patch("ai_project.rag_judge.JudgeProvider") as provider:
        assert main(["eval-rag-judge", "--validate-only"]) == 0
    provider.assert_not_called()


def test_cli_reports_and_dotenv(tmp_path, inputs):
    output = tmp_path / "judge.json"
    with (
        patch("ai_project.rag_judge.JudgeProvider", return_value=provider_for_saved_answers()),
        patch.dict(
            "os.environ", {"OPENROUTER_API_KEY": "test-only", "OPENROUTER_MODEL": "configured"}
        ),
        patch("ai_project.rag_judge.load_dotenv") as dotenv,
    ):
        assert main(["eval-rag-judge", "--model", "chosen", "--output", str(output)]) == 0
    dotenv.assert_called_once_with(Path.cwd() / ".env", override=False)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["model"] == "chosen"
    assert report["prompt_version"] == "rag-judge-v1"
    assert len(report["prompt_sha256"]) == 64
    assert set(report["input_hashes"]) == {"baseline", "cases", "human_labels"}
    text = output.with_suffix(".md").read_text(encoding="utf-8")
    assert "N01" in text and "R09" in text and "R07 / completeness" in text
    assert "Human:" in text and "Judge:" in text
    assert "test-only" not in output.read_text(encoding="utf-8")
    assert markdown(report) == text
    with patch("ai_project.rag_judge.JudgeProvider") as provider:
        with pytest.raises(SystemExit):
            main(["eval-rag-judge", "--output", str(output)])
        provider.assert_not_called()


def test_provider_uses_judge_schema():
    assert JudgeProvider.response_model is JudgeVerdict
    assert JudgeProvider.schema_name == "peopleflow_judge"
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    assert "untrusted DATA" in prompt and "ONLY against its own source_ids" in prompt


def test_missing_settings_diagnostic(tmp_path, capsys):
    with (
        patch.dict("os.environ", {}, clear=True),
        patch("ai_project.rag_judge.load_dotenv"),
        patch("ai_project.rag_judge.JudgeProvider") as provider,
        pytest.raises(SystemExit) as error,
    ):
        main(["eval-rag-judge", "--output", str(tmp_path / "judge.json")])
    assert error.value.code == 1
    text = capsys.readouterr().err
    assert "during OpenRouter configuration" in text
    assert "Set OPENROUTER_API_KEY and OPENROUTER_MODEL" in text
    assert "project .env" in text
    provider.assert_not_called()


def test_placeholder_diagnostic(tmp_path, capsys):
    with patch("ai_project.rag_judge.JudgeProvider") as provider, pytest.raises(SystemExit):
        main(
            [
                "eval-rag-judge",
                "--model",
                "provider/model-id",
                "--output",
                str(tmp_path / "judge.json"),
            ]
        )
    assert "documentation placeholder" in capsys.readouterr().err
    provider.assert_not_called()


def test_existing_markdown_diagnostic(tmp_path, capsys):
    output = tmp_path / "judge.json"
    output.with_suffix(".md").write_text("Keep this report", encoding="utf-8")
    with patch("ai_project.rag_judge.JudgeProvider") as provider, pytest.raises(SystemExit):
        main(["eval-rag-judge", "--output", str(output)])
    assert "during output validation" in capsys.readouterr().err
    assert output.with_suffix(".md").read_text(encoding="utf-8") == "Keep this report"
    provider.assert_not_called()


def test_schema_error_diagnostic_hides_input(capsys):
    with (
        patch(
            "ai_project.rag_judge.load_inputs",
            side_effect=ValidationError.from_exception_data(
                "SavedData",
                [{"type": "int_parsing", "loc": ("field",), "input": "sensitive-candidate-text"}],
            ),
        ),
        pytest.raises(SystemExit),
    ):
        main(["eval-rag-judge", "--validate-only"])
    text = capsys.readouterr().err
    assert "during input validation" in text
    assert "sensitive-candidate-text" not in text
