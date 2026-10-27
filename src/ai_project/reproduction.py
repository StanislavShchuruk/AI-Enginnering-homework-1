"""Sequential experiment orchestration using existing parsing and reporting modules."""

import os
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from ai_project.batch import parse_all
from ai_project.comparison import compare_runs
from ai_project.config import Settings
from ai_project.costs import PricingConfig
from ai_project.evaluation import evaluate, load_json, markdown
from ai_project.providers import create_provider
from ai_project.service import AIService


class Experiment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    provider: Literal["openrouter", "ollama"]
    prompt_version: Literal["v1", "v2"]
    temperature: float = Field(ge=0, le=2)
    top_p: float = Field(gt=0, le=1)
    output: str


def load_experiments(path: Path, root: Path) -> list[Experiment]:
    results_dir = root / "results"
    if results_dir.exists() and not results_dir.is_dir():
        raise ValueError("results/ must be a directory.")
    if results_dir.resolve() != root.resolve() / "results":
        raise ValueError("results/ must not redirect outside the project.")
    experiments = TypeAdapter(list[Experiment]).validate_python(load_json(path))
    if not experiments:
        raise ValueError("Experiment matrix must not be empty.")
    outputs: set[Path] = set()
    configurations: set[tuple[Any, ...]] = set()
    for experiment in experiments:
        relative = Path(experiment.output)
        output = (root / relative).resolve()
        if (relative.is_absolute() or relative.parent != Path("results")
                or output.parent != (root / "results").resolve()
                or output.suffix != ".json" or output.name.startswith(".")):
            raise ValueError("Prediction outputs must be named JSON files directly in results/.")
        configuration = (experiment.provider, experiment.prompt_version,
                         experiment.temperature, experiment.top_p)
        if output in outputs or configuration in configurations:
            raise ValueError("Experiment outputs and configurations must be unique.")
        outputs.add(output)
        configurations.add(configuration)
    return experiments


def experiment_settings(experiment: Experiment, values: dict[str, str]) -> Settings:
    loader = (Settings.openrouter_from_env if experiment.provider == "openrouter"
              else Settings.ollama_from_env)
    prefix = experiment.provider.upper()
    explicit = {**values, f"{prefix}_TEMPERATURE": str(experiment.temperature),
                f"{prefix}_TOP_P": str(experiment.top_p)}
    return replace(loader(explicit), temperature=experiment.temperature, top_p=experiment.top_p)


def validate_predictions(
    payload: Any, experiment: Experiment, golden: Any, ticket_ids: set[int]
) -> None:
    report = evaluate(payload, golden)
    metadata = report["metadata"]
    for key in ("provider", "prompt_version", "temperature", "top_p"):
        if metadata.get(key) != getattr(experiment, key):
            raise ValueError(f"Prediction metadata does not match experiment: {key}.")
    if not isinstance(metadata.get("configured_model"), str) or not metadata["configured_model"]:
        raise ValueError("Prediction configured_model is missing.")
    actual_ids = {r["ticket_id"] for r in payload["results"]
                  if isinstance(r, dict) and type(r.get("ticket_id")) is int}
    if (report["issues"] or actual_ids != ticket_ids
            or len(payload["results"]) != len(ticket_ids)
            or report["valid_output_rate"]["correct"] != len(ticket_ids)):
        raise ValueError("Prediction batch is incomplete, invalid, or contains failed tickets.")
    for record in payload["results"]:
        for key in ("provider", "prompt_version", "temperature", "top_p"):
            if key in record and record[key] != getattr(experiment, key):
                raise ValueError(f"Prediction record conflicts with experiment: {key}.")


def reproduce(root: Path, *, eval_only: bool = False, force: bool = False) -> None:
    if eval_only and force:
        raise ValueError("--eval-only and --force cannot be combined.")
    root = root.resolve()
    experiments = load_experiments(root / "experiments.json", root)
    try:
        pricing = PricingConfig.model_validate(
            load_json(root / "config/pricing.json")
        )
    except (OSError, ValueError) as exc:
        raise ValueError(
            "Cannot load config/pricing.json: file is missing, unreadable, or invalid. "
            "Expected models mapped to token rates, with optional power_watts and "
            "usd_per_kwh; all rates must be finite and nonnegative."
        ) from exc
    golden = load_json(root / "data/golden_set.json")
    empty = {"results": [], "total_tickets": 0, "completed": True}
    evaluate(empty, golden)
    if len(golden) != 40:
        raise ValueError("Reproduction requires the full 40-record Golden Set.")
    splits = {name: load_json(root / f"data/{name}_ids.json")
              for name in ("development", "holdout")}
    for name, count in (("development", 15), ("holdout", 25)):
        if not isinstance(splits[name], list):
            raise ValueError(f"{name} IDs must be an array.")
        evaluate(empty, golden, ids=splits[name])
        if len(splits[name]) != count:
            raise ValueError(f"{name} split must contain {count} IDs.")
    if set(splits["development"]) & set(splits["holdout"]):
        raise ValueError("Development and holdout IDs must not overlap.")
    tickets = load_json(root / "data/tickets.json")
    if not isinstance(tickets, list) or not tickets:
        raise ValueError("Tickets must be a nonempty array.")
    ticket_ids: set[int] = set()
    for ticket in tickets:
        if (not isinstance(ticket, dict) or type(ticket.get("id")) is not int
                or ticket["id"] in ticket_ids or not isinstance(ticket.get("text"), str)
                or not ticket["text"].strip()):
            raise ValueError("Tickets require unique integer IDs and nonempty text.")
        ticket_ids.add(ticket["id"])
    if not {case["id"] for case in golden} <= ticket_ids:
        raise ValueError("Golden IDs must reference input tickets.")

    report_dir = root / "results/reproduction"
    if (report_dir.resolve() != root / "results/reproduction"
            or report_dir.is_symlink()
            or (report_dir.exists() and not report_dir.is_dir())):
        raise ValueError("Report directory must be a local directory, not a symlink.")
    cached: dict[str, Any] = {}
    for experiment in experiments:
        path = root / experiment.output
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError(f"Invalid prediction output path: {experiment.output}")
        if path.exists() and (eval_only or not force):
            try:
                payload = load_json(path)
                validate_predictions(payload, experiment, golden, ticket_ids)
            except (ValueError, OSError) as exc:
                raise ValueError(f"{experiment.output}: invalid saved predictions; "
                                 "use --force to rerun inference.") from exc
            cached[experiment.output] = payload
        elif eval_only:
            raise ValueError(f"Missing predictions for --eval-only: {experiment.output}")
        else:
            prompt = root / f"prompts/{experiment.prompt_version}.txt"
            if not prompt.exists():
                prompt = root / f"docs/prompts/{experiment.prompt_version}.txt"
            if not prompt.read_text(encoding="utf-8-sig").strip():
                raise ValueError(f"Empty prompt: {experiment.prompt_version}")

    # Read settings only when inference is needed. Never mutate the process environment.
    settings: dict[str, Settings] = {}
    if any(e.output not in cached for e in experiments):
        values = {key: value for key, value in dotenv_values(root / ".env").items()
                  if value is not None}
        values.update(os.environ)
        for experiment in experiments:
            if experiment.output not in cached:
                settings[experiment.output] = experiment_settings(experiment, values)

    # Validate every report destination before inference or report writes.
    destinations = [report_dir / "comparison.md"]
    for experiment in experiments:
        scopes = ["full"]
        if experiment.temperature == 0 and experiment.top_p == 1:
            scopes += list(splits)
        destinations += [report_dir / f"{Path(experiment.output).stem}_{scope}.md"
                         for scope in scopes]
    if len(set(destinations)) != len(destinations):
        raise ValueError("Report paths collide.")
    for path in destinations:
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError(f"Invalid report destination: {path.name}")
    runs: list[tuple[str, Any]] = []
    reports: dict[Path, str] = {}
    for experiment in experiments:
        payload = cached.get(experiment.output)
        if payload is None:
            print(f"Running {experiment.output}", flush=True)
            try:
                current = settings[experiment.output]
                payload = parse_all(AIService(create_provider(current)), current, root,
                                    root / experiment.output, experiment.prompt_version,
                                    overwrite=force)
                validate_predictions(payload, experiment, golden, ticket_ids)
            except Exception as exc:
                raise ValueError(
                    f"Experiment failed: {experiment.output}; workflow incomplete. "
                    "Inspect the saved batch before rerunning."
                ) from exc
        else:
            print(f"Using validated predictions: {experiment.output}", flush=True)
        runs.append((experiment.output, payload))
        scopes = {"full": None}
        if experiment.temperature == 0 and experiment.top_p == 1:
            scopes.update(splits)
        for scope, ids in scopes.items():
            report_path = report_dir / f"{Path(experiment.output).stem}_{scope}.md"
            reports[report_path] = markdown(evaluate(payload, golden, ids=ids))
    reports[report_dir / "comparison.md"] = compare_runs(runs, golden, pricing.models, pricing)
    report_dir.mkdir(parents=True, exist_ok=True)
    for path, content in reports.items():
        path.write_text(content, encoding="utf-8")
    print(f"Reproduction complete: {len(runs)} runs; {len(reports)} reports in {report_dir}")
