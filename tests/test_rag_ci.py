"""Replay actual saved artifacts; regressions must change the CLI exit status."""

import json
from pathlib import Path

import pytest

from ai_project.cli import main


def changed_baseline(tmp_path, change):
    payload = json.loads(Path("results/rag_baseline.json").read_text(encoding="utf-8"))
    change(payload)
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def change_answer(payload, change):
    generation = payload["cases"][0]["generation"]
    answer = json.loads(generation["raw_response"])
    change(answer)
    generation["answer"] = answer
    generation["raw_response"] = json.dumps(answer)


def test_saved_baseline_passes_and_counts_invalid_in_status(capsys):
    assert main(["ci-rag"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["status"]["matched"] == 16
    assert report["status_denominator"] == 20
    assert report["failing_cases"]["status"] == ["R06", "R09", "P02", "N03"]


@pytest.mark.parametrize("regression", ["schema", "status", "citation"])
def test_regression_exits_nonzero(tmp_path, regression, capsys):
    def change(answer):
        if regression == "schema":
            answer.pop("status")
        elif regression == "status":
            answer["status"] = "partial"
            answer["missing_information"] = "A required fact is unavailable."
        else:
            answer["claims"][0]["source_ids"] = ["S999"]

    path = changed_baseline(tmp_path, lambda p: change_answer(p, change))
    assert main(["ci-rag", "--baseline", str(path)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert (
        "R01"
        in report["failing_cases"][
            regression if regression != "citation" else "citation_membership"
        ]
    )
    assert report["summary"]["valid_structured_responses"] == (18 if regression == "schema" else 19)


@pytest.mark.parametrize("artifact", ["cases", "prompt", "corpus", "context"])
def test_stale_artifacts_fail(tmp_path, artifact, capsys):
    def change(payload):
        if artifact == "cases":
            payload["cases_sha256"] = "0" * 64
        elif artifact == "prompt":
            payload["settings"]["prompt_sha256"] = "0" * 64
        elif artifact == "corpus":
            payload["settings"]["index_metadata"]["source_sha256"] = "0" * 64
        else:
            payload["cases"][0]["generation"]["sources"][0]["text"] = "stale"

    path = changed_baseline(tmp_path, change)
    assert main(["ci-rag", "--baseline", str(path)]) == 1
    assert "RAG CI setup failed" in capsys.readouterr().out


def test_missing_fixture_is_actionable(tmp_path, capsys):
    assert main(["ci-rag", "--baseline", str(tmp_path / "missing.json")]) == 1
    assert "Required artifact missing" in capsys.readouterr().out


def test_cached_scores_are_ignored(tmp_path):
    def change(payload):
        payload["summary"] = {}
        for row in payload["cases"]:
            row["scores"] = {}
            row["outcome"] = "not_a_score"

    path = changed_baseline(tmp_path, change)
    assert main(["ci-rag", "--baseline", str(path)]) == 0
