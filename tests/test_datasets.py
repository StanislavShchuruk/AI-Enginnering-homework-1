"""Read-only checks for the manually maintained dataset and golden labels."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from ai_project.models import HRSupportTicket

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def load_records(filename: str) -> list[dict[str, Any]]:
    path = DATA_DIR / filename
    try:
        records = json.loads(
            path.read_text(encoding="utf-8-sig"), object_pairs_hook=reject_duplicate_keys
        )
    except (OSError, ValueError) as exc:
        pytest.fail(f"{filename}: cannot read valid JSON: {exc}", pytrace=False)
    assert isinstance(records, list), f"{filename}: top level must be a JSON array"
    for index, record in enumerate(records):
        assert isinstance(record, dict), f"{filename}[{index}]: expected an object"
    return records


def record_ids(records: list[dict[str, Any]], filename: str) -> list[int]:
    ids: list[int] = []
    for index, record in enumerate(records):
        value = record.get("id")
        assert type(value) is int, f"{filename}[{index}].id: expected an integer (not bool)"
        ids.append(value)
    assert len(ids) == len(set(ids)), f"{filename}: ticket IDs must be unique"
    return ids


@pytest.mark.parametrize("filename,count", [("tickets.json", 100), ("golden_set.json", 40)])
def test_record_count(filename: str, count: int) -> None:
    records = load_records(filename)
    assert len(records) == count, f"{filename}: expected {count} records, got {len(records)}"


@pytest.mark.parametrize("filename", ["tickets.json", "golden_set.json"])
def test_unique_integer_ids(filename: str) -> None:
    record_ids(load_records(filename), filename)


def test_golden_ids_match_input_tickets() -> None:
    input_ids = set(record_ids(load_records("tickets.json"), "tickets.json"))
    golden_ids = set(record_ids(load_records("golden_set.json"), "golden_set.json"))
    missing = golden_ids - input_ids
    assert not missing, f"Golden IDs missing from tickets.json: {sorted(missing)}"


def test_expected_outputs_validate() -> None:
    errors: list[str] = []
    for index, case in enumerate(load_records("golden_set.json")):
        label = f"golden_set.json[{index}] (id={case.get('id')!r})"
        if "expected" not in case:
            errors.append(f"{label}: missing expected output")
            continue
        try:
            HRSupportTicket.model_validate(case["expected"])
        except ValidationError as exc:
            errors.append(f"{label}: {exc}")
    assert not errors, "Invalid golden outputs:\n" + "\n".join(errors)


def load_json(filename: str) -> Any:
    return json.loads(
        (DATA_DIR / filename).read_text(encoding="utf-8-sig"),
        object_pairs_hook=reject_duplicate_keys,
    )


def test_ticket_shape_and_sequential_ids() -> None:
    tickets = load_records("tickets.json")
    assert record_ids(tickets, "tickets.json") == list(range(1, 101))
    for ticket in tickets:
        assert set(ticket) == {"id", "text"}
        assert isinstance(ticket["text"], str) and ticket["text"].strip()
    assert len({ticket["text"] for ticket in tickets}) == 100


def test_golden_splits() -> None:
    development = load_json("development_ids.json")
    holdout = load_json("holdout_ids.json")
    for ids, count in [(development, 15), (holdout, 25)]:
        assert isinstance(ids, list) and len(ids) == count
        assert all(type(value) is int for value in ids)
        assert len(set(ids)) == count
    assert not set(development) & set(holdout)
    cases = load_records("golden_set.json")
    assert set(development) | set(holdout) == {case["id"] for case in cases}
    assert {1, 2, 7, 10, 12, 14, 17, 18, 23, 24} <= set(development)
    for case in cases:
        assert set(case) == {"id", "expected"}


def test_golden_coverage() -> None:
    labels = [case["expected"] for case in load_records("golden_set.json")]
    assert {label["category"] for label in labels} == {
        "authentication", "absence", "attendance", "shifts", "payroll",
        "employee_profile", "technical", "other",
    }
    assert {label["priority"] for label in labels} == {"low", "medium", "high", "unknown"}
    assert {label["requires_support"] for label in labels} == {True, False}
