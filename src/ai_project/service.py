"""Application logic, independent of the CLI and provider implementation."""

import json
import time
from dataclasses import dataclass
from pathlib import Path

from ai_project.models import HRSupportTicket
from ai_project.providers import AIProvider


@dataclass(frozen=True)
class TicketResult:
    ticket: HRSupportTicket
    elapsed_seconds: float
    model: str
    usage: dict[str, int | None] | None


class AIService:
    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    def run(self, prompt: str) -> str:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Prompt must not be empty.")
        return self.provider.generate(prompt).text

    def parse_ticket(self, ticket_id: int, project_root: Path, version: str = "v1") -> TicketResult:
        if version not in ("v1", "v2"):
            raise ValueError("Supported prompt versions are v1 and v2.")
        records = json.loads((project_root / "data/tickets.json").read_text(encoding="utf-8-sig"))
        if not isinstance(records, list):
            raise ValueError("tickets.json must contain an array.")
        matches = [
            r
            for r in records
            if isinstance(r, dict) and type(r.get("id")) is int and r["id"] == ticket_id
        ]
        if len(matches) != 1:
            raise ValueError(f"Expected one ticket with ID {ticket_id}; found {len(matches)}.")
        text = matches[0].get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Ticket text must be a nonempty string.")
        prompt_path = project_root / "prompts" / f"{version}.txt"
        if not prompt_path.exists():
            prompt_path = project_root / "docs/prompts" / f"{version}.txt"
        system_prompt = prompt_path.read_text(encoding="utf-8-sig")
        if not system_prompt.strip():
            raise ValueError("System prompt must not be empty.")
        started = time.perf_counter()
        result = self.provider.generate(text, system_prompt=system_prompt)
        ticket = HRSupportTicket.model_validate_json(result.text)
        return TicketResult(ticket, time.perf_counter() - started, result.model, result.usage)
