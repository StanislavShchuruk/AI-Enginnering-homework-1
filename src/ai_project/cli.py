"""Command-line entry point."""

import argparse
import json
import logging
import sys
from pathlib import Path

from pydantic import ValidationError

from ai_project.batch import parse_all
from ai_project.config import Settings
from ai_project.providers import ProviderError, create_provider
from ai_project.service import AIService


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
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


def parse_all_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Parse all HR tickets sequentially via the selected provider."
    )
    parser.add_argument("--prompt-version", choices=["v1"], default="v1")
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
    parser.add_argument("--prompt-version", choices=["v1"], default="v1")
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
