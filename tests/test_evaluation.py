"""Synthetic evaluation fixtures; no providers or real datasets are needed."""

import copy
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from ai_project.cli import main
from ai_project.evaluation import evaluate, markdown, percentile


def ticket(**changes: Any) -> dict[str, Any]:
    return {
        "summary": "Login",
        "category": "authentication",
        "priority": "medium",
        "application": "Portal",
        "language": "en",
        "requires_support": True,
        "details": {"error_code": None, "error_message": "Error"},
        "suggested_actions": [],
        **changes,
    }


def entry(ticket_id: int = 1, **changes: Any) -> dict[str, Any]:
    return {
        "ticket_id": ticket_id,
        "status": "success",
        "output": ticket(),
        "elapsed_seconds": 1,
        **changes,
    }


def batch(*records: Any, **changes: Any) -> dict[str, Any]:
    return {
        "results": list(records),
        "total_tickets": len(records),
        "completed": True,
        "metadata": {
            "provider": "test",
            "configured_model": "offline",
            "prompt_version": "v1",
            "temperature": 0,
            "top_p": 1,
        },
        **changes,
    }


def gold(*ids: int) -> list[dict[str, Any]]:
    return [{"id": ticket_id, "expected": ticket()} for ticket_id in ids]


def test_matching_and_normalization() -> None:
    first = ticket(
        application="  PORTAL ", details={"error_code": None, "error_message": " ERROR  "}
    )
    report = evaluate(
        batch(entry(2, output=ticket(priority="high")), entry(1, output=first)), gold(1, 2)
    )
    assert report["fields"]["application"]["correct"] == 2
    assert report["fields"]["priority"]["correct"] == 1
    assert report["mismatches"] == [
        {
            "ticket_id": 2,
            "field": "priority",
            "expected": "medium",
            "actual": "high",
            "actual_missing": False,
        }
    ]


def test_null_is_not_empty_and_unicode_casefold() -> None:
    reference = gold(1)
    reference[0]["expected"]["application"] = "Straße"
    report = evaluate(
        batch(
            entry(
                output=ticket(
                    application="STRASSE", details={"error_code": "", "error_message": "Error"}
                )
            )
        ),
        reference,
    )
    assert report["fields"]["application"]["correct"] == 1
    assert report["mismatches"][0]["actual"] == ""


def test_invalid_failed_missing_and_full_batch_validity() -> None:
    invalid = ticket(requires_support="true")
    report = evaluate(
        batch(
            entry(1, output=invalid),
            entry(2, status="error", output=None),
            entry(8),
            total_tickets=5,
        ),
        gold(1, 2, 3),
    )
    assert report["valid_output_rate"] == {"correct": 1, "total": 5, "accuracy_percent": 20}
    assert report["missing_golden_ids"] == [3]
    assert all(score["correct"] == 0 and score["total"] == 3 for score in report["fields"].values())
    assert len(report["mismatches"]) == 21
    assert any("differs" in issue for issue in report["issues"])


def test_duplicates_are_ambiguous_and_missing_id_is_invalid() -> None:
    no_id = entry()
    del no_id["ticket_id"]
    report = evaluate(batch(entry(), entry(), no_id, None, entry(True)), gold(1))
    assert report["duplicate_prediction_ids"] == [1]
    assert report["fields"]["category"]["correct"] == 0
    assert report["valid_output_rate"]["total"] == 5
    assert report["valid_output_rate"]["correct"] == 2
    assert any("ticket_id" in issue for issue in report["issues"])


@pytest.mark.parametrize(
    "golden", [[], {}, [{"expected": ticket()}], gold(1, 1), [{"id": 1, "expected": {}}]]
)
def test_bad_golden_is_rejected(golden: Any) -> None:
    with pytest.raises(ValueError):
        evaluate(batch(entry()), golden)


@pytest.mark.parametrize(
    "payload", [[], {}, batch(total_tickets=True), batch(total_tickets=-1), {"results": {}}]
)
def test_bad_batch_is_rejected(payload: Any) -> None:
    with pytest.raises(ValueError):
        evaluate(payload, gold(1))


def test_latency_percentiles_and_filtering() -> None:
    records = [
        entry(i, elapsed_seconds=value)
        for i, value in enumerate([0, 10, 20, 30, -1, None, True, float("nan"), float("inf"), "3"])
    ]
    records += [
        entry(11, status="error", elapsed_seconds=500),
        entry(12, output={}, elapsed_seconds=40),
    ]
    report = evaluate(batch(*records), gold(1))
    assert report["latency_seconds"] == {"samples": 5, "p50": 20, "p95": 38}
    assert percentile([], 0.95) is None
    assert percentile([4], 0.95) == 4
    assert percentile([0, 10], 0.95) == 9.5


def test_markdown_escaping_and_missing_values() -> None:
    reference = gold(1, 2)
    reference[0]["expected"]["application"] = "a|b\n<c>`\\"
    report = evaluate(batch(entry(output=ticket(application=""))), reference)
    rendered = markdown(report)
    assert "&#124;" in rendered and "&lt;c&gt;" in rendered
    assert "&#96;" in rendered and "&#92;" in rendered
    assert "**MISSING/INVALID**" in rendered and '""' in rendered
    assert "null" in rendered and "No LLM judge" in rendered
    for line in rendered.splitlines():
        if line.startswith("| 1 |"):
            assert line.count("|") == 5


@pytest.mark.parametrize(
    "metadata, expected",
    [
        ({"temperature": 0.0, "top_p": 1.0}, "Temperature: 0.0; top_p: 1.0."),
        ({}, "Temperature: Not recorded; top_p: Not recorded."),
    ],
)
def test_markdown_sampling_settings(metadata: dict[str, Any], expected: str) -> None:
    report = evaluate(batch(entry(), metadata=metadata), gold(1))
    assert expected in markdown(report)


@pytest.mark.parametrize("extension", ["md", "json"])
def test_cli_outputs_and_no_provider(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], extension: str
) -> None:
    predictions = tmp_path / "predictions.json"
    golden = tmp_path / "golden.json"
    output = tmp_path / f"report.{extension}"
    predictions.write_text(json.dumps(batch(entry())), encoding="utf-8")
    golden.write_text(json.dumps(gold(1)), encoding="utf-8")
    args = ["eval", "--predictions", str(predictions), "--golden", str(golden)]
    with patch("ai_project.cli.create_provider", side_effect=AssertionError("No provider")):
        assert main(args) == 0
        assert main([*args, "--output", str(output)]) == 0
    assert "Valid outputs: 1/1" in capsys.readouterr().out
    content = output.read_text(encoding="utf-8")
    if extension == "json":
        assert json.loads(content)["metadata"]["configured_model"] == "offline"
    else:
        assert "# Offline evaluation" in content
    with pytest.raises(SystemExit):
        main([*args, "--output", str(predictions)])
    with pytest.raises(SystemExit):
        main([*args, "--output", str(output)])
    output.write_text("Old report", encoding="utf-8")
    assert main([*args, "--output", str(output), "--overwrite"]) == 0
    assert output.read_text(encoding="utf-8") == content
    for source in (predictions, golden):
        original = source.read_text(encoding="utf-8")
        with pytest.raises(SystemExit):
            main([*args, "--output", str(source), "--overwrite"])
        assert source.read_text(encoding="utf-8") == original
    assert json.loads(predictions.read_text(encoding="utf-8")) == batch(entry())


def test_missing_output_and_empty_batch() -> None:
    record = copy.deepcopy(entry())
    del record["output"]
    assert evaluate(batch(record), gold(1))["valid_output_rate"]["correct"] == 0
    report = evaluate(batch(), gold(1))
    assert report["valid_output_rate"]["accuracy_percent"] is None
    assert report["fields"]["category"]["accuracy_percent"] == 0


def test_cli_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        main(["eval", "--predictions", str(path), "--golden", str(path)])
    assert error.value.code == 1


def test_selected_ids_preserve_batch_metrics() -> None:
    predictions = batch(
        entry(1, output=ticket(priority="high"), elapsed_seconds=1),
        entry(2, elapsed_seconds=10),
        entry(3, output={}, elapsed_seconds=20),
        entry(4, status="error", output=None),
        total_tickets=5,
    )
    original = copy.deepcopy(predictions)
    reference = gold(1, 2, 3, 4, 5)
    full = evaluate(predictions, reference)
    selected = evaluate(predictions, reference, ids=[1, 5])
    assert selected["golden_count"] == 2
    assert selected["missing_golden_ids"] == [5]
    assert selected["fields"]["priority"]["correct"] == 0
    assert selected["fields"]["category"]["correct"] == 1
    assert all(score["total"] == 2 for score in selected["fields"].values())
    assert {item["ticket_id"] for item in selected["mismatches"]} == {1, 5}
    assert selected["valid_output_rate"] == full["valid_output_rate"]
    assert selected["latency_seconds"] == full["latency_seconds"]
    assert selected["input_prediction_count"] == 4
    assert "entire prediction batch" in markdown(selected)
    assert "selected golden IDs: [1, 5]" in markdown(selected)
    assert predictions == original
    assert evaluate(predictions, reference, ids=None) == full


@pytest.mark.parametrize("ids", [[], [1, 1], [True], [1.0], ["1"], [None], {}, "1", [99]])
def test_invalid_selected_ids(ids: Any) -> None:
    with pytest.raises(ValueError):
        evaluate(batch(entry()), gold(1), ids=ids)


@pytest.mark.parametrize("extension", ["md", "json"])
def test_cli_ids_file(tmp_path: Path, extension: str) -> None:
    predictions = tmp_path / "predictions.json"
    golden = tmp_path / "golden.json"
    ids_file = tmp_path / "ids.json"
    output = tmp_path / f"report.{extension}"
    predictions.write_text(json.dumps(batch(entry(1), entry(2))), encoding="utf-8")
    golden.write_text(json.dumps(gold(1, 2)), encoding="utf-8")
    ids_file.write_text("[2]", encoding="utf-8")
    args = ["eval", "--predictions", str(predictions), "--golden", str(golden),
            "--ids-file", str(ids_file)]
    with patch("ai_project.cli.create_provider", side_effect=AssertionError("No provider")):
        assert main([*args, "--output", str(output)]) == 0
    content = output.read_text(encoding="utf-8")
    if extension == "json":
        report = json.loads(content)
        assert report["golden_count"] == 1
        assert report["fields"]["category"]["total"] == 1
        assert report["valid_output_rate"]["total"] == 2
        assert report["latency_seconds"]["samples"] == 2
    else:
        assert "Golden records: 1." in content
        assert "entire prediction batch" in content
    with pytest.raises(SystemExit):
        main([*args, "--output", str(ids_file), "--overwrite"])
    assert ids_file.read_text(encoding="utf-8") == "[2]"
    for invalid in ["null", "[]", "[true]", "[1, 1]", "[99]", "{broken"]:
        ids_file.write_text(invalid, encoding="utf-8")
        with pytest.raises(SystemExit) as error:
            main(args)
        assert error.value.code == 1
