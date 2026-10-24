"""Sequential ticket processing with atomic, incremental result persistence."""

import json
import os
import re
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ai_project.config import Settings
from ai_project.providers import ProviderError
from ai_project.service import AIService


def atomic_save(path: Path, payload: dict[str, Any], *, replace: bool) -> None:
    """Publish complete JSON on the same filesystem; never truncate the destination."""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        elif os.name == "nt":
            # Windows rename is atomic and fails if the destination already exists.
            os.rename(temporary, path)
        else:
            # Atomic no-clobber publication, including if another run won the race.
            os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def sanitized_error(exc: Exception, provider: str = "openrouter") -> str:
    """Never persist arbitrary exception bodies, ticket text, or credentials."""
    if isinstance(exc, ValidationError):
        return "Returned JSON failed HRSupportTicket validation."
    if isinstance(exc, ProviderError):
        name = "Ollama" if provider == "ollama" else "OpenRouter"
        status = re.search(r"\bHTTP ([45]\d{2})\b", str(exc))
        if status:
            return f"{name} request failed (HTTP {status.group(1)})."
        return f"{name} request failed or returned an unusable response."
    if isinstance(exc, OSError):
        return "Unable to read a required project file."
    if isinstance(exc, ValueError):
        return "Invalid ticket input or configuration."
    return "Unexpected ticket processing error."


def parse_all(
    service: AIService,
    settings: Settings,
    project_root: Path,
    output: Path,
    version: str = "v1",
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    if version != "v1":
        raise ValueError("Only prompt version v1 is supported.")
    output = output.resolve()
    protected = [
        project_root / name
        for name in (
            "data/tickets.json",
            "data/golden_set.json",
            "prompts/v1.txt",
            "docs/prompts/v1.txt",
        )
    ]
    if output in [path.resolve() for path in protected]:
        raise ValueError("Output must not replace datasets or prompts.")
    if output.exists() and not overwrite:
        raise FileExistsError("Output already exists; choose a new path or pass --overwrite.")
    records = json.loads((project_root / "data/tickets.json").read_text(encoding="utf-8-sig"))
    if not isinstance(records, list):
        raise ValueError("tickets.json must contain an array.")
    ids: list[int] = []
    for record in records:
        if not isinstance(record, dict) or type(record.get("id")) is not int:
            raise ValueError("Every ticket must have an integer ID.")
        ids.append(record["id"])
    if len(ids) != len(set(ids)):
        raise ValueError("Ticket IDs must be unique.")
    payload: dict[str, Any] = {
        "metadata": {
            "provider": settings.provider,
            "configured_model": settings.model,
            "prompt_version": version,
            "temperature": settings.temperature,
            "top_p": settings.top_p,
            "timestamp": datetime.now(UTC).isoformat(),
        },
        "total_tickets": len(ids),
        "completed": False,
        "results": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_save(output, payload, replace=overwrite)
    for ticket_id in ids:
        started = time.perf_counter()
        entry: dict[str, Any] = {
            "ticket_id": ticket_id,
            "provider": settings.provider,
            "temperature": settings.temperature,
            "top_p": settings.top_p,
            "status": "error",
            "output": None,
            "elapsed_seconds": 0.0,
            "model": settings.model,
            "usage": None,
            "error": None,
        }
        try:
            result = service.parse_ticket(ticket_id, project_root, version)
            entry.update(
                status="success",
                output=result.ticket.model_dump(mode="json"),
                elapsed_seconds=result.elapsed_seconds,
                model=result.model,
                usage=result.usage,
            )
        except Exception as exc:
            # KeyboardInterrupt/SystemExit deliberately propagate, preserving previous saves.
            entry.update(
                elapsed_seconds=time.perf_counter() - started,
                error=sanitized_error(exc, settings.provider),
            )
        payload["results"].append(entry)
        atomic_save(output, payload, replace=True)
    payload["completed"] = True
    atomic_save(output, payload, replace=True)
    return payload
