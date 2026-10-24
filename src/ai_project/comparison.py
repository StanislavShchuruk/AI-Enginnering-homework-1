"""Multi-run reporting using the unchanged offline evaluator."""

from typing import Any

from ai_project.costs import Electricity, TokenPrices, estimate_cost
from ai_project.evaluation import EXCLUDED, FIELDS, NOTES, cell, evaluate, format_percent


def compare_runs(
    runs: list[tuple[str, Any]],
    golden: Any,
    prices: dict[str, TokenPrices],
    electricity: Electricity,
) -> str:
    lines = [
        "# Offline run comparison",
        "",
        "All costs are USD estimates per 1,000 attempted documents; token estimates are "
        "not actual billed charges. N/A means unavailable, not zero.",
        "",
        "| Run | Provider | Model (configured) | Prompt | Temperature | top_p | "
        "Evaluated documents (golden) | Input records | Field accuracy (correct/total) | "
        "Valid-output rate | p50 (s) | p95 (s) | API fee / 1,000 | Electricity / 1,000 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    reports = []
    details = []
    for index, (name, predictions) in enumerate(runs, 1):
        report = evaluate(predictions, golden)
        reports.append(report)
        metadata = report["metadata"]
        cost = estimate_cost(predictions, prices, electricity)
        correct = sum(score["correct"] for score in report["fields"].values())
        total = sum(score["total"] for score in report["fields"].values())
        rate = report["valid_output_rate"]
        latency = report["latency_seconds"]
        values = [
            str(index),
            *(
                cell(metadata[key]) if key in metadata else "N/A"
                for key in (
                    "provider",
                    "configured_model",
                    "prompt_version",
                    "temperature",
                    "top_p",
                )
            ),
            str(report["golden_count"]),
            str(report["input_prediction_count"]),
            f"{correct}/{total} ({format_percent(100 * correct / total)})",
            f"{rate['correct']}/{rate['total']} ({format_percent(rate['accuracy_percent'])})",
            *("N/A" if latency[key] is None else f"{latency[key]:.6f}" for key in ("p50", "p95")),
            *(
                "N/A" if cost[key] is None else f"${cost[key]:.6f}"
                for key in ("api_usd_per_1000", "electricity_usd_per_1000")
            ),
        ]
        lines.append("| " + " | ".join(values) + " |")
        details += [f"- Run {index}: {cell(name)}. {cost['reason']}"]
        details += [f"  - Data issue: {cell(issue)}" for issue in report["issues"]]
        # Make returned-model differences visible without recreating record JSON tables.
        models = sorted({str(r["model"]) for r in report["record_metadata"] if "model" in r})
        if models:
            details.append(f"  - Recorded response models: {cell(', '.join(models))}.")
        for key in ("provider", "temperature", "top_p", "prompt_version"):
            if any(key in r and r[key] != metadata.get(key) for r in report["record_metadata"]):
                details.append(
                    f"  - Recorded {key} differs from run metadata; table uses run metadata."
                )
    lines += [
        "",
        "## Field accuracy",
        "",
        "| Field | " + " | ".join(f"Run {i}" for i in range(1, len(reports) + 1)) + " |",
        "| --- | " + " | ".join("---" for _ in reports) + " |",
    ]
    for field in FIELDS:
        scores = [r["fields"][field] for r in reports]
        lines.append(
            "| "
            + field
            + " | "
            + " | ".join(
                f"{s['correct']}/{s['total']} ({format_percent(s['accuracy_percent'])})"
                for s in scores
            )
            + " |"
        )
    lines += ["", "## Runs and data issues", "", *details, "", "## Pricing assumptions", ""]
    lines += [
        f"- {cell(model)}: input ${price.input_usd_per_million:g}/1M tokens; "
        f"output ${price.output_usd_per_million:g}/1M tokens."
        for model, price in prices.items()
    ] or ["- No token prices configured."]
    lines += [
        f"- Local average power: {electricity.power_watts} W; electricity: "
        f"{electricity.usd_per_kwh} USD/kWh. None means not configured.",
        "",
        "## Methodology and limitations",
        "",
        "- Field accuracy sums correct counts across the seven scored fields and divides by "
        "seven times the golden document count. All runs use the same golden set.",
        *[f"- {text}" for text in NOTES.values()],
        *[f"- {field} excluded: {text}" for field, text in EXCLUDED.items()],
        "- Hosted estimate: (prompt tokens × input price + completion tokens × output price) "
        "/ 1,000,000 × 1,000 / input record count. Both usage counts must be recorded for "
        "every record, including failures; missing usage is never assumed zero. Rates are "
        "explicitly assigned to the configured model, including returned model aliases.",
        "- Local API fee is $0. Electricity estimate: watts / 1,000 × summed elapsed seconds "
        "/ 3,600 × USD/kWh × 1,000 / input record count. All records, including failures, "
        "need valid timing. Costs require a complete nonempty batch with matching counts.",
        "- Local inference has hardware, energy, and operating costs. Electricity excludes "
        "idle time outside records and hardware amortization. Summed sequential processing "
        "time is an approximation, not a power measurement or parallel wall-clock time.",
        "- Token estimates exclude unrecorded retries, discounts, caching, routing surcharges, "
        "taxes, and other billing adjustments. Failed requests may incur unrecorded charges. "
        "Latency excludes failures, whereas cost includes recorded failed attempts. "
        "Model aliases and hardware/load differences can limit comparability.",
        "- No .env is read, no models are called, and no LLM judge is used.",
        "",
    ]
    return "\n".join(lines)
