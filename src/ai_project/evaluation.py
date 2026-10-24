"""Offline evaluation of persisted parse-all results; no provider configuration needed."""

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ai_project.models import HRSupportTicket

FIELDS = (
    "category",
    "priority",
    "application",
    "language",
    "requires_support",
    "details.error_code",
    "details.error_message",
)
TEXT_FIELDS = {"application", "details.error_code", "details.error_message"}
NOTES = {
    "normalization": "Nullable text uses strip().casefold(); null differs from empty string. "
    "Enums and booleans compare exactly. No punctuation or internal whitespace changes.",
    "scoring": "Every golden ID is in every field denominator. Missing, failed, invalid, "
    "or duplicate-ID predictions are incorrect for all fields. Extra IDs affect validity only.",
    "validity": "Valid successful HRSupportTicket outputs / max(total_tickets, result count). "
    "Absent batch entries count as invalid; malformed entries and failed outputs are invalid.",
    "percentiles": "Linear interpolation on sorted samples at index (n-1)*p (type 7). "
    "Latency includes success-status records with finite nonnegative numeric elapsed_seconds, "
    "even if their output is invalid; booleans are excluded. No samples yields null.",
}
EXCLUDED = {
    "summary": "Free-text summaries can express the same meaning with different wording.",
    "suggested_actions": "Multiple valid action selections, phrasings, and orders are possible.",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower = math.floor(index)
    upper = math.ceil(index)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def metric(correct: int, total: int) -> dict[str, Any]:
    return {
        "correct": correct,
        "total": total,
        "accuracy_percent": 100 * correct / total if total else None,
    }


def field_value(output: dict[str, Any], field: str) -> Any:
    value: Any = output
    for part in field.split("."):
        value = value[part]
    return value


def evaluate(predictions: Any, golden: Any) -> dict[str, Any]:
    if not isinstance(predictions, dict) or not isinstance(predictions.get("results"), list):
        raise ValueError("Predictions must be a parse-all object with a results array.")
    total = predictions.get("total_tickets")
    if type(total) is not int or total < 0:
        raise ValueError("total_tickets must be a nonnegative integer.")
    if not isinstance(golden, list) or not golden:
        raise ValueError("Golden data must be a nonempty array.")
    expected: dict[int, dict[str, Any]] = {}
    for record in golden:
        if not isinstance(record, dict) or type(record.get("id")) is not int:
            raise ValueError("Every golden record needs an integer id.")
        ticket_id = record["id"]
        if ticket_id in expected:
            raise ValueError(f"Duplicate golden ID: {ticket_id}")
        try:
            expected[ticket_id] = HRSupportTicket.model_validate(record.get("expected")).model_dump(
                mode="json"
            )
        except ValidationError as exc:
            raise ValueError(f"Invalid golden output for ID {ticket_id}.") from exc

    records = predictions["results"]
    issues: list[str] = []
    ids = Counter(
        r["ticket_id"] for r in records if isinstance(r, dict) and type(r.get("ticket_id")) is int
    )
    duplicates = sorted(key for key, count in ids.items() if count > 1)
    if duplicates:
        issues.append(f"Duplicate prediction IDs: {duplicates}")
    if total != len(records):
        issues.append(f"total_tickets={total} differs from result count={len(records)}.")
    if predictions.get("completed") is not True:
        issues.append("Batch is incomplete or completed is missing/invalid.")
    valid: dict[int, dict[str, Any]] = {}
    valid_count = 0
    latencies: list[float] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            issues.append(f"Result {index}: expected an object.")
            continue
        ticket_id = record.get("ticket_id")
        identity_valid = type(ticket_id) is int
        if not identity_valid:
            issues.append(f"Result {index}: missing/invalid ticket_id.")
        status = record.get("status")
        if status not in ("success", "error"):
            issues.append(f"Result {index}: missing/invalid status.")
        if status != "success":
            continue
        elapsed = record.get("elapsed_seconds")
        if type(elapsed) in (float, int) and math.isfinite(elapsed) and elapsed >= 0:
            latencies.append(float(elapsed))
        else:
            issues.append(f"Result {index}: invalid elapsed_seconds; excluded from latency.")
        try:
            output = HRSupportTicket.model_validate(record.get("output")).model_dump(mode="json")
        except ValidationError:
            issues.append(f"Result {index}: invalid HRSupportTicket output.")
            continue
        if identity_valid:
            valid_count += 1
            if ids[ticket_id] == 1:
                valid[ticket_id] = output

    missing = sorted(set(expected) - set(ids))
    if missing:
        issues.append(f"Missing golden predictions: {missing}")
    counts = dict.fromkeys(FIELDS, 0)
    mismatches: list[dict[str, Any]] = []
    for ticket_id, reference in expected.items():
        actual_output = valid.get(ticket_id)
        for field in FIELDS:
            wanted = field_value(reference, field)
            actual = field_value(actual_output, field) if actual_output is not None else None
            normalized_wanted = wanted
            normalized_actual = actual
            if field in TEXT_FIELDS:
                normalized_wanted = wanted.strip().casefold() if wanted is not None else None
                normalized_actual = actual.strip().casefold() if actual is not None else None
            if actual_output is not None and normalized_actual == normalized_wanted:
                counts[field] += 1
            else:
                mismatches.append(
                    {
                        "ticket_id": ticket_id,
                        "field": field,
                        "expected": wanted,
                        "actual": actual,
                        "actual_missing": actual_output is None,
                    }
                )
    metadata = predictions.get("metadata", {})
    if not isinstance(metadata, dict):
        issues.append("metadata must be an object.")
        metadata = {}
    return {
        "metadata": metadata,
        "record_metadata": [
            {
                key: r[key]
                for key in (
                    "ticket_id",
                    "provider",
                    "model",
                    "prompt_version",
                    "temperature",
                    "top_p",
                )
                if key in r
            }
            for r in records
            if isinstance(r, dict)
        ],
        "input_prediction_count": len(records),
        "declared_total": total,
        "golden_count": len(expected),
        "missing_golden_ids": missing,
        "duplicate_prediction_ids": duplicates,
        "issues": issues,
        "valid_output_rate": metric(valid_count, max(total, len(records))),
        "fields": {field: metric(counts[field], len(expected)) for field in FIELDS},
        "latency_seconds": {
            "samples": len(latencies),
            "p50": percentile(latencies, 0.5),
            "p95": percentile(latencies, 0.95),
        },
        "mismatches": mismatches,
        "excluded_fields": EXCLUDED,
        "notes": NOTES,
        "judge": "No LLM judge is used.",
    }


def cell(value: Any) -> str:
    """JSON distinguishes null, empty strings, and literal missing-value text."""
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", "&#124;")
        .replace("\\", "&#92;")
        .replace("`", "&#96;")
        .replace("\r", "&#13;")
        .replace("\n", "<br>")
    )


def summary(report: dict[str, Any]) -> str:
    rate = report["valid_output_rate"]
    lines = [
        f"Valid outputs: {rate['correct']}/{rate['total']} "
        f"({format_percent(rate['accuracy_percent'])})"
    ]
    for field, score in report["fields"].items():
        lines.append(
            f"{field}: {score['correct']}/{score['total']} "
            f"({format_percent(score['accuracy_percent'])})"
        )
    latency = report["latency_seconds"]
    lines.append(
        f"Latency seconds: p50={latency['p50']}, p95={latency['p95']} (n={latency['samples']})"
    )
    lines.append(f"Mismatches: {len(report['mismatches'])}; data issues: {len(report['issues'])}")
    return "\n".join(lines)


def format_percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}%"


def markdown(report: dict[str, Any]) -> str:
    rate = report["valid_output_rate"]
    metadata = report["metadata"]
    temperature = cell(metadata["temperature"]) if "temperature" in metadata else "Not recorded"
    top_p = cell(metadata["top_p"]) if "top_p" in metadata else "Not recorded"
    lines = [
        "# Offline evaluation",
        "",
        f"Temperature: {temperature}; top_p: {top_p}.",
        "",
        f"Golden records: {report['golden_count']}. "
        f"Input predictions: {report['input_prediction_count']}. "
        f"Declared total: {report['declared_total']}.",
        "",
        f"Valid-output rate: {rate['correct']}/{rate['total']} "
        f"({format_percent(rate['accuracy_percent'])}).",
        "",
        "## Field accuracy",
        "",
        "| Field | Correct/total | Accuracy |",
        "| --- | --- | --- |",
    ]
    for field, score in report["fields"].items():
        lines.append(
            f"| {field} | {score['correct']}/{score['total']} | "
            f"{format_percent(score['accuracy_percent'])} |"
        )
    latency = report["latency_seconds"]
    lines += [
        "",
        "## Latency (seconds)",
        "",
        f"Samples: {latency['samples']}; p50: {cell(latency['p50'])}; p95: {cell(latency['p95'])}.",
        "",
        "## Mismatches",
        "",
        "`null` means explicit null; JSON quotes preserve empty strings. "
        "**MISSING/INVALID** means no usable unique prediction.",
        "",
        "| Ticket ID | Field | Expected | Actual |",
        "| --- | --- | --- | --- |",
    ]
    for item in report["mismatches"]:
        actual = "**MISSING/INVALID**" if item["actual_missing"] else cell(item["actual"])
        lines.append(
            f"| {item['ticket_id']} | {item['field']} | {cell(item['expected'])} | {actual} |"
        )
    if not report["mismatches"]:
        lines.append("| — | — | No mismatches | — |")
    lines += ["", "## Data issues", ""]
    lines += [f"- {cell(issue)}" for issue in report["issues"]] or ["None."]
    lines += ["", "## Scoring and excluded fields", ""]
    lines += [f"- {name}: {text}" for name, text in report["notes"].items()]
    lines += [f"- {name} excluded: {text}" for name, text in EXCLUDED.items()]
    lines += ["- No LLM judge is used.", ""]
    return "\n".join(lines)
