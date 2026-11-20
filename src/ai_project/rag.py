"""Grounded generation and structural citation validation (not entailment scoring)."""

import argparse
import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from ai_project.chunking import TOKEN_COUNTER, count_tokens
from ai_project.config import Settings
from ai_project.providers import AIProvider, OllamaProvider, ProviderError
from ai_project.reranking import DEFAULT_BATCH_SIZE, DEFAULT_RERANKER, CrossEncoderReranker
from ai_project.retrieval import ACCESS_GROUPS, DEFAULT_INDEX, IndexChunk, OllamaEmbedder, search

PROMPT_PATH = Path("docs/prompts/rag-v1.txt")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Claim(StrictModel):
    text: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Claim must not be blank")
        return value


class RagAnswer(StrictModel):
    status: Literal["answered", "partial", "unavailable"]
    claims: list[Claim]
    missing_information: str | None

    @model_validator(mode="after")
    def check_status(self) -> "RagAnswer":
        gap = bool(self.missing_information and self.missing_information.strip())
        if self.status == "answered" and (not self.claims or self.missing_information is not None):
            raise ValueError("Answered requires claims and no gap")
        if self.status == "partial" and (not self.claims or not gap):
            raise ValueError("Partial requires claims and a gap")
        if self.status == "unavailable" and (self.claims or not gap):
            raise ValueError("Unavailable requires no claims and a gap")
        return self


class RagOllamaProvider(OllamaProvider):
    response_model = RagAnswer
    schema_name = "peopleflow_answer"


class RagResponseError(ValueError):
    """Retain invalid generation for offline review without displaying it as an answer."""

    def __init__(self, artifact: dict[str, Any], message: str) -> None:
        super().__init__(message)
        self.artifact = artifact


def context_json(sources: list[dict[str, Any]]) -> str:
    return json.dumps(sources, ensure_ascii=False, separators=(",", ":"))


def assemble_context(
    hits: list[dict[str, Any]],
    access_groups: list[str],
    token_budget: int = 3200,
) -> tuple[list[dict[str, Any]], int]:
    """Greedily add whole chunks in returned rank order; skip those that do not fit."""
    if type(token_budget) is not int or token_budget < 2:
        raise ValueError("Context token budget must be an integer of at least 2")
    if not access_groups or set(access_groups) - ACCESS_GROUPS:
        raise ValueError("Known access groups required")
    # Check every hit before using any of them, even hits too large for the budget.
    for hit in hits:
        group = hit.get("metadata", {}).get("access_group")
        if group not in access_groups or hit.get("access_group", group) != group:
            raise ValueError("Unauthorized chunk blocked before generation")
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hit in hits:
        chunk = IndexChunk.model_validate({k: hit[k] for k in IndexChunk.model_fields if k in hit})
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        source = {"source_id": f"S{len(sources) + 1}", **chunk.model_dump(mode="json")}
        if count_tokens(context_json([*sources, source])) <= token_budget:
            sources.append(source)
    return sources, count_tokens(context_json(sources))


def validate_citations(answer: RagAnswer, sources: list[dict[str, Any]]) -> None:
    """Validate references only; passage support and atomicity are Task 9 concerns."""
    allowed = {source["source_id"] for source in sources}
    if any(source_id not in allowed for claim in answer.claims for source_id in claim.source_ids):
        raise ValueError("Answer cited a source absent from the generation context")


def render_answer(answer: RagAnswer, sources: list[dict[str, Any]]) -> str:
    validate_citations(answer, sources)
    mapping = {source["source_id"]: source for source in sources}
    lines: list[str] = []
    for claim in answer.claims:
        labels = []
        for source_id in dict.fromkeys(claim.source_ids):
            source = mapping[source_id]
            section = " > ".join(source["section_path"]) or "(no section)"
            version = f"; version {source['version']}" if source["version"] else ""
            labels.append(f"[{source_id}: {source['document_title']} — {section}{version}]")
        lines.append(f"{claim.text} {' '.join(labels)}")
    if answer.missing_information:
        lines.append(answer.missing_information)
    return "\n\n".join(lines)


def generate_answer(
    question: str,
    hits: list[dict[str, Any]],
    provider: AIProvider,
    *,
    access_groups: list[str],
    token_budget: int = 3200,
    prompt_path: Path = PROMPT_PATH,
) -> dict[str, Any]:
    if not question.strip():
        raise ValueError("Question must not be blank")
    sources, tokens = assemble_context(hits, access_groups, token_budget)
    system = prompt_path.read_text(encoding="utf-8")
    # Keep the exact counted serialization in the request, including metadata and wrappers.
    request = '{"question":' + json.dumps(question, ensure_ascii=False) + ',"excerpts":'
    request += context_json(sources) + "}"
    started = time.perf_counter()
    generated = provider.generate(request, system_prompt=system)
    artifact = {
        "question": question,
        "sources": sources,
        "context_tokens": tokens,
        "context_token_budget": token_budget,
        "token_counter": TOKEN_COUNTER,
        "retrieved_chunk_ids": [hit["chunk_id"] for hit in hits],
        "prompt_version": "rag-v1",
        "prompt_sha256": hashlib.sha256(system.encode()).hexdigest(),
        "generation_request": request,
        "raw_response": generated.text,
        "model": generated.model,
        "usage": generated.usage,
        "generation_seconds": round(time.perf_counter() - started, 3),
    }
    try:
        answer = RagAnswer.model_validate_json(generated.text)
        validate_citations(answer, sources)
    except ValidationError:
        raise RagResponseError(
            artifact, "Generated answer failed structured response validation"
        ) from None
    except ValueError:
        raise RagResponseError(
            artifact, "Answer cited a source absent from the generation context"
        ) from None
    return {
        **artifact,
        "answer": answer.model_dump(mode="json"),
        "rendered_answer": render_answer(answer, sources),
    }


def ask_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Grounded PeopleFlow answers using local Ollama.")
    parser.add_argument("question")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument(
        "--mode", choices=["vector", "hybrid", "hybrid-rerank"], default="hybrid-rerank"
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--context-token-budget", type=int, default=3200)
    parser.add_argument("--model", help="Overrides OLLAMA_MODEL (default qwen3:8b).")
    parser.add_argument("--ollama-url", help="Overrides OLLAMA_BASE_URL for local generation.")
    parser.add_argument("--embedding-url", default="http://localhost:11434")
    parser.add_argument("--reranker-model", default=DEFAULT_RERANKER)
    parser.add_argument("--reranker-batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--reranker-device", default="cpu")
    parser.add_argument("--access-group", action="append", choices=sorted(ACCESS_GROUPS))
    parser.add_argument("--hr-access", action="store_true", help="Local HR smoke test only.")
    parser.add_argument(
        "--output", type=Path, help="Save validated answer and sources to a new JSON."
    )
    args = parser.parse_args(argv)
    try:
        if not args.question.strip() or args.top_k < 1 or args.context_token_budget < 2:
            raise ValueError("Provide a question, positive top-k and budget of at least 2")
        if args.output and (args.output.suffix.lower() != ".json" or args.output.exists()):
            raise ValueError("Output must be a new .json file")
        settings = Settings.ollama_from_env()
        settings = replace(
            settings,
            model=args.model if args.model is not None else settings.model,
            base_url=args.ollama_url or settings.base_url,
        )
        provider = RagOllamaProvider(settings)
        groups = list(
            dict.fromkeys(
                [
                    "all_employees",
                    *(args.access_group or []),
                    *(["hr_confidential"] if args.hr_access else []),
                ]
            )
        )
        hits = search(
            args.question,
            args.index,
            top_k=args.top_k,
            access_groups=groups,
            embedder=OllamaEmbedder(args.embedding_url),
            mode=args.mode,
            reranker=CrossEncoderReranker(
                args.reranker_model,
                batch_size=args.reranker_batch_size,
                device=args.reranker_device,
            )
            if args.mode == "hybrid-rerank"
            else None,
        )
        result = generate_answer(
            args.question,
            hits,
            provider,
            access_groups=groups,
            token_budget=args.context_token_budget,
        )
        result["retrieval"] = {
            "mode": args.mode,
            "top_k": args.top_k,
            "index": str(args.index),
            "access_groups": groups,
            "reranker_model": args.reranker_model if args.mode == "hybrid-rerank" else None,
        }
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    except (ValueError, OSError, RuntimeError, ProviderError):
        parser.exit(
            1,
            "Ask failed: check local models, settings, index, output path and response "
            "schema/citations. No answer displayed.\n",
        )
    print(result["rendered_answer"])
    if args.output:
        print(f"Saved answer and source mapping to {args.output}")
    return 0
