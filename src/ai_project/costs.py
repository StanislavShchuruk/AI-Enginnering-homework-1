"""Explicit offline cost estimates for complete saved batches."""

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TokenPrices(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    input_usd_per_million: float = Field(ge=0, strict=True)
    output_usd_per_million: float = Field(ge=0, strict=True)


class Electricity(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    power_watts: float | None = Field(default=None, ge=0, strict=True)
    usd_per_kwh: float | None = Field(default=None, ge=0, strict=True)


def nonnegative_number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def estimate_cost(
    predictions: dict[str, Any],
    prices: dict[str, TokenPrices],
    electricity: Electricity,
) -> dict[str, Any]:
    """Scale measured whole-batch costs to 1000 attempted documents, including failures."""
    metadata = predictions.get("metadata", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    provider = metadata.get("provider")
    model = metadata.get("configured_model")
    records = predictions["results"]
    count = len(records)
    cost: dict[str, Any] = {
        "api_usd_per_1000": 0.0 if provider == "ollama" else None,
        "electricity_usd_per_1000": None,
        "reason": "",
    }
    if provider not in ("openrouter", "ollama"):
        cost["reason"] = "Unknown provider."
        return cost
    if (
        not count
        or predictions.get("completed") is not True
        or predictions["total_tickets"] != count
    ):
        cost["reason"] = "Cost requires a nonempty complete batch with matching record count."
        return cost
    for record in records:
        if not isinstance(record, dict) or record.get("provider", provider) != provider:
            cost["reason"] = "Missing record or conflicting provider metadata."
            return cost
    if provider == "openrouter":
        price = prices.get(model) if isinstance(model, str) else None
        if price is None:
            cost["reason"] = "No explicit pricing for configured model."
            return cost
        prompt_tokens = completion_tokens = 0
        for record in records:
            # Returned provider model names may be aliases of the configured model.
            usage = record.get("usage")
            if not isinstance(usage, dict) or any(
                type(usage.get(key)) is not int or usage[key] < 0
                for key in ("prompt_tokens", "completion_tokens")
            ):
                cost["reason"] = (
                    "Prompt/completion usage missing or invalid for one or more records."
                )
                return cost
            prompt_tokens += usage["prompt_tokens"]
            completion_tokens += usage["completion_tokens"]
        cost["api_usd_per_1000"] = (
            (
                prompt_tokens * price.input_usd_per_million
                + completion_tokens * price.output_usd_per_million
            )
            / 1_000_000
            * 1000
            / count
        )
        cost["reason"] = "Configured-model token rates applied to all recorded usage."
    else:
        if electricity.power_watts is None or electricity.usd_per_kwh is None:
            cost["reason"] = "Average power or electricity price not configured."
            return cost
        if any(not nonnegative_number(r.get("elapsed_seconds")) for r in records):
            cost["reason"] = "Elapsed time missing or invalid for one or more records."
            return cost
        seconds = sum(r["elapsed_seconds"] for r in records)
        cost["electricity_usd_per_1000"] = (
            electricity.power_watts / 1000 * seconds / 3600 * electricity.usd_per_kwh * 1000 / count
        )
        cost["reason"] = "Configured average power applied to summed record elapsed time."
    return cost
