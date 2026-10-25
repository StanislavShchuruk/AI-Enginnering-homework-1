"""Command-line entry point."""

import argparse
import json
import logging
import sys
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from ai_project.batch import parse_all
from ai_project.comparison import compare_runs
from ai_project.config import Settings
from ai_project.costs import Electricity, TokenPrices
from ai_project.evaluation import evaluate, load_json, markdown, summary
from ai_project.providers import ProviderError, create_provider
from ai_project.reproduction import reproduce
from ai_project.service import AIService


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "reproduce":
        return reproduce_main(argv[1:])
    if argv and argv[0] == "compare":
        return compare_main(argv[1:])
    if argv and argv[0] == "eval":
        return eval_main(argv[1:])
    if argv and argv[0] == "parse-all":
        return parse_all_main(argv[1:])
    if argv and argv[0] == "parse-ticket":
        return parse_ticket_main(argv[1:])
    parser = argparse.ArgumentParser(
        description="Run the offline mock, or parse HR tickets with OpenRouter or Ollama.",
        epilog="OpenRouter: ai-project parse-ticket --ticket-id 1 --prompt-version v1",
    )
    parser.add_argument("prompt", help="Text to send to the configured provider")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        service = AIService(create_provider(Settings.from_env()))
        print(service.run(args.prompt))
    except ValueError as exc:
        parser.error(str(exc))
    return 0


def compare_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Compare saved prediction runs entirely offline.")
    parser.add_argument("--predictions", type=Path, nargs="+", required=True)
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pricing", type=Path, help="Model-keyed JSON token prices in USD per 1M.")
    parser.add_argument("--power-watts", type=float)
    parser.add_argument("--electricity-usd-per-kwh", type=float)
    args = parser.parse_args(argv)
    try:
        inputs = [*args.predictions, args.golden]
        if args.pricing:
            inputs.append(args.pricing)
        if any(path.suffix.lower() != ".json" or path.name.startswith(".env") for path in inputs):
            raise ValueError("Predictions, golden data, and pricing must be JSON files.")
        if args.output.suffix.lower() != ".md":
            raise ValueError("Comparison output must end in .md.")
        if args.output.exists() or args.output.resolve() in [path.resolve() for path in inputs]:
            raise ValueError("Comparison output must be a new file; existing files are protected.")
        prices = (
            TypeAdapter(dict[str, TokenPrices]).validate_python(load_json(args.pricing))
            if args.pricing else {}
        )
        electricity = Electricity(
            power_watts=args.power_watts, usd_per_kwh=args.electricity_usd_per_kwh
        )
        golden = load_json(args.golden)
        runs = [(str(path), load_json(path)) for path in args.predictions]
        content = compare_runs(runs, golden, prices, electricity)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(content)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Comparison failed: {exc}\n")
    print(f"Saved comparison to {args.output}")
    return 0


def eval_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Evaluate saved predictions entirely offline.")
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--ids-file", type=Path, help="JSON array of golden IDs to score.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing report.")
    args = parser.parse_args(argv)
    try:
        ids = None
        if args.ids_file is not None:
            ids = load_json(args.ids_file)
            if not isinstance(ids, list):
                raise ValueError("IDs file must contain a JSON array of integers.")
        if args.output:
            if args.output.suffix.lower() not in (".json", ".md"):
                raise ValueError("Output must end in .json or .md.")
            if args.output.resolve() in (
                args.predictions.resolve(),
                args.golden.resolve(),
                args.ids_file.resolve() if args.ids_file is not None else None,
            ):
                raise ValueError("Output cannot replace predictions, golden data, or IDs file.")
            if args.output.exists() and not args.overwrite:
                raise ValueError("Output exists; choose a new path or pass --overwrite.")
        report = evaluate(load_json(args.predictions), load_json(args.golden), ids=ids)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            content = (
                markdown(report)
                if args.output.suffix.lower() == ".md"
                else (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
            )
            with args.output.open("w" if args.overwrite else "x", encoding="utf-8") as stream:
                stream.write(content)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Evaluation failed: {exc}\n")
    print(summary(report))
    if args.output:
        print(f"Saved evaluation to {args.output}")
    return 0


def parse_all_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Parse all HR tickets sequentially via the selected provider."
    )
    parser.add_argument("--prompt-version", choices=["v1", "v2"], default="v1")
    parser.add_argument("--provider", choices=["openrouter", "ollama"], default="openrouter")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        settings = provider_settings(args.provider)
        payload = parse_all(
            AIService(create_provider(settings)),
            settings,
            args.project_root,
            args.output,
            args.prompt_version,
            overwrite=args.overwrite,
        )
    except FileExistsError:
        parser.exit(1, "Output exists; choose a new path or pass --overwrite.\n")
    except (ValueError, OSError):
        parser.exit(1, "Batch setup or result persistence failed; check input and output paths.\n")
    failures = sum(item["status"] == "error" for item in payload["results"])
    print(f"Saved {len(payload['results'])} results ({failures} errors) to {args.output}")
    return 1 if failures else 0


def parse_ticket_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Parse one HR ticket through the selected provider."
    )
    parser.add_argument("--ticket-id", type=int, required=True)
    parser.add_argument("--provider", choices=["openrouter", "ollama"], default="openrouter")
    parser.add_argument("--prompt-version", choices=["v1", "v2"], default="v1")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        service = AIService(create_provider(provider_settings(args.provider)))
        result = service.parse_ticket(args.ticket_id, args.project_root, args.prompt_version)
    except ValidationError as exc:
        fields = ", ".join(".".join(map(str, e["loc"])) or "root" for e in exc.errors())
        parser.exit(1, f"Returned JSON failed HRSupportTicket validation: {fields}\n")
    except (ValueError, OSError, ProviderError) as exc:
        parser.exit(1, f"{exc}\n")
    print(
        json.dumps(
            {
                "ticket": result.ticket.model_dump(mode="json"),
                "elapsed_seconds": round(result.elapsed_seconds, 3),
                "model": result.model,
                "usage": result.usage,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def provider_settings(provider: str) -> Settings:
    if provider == "ollama":
        return Settings.ollama_from_env()
    return Settings.openrouter_from_env()



def reproduce_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Reproduce the configured experiments sequentially."
    )
    parser.add_argument("--eval-only", action="store_true",
                        help="Regenerate reports from saved predictions without provider calls.")
    parser.add_argument("--force", action="store_true",
                        help="Rerun inference and overwrite prediction outputs.")
    args = parser.parse_args(argv)
    if args.eval_only and args.force:
        parser.error("--eval-only and --force cannot be combined.")
    try:
        reproduce(Path.cwd(), eval_only=args.eval_only, force=args.force)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Reproduction failed: {exc}\n")
    return 0
