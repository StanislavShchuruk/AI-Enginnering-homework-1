"""Draft corpus-grounded evaluation of existing vector search, always at k=5."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from qdrant_client import QdrantClient

from ai_project.retrieval import (
    ACCESS_GROUPS,
    DEFAULT_INDEX,
    DEFAULT_URL,
    IndexChunk,
    IndexMetadata,
    OllamaEmbedder,
    active_collection,
    load_chunks,
    search,
)

DEFAULT_CASES = Path("evals/retrieval_cases.json")
DEFAULT_OUTPUT = Path("results/retrieval_vector_baseline.json")
K = 5
Text = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]
ChunkID = Annotated[str, StringConstraints(pattern=r"^.+-[0-9a-f]{64}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Evidence(StrictModel):
    chunk_id: ChunkID
    document_title: Text
    section_path: list[Text]
    version: str | None
    excerpt: Text


class QueryCase(StrictModel):
    id: Text
    question: Text
    allowed_access_groups: list[Text] = Field(min_length=1)

    @field_validator("allowed_access_groups", check_fields=False)
    @classmethod
    def known_groups(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)) or set(value) - ACCESS_GROUPS:
            raise ValueError("Access groups must be unique known corpus groups")
        return value


class RelevanceCase(QueryCase):
    topic: Literal["leave", "payroll", "attendance", "shifts", "support"]
    label_note: Text
    expected_chunk_ids: list[ChunkID] = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_labels(self) -> "RelevanceCase":
        expected = set(self.expected_chunk_ids)
        evidence_ids = [item.chunk_id for item in self.evidence]
        if len(expected) != len(self.expected_chunk_ids):
            raise ValueError("Expected chunk IDs must be unique")
        if len(evidence_ids) != len(set(evidence_ids)) or set(evidence_ids) != expected:
            raise ValueError("Exactly one evidence entry is required per expected chunk")
        return self


class AccessCase(QueryCase):
    forbidden_access_groups: list[Text] = Field(min_length=1)
    note: Text

    @field_validator("forbidden_access_groups")
    @classmethod
    def known_forbidden_groups(cls, value: list[str]) -> list[str]:
        return cls.known_groups(value)

    @model_validator(mode="after")
    def disjoint_groups(self) -> "AccessCase":
        if set(self.allowed_access_groups) & set(self.forbidden_access_groups):
            raise ValueError("Allowed and forbidden groups must be disjoint")
        return self


class RetrievalCases(StrictModel):
    schema_version: Literal["1.0"]
    status: Literal["draft"]
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    labeling_method: Text
    cases: list[RelevanceCase] = Field(min_length=1)
    access_control_cases: list[AccessCase] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_cases(self) -> "RetrievalCases":
        ids = [case.id for case in [*self.cases, *self.access_control_cases]]
        if len(ids) != len(set(ids)):
            raise ValueError("Case IDs must be unique across both case lists")
        return self


def index_context(index_path: Path) -> tuple[str, IndexMetadata, dict[str, IndexChunk]]:
    """Resolve the active index's canonical input and verify its persisted payloads."""
    if not (index_path / "qdrant").is_dir():
        raise ValueError("No local index; run index-corpus first")
    client = QdrantClient(path=str(index_path / "qdrant"))
    try:
        collection = active_collection(client)
        metadata = IndexMetadata.model_validate_json(
            (index_path / f"{collection}.json").read_text(encoding="utf-8")
        )
        chunks, digest = load_chunks(Path(metadata.source_file))
        if digest != metadata.source_sha256 or len(chunks) != metadata.chunk_count:
            raise ValueError(
                "Canonical chunks differ from the current index metadata; rebuild first"
            )
        corpus = {chunk.chunk_id: chunk for chunk in chunks}
        seen: set[str] = set()
        offset = None
        while True:
            points, offset = client.scroll(
                collection, limit=256, offset=offset, with_payload=True, with_vectors=False
            )
            for point in points:
                payload = point.payload or {}
                chunk_id = payload.get("chunk_id")
                chunk = corpus.get(chunk_id) if isinstance(chunk_id, str) else None
                if (
                    chunk is None
                    or chunk_id in seen
                    or payload
                    != {
                        **chunk.model_dump(mode="json"),
                        "access_group": chunk.metadata["access_group"],
                    }
                ):
                    raise ValueError("Persisted index payloads differ from canonical chunks")
                seen.add(chunk_id)
            if offset is None:
                break
        if seen != set(corpus):
            raise ValueError("Indexed chunk IDs differ from canonical chunks")
        return collection, metadata, corpus
    finally:
        client.close()


def validate_labels(suite: RetrievalCases, corpus: dict[str, IndexChunk]) -> None:
    """Check every label and its evidence before making any embedding requests."""
    for case in suite.cases:
        for evidence in case.evidence:
            chunk = corpus.get(evidence.chunk_id)
            if chunk is None:
                raise ValueError(f"{case.id}: expected chunk does not exist: {evidence.chunk_id}")
            if chunk.metadata["access_group"] not in case.allowed_access_groups:
                raise ValueError(f"{case.id}: expected chunk is not visible to case access groups")
            if (
                evidence.document_title != chunk.document_title
                or evidence.section_path != chunk.section_path
                or evidence.version != chunk.version
                or evidence.excerpt not in chunk.text
            ):
                raise ValueError(f"{case.id}: evidence does not match the canonical chunk")


def score_case(expected_ids: list[str], ranked_ids: list[str]) -> dict[str, Any]:
    """Recall is over all expected chunks; reciprocal rank uses the first hit only."""
    if not expected_ids or len(expected_ids) != len(set(expected_ids)):
        raise ValueError("Expected IDs must be nonempty and unique")
    top = ranked_ids[:K]
    if len(top) != len(set(top)):
        raise ValueError("Search returned duplicate chunk IDs")
    expected = set(expected_ids)
    first = next((rank for rank, chunk_id in enumerate(top, 1) if chunk_id in expected), None)
    missing = [chunk_id for chunk_id in expected_ids if chunk_id not in top]
    return {
        "ranked_ids": top,
        "first_relevant_rank": first,
        "miss": first is None,
        "missing_expected_chunk_ids": missing,
        "recall_at_5": len(expected.intersection(top)) / len(expected),
        "reciprocal_rank_at_5": 1 / first if first is not None else 0.0,
    }


def evaluate_retrieval(
    cases_path: Path = DEFAULT_CASES,
    index_path: Path = DEFAULT_INDEX,
    *,
    embedder: OllamaEmbedder | None = None,
) -> dict[str, Any]:
    if cases_path.suffix.lower() != ".json" or cases_path.name.startswith(".env"):
        raise ValueError("Cases must be a JSON file")
    cases_bytes = cases_path.read_bytes()
    suite = RetrievalCases.model_validate_json(cases_bytes)
    collection, metadata, corpus = index_context(index_path)
    if suite.source_sha256 != metadata.source_sha256:
        raise ValueError("Cases source hash differs from the indexed corpus; review labels first")
    validate_labels(suite, corpus)
    embedder = embedder or OllamaEmbedder()
    results = []
    for case in suite.cases:
        hits = search(
            case.question,
            index_path,
            top_k=K,
            access_groups=case.allowed_access_groups,
            embedder=embedder,
        )
        results.append(
            {
                "id": case.id,
                "question": case.question,
                "allowed_access_groups": case.allowed_access_groups,
                "expected_chunk_ids": case.expected_chunk_ids,
                **score_case(case.expected_chunk_ids, [hit["chunk_id"] for hit in hits]),
            }
        )
    access_results = []
    for case in suite.access_control_cases:
        hits = search(
            case.question,
            index_path,
            top_k=K,
            access_groups=case.allowed_access_groups,
            embedder=embedder,
        )
        forbidden = [
            hit["chunk_id"]
            for hit in hits
            if hit.get("access_group") in case.forbidden_access_groups
        ]
        # Fail closed on missing/unknown groups too; the HR-specific count stays separate.
        invisible = [
            hit["chunk_id"]
            for hit in hits
            if hit.get("access_group") not in case.allowed_access_groups
        ]
        access_results.append(
            {
                **case.model_dump(),
                "ranked_ids": [hit["chunk_id"] for hit in hits],
                "returned_access_groups": [hit.get("access_group") for hit in hits],
                "returned_count": len(hits),
                "forbidden_chunk_ids": forbidden,
                "forbidden_chunk_count": len(forbidden),
                "invisible_chunk_ids": invisible,
                "passed": not forbidden and not invisible,
            }
        )
    # Search reopens local Qdrant per query; reject a run spanning a concurrent rebuild.
    final_collection, final_metadata, _ = index_context(index_path)
    if final_collection != collection or final_metadata != metadata:
        raise ValueError("Active index changed during evaluation; rerun against a stable index")
    return {
        "status": "provisional",
        "review_required": True,
        "cases_status": suite.status,
        "run_at_utc": datetime.now(UTC).isoformat(),
        "retriever": "vector",
        "k": K,
        "cases_file": cases_path.as_posix(),
        "cases_sha256": hashlib.sha256(cases_bytes).hexdigest(),
        "embedding_model": metadata.embedding_model,
        "vector_dimension": metadata.vector_dimension,
        "source_sha256": metadata.source_sha256,
        "source_file": metadata.source_file,
        "indexed_chunk_count": len(corpus),
        "relevance": {
            "case_count": len(results),
            "mean_recall_at_5": sum(r["recall_at_5"] for r in results) / len(results),
            "mrr_at_5": sum(r["reciprocal_rank_at_5"] for r in results) / len(results),
            "miss_count": sum(r["miss"] for r in results),
            "cases": results,
        },
        "access_control": {
            "case_count": len(access_results),
            "passed": all(r["passed"] for r in access_results),
            "cases": access_results,
        },
    }


def evaluation_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Provisional PeopleFlow vector retrieval eval at k=5."
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ollama-url", default=DEFAULT_URL)
    args = parser.parse_args(argv)
    try:
        if args.output.suffix.lower() != ".json" or args.output.name.startswith(".env"):
            raise ValueError("Output must be a JSON report")
        if args.output.resolve() == args.cases.resolve() or args.output.resolve().is_relative_to(
            args.index.resolve()
        ):
            raise ValueError("Output cannot replace cases or write inside the index")
        report = evaluate_retrieval(
            args.cases, args.index, embedder=OllamaEmbedder(args.ollama_url)
        )
        if args.output.resolve() == Path(report["source_file"]).resolve():
            raise ValueError("Output cannot replace canonical chunks")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=args.output.parent, suffix=".json", delete=False
            ) as stream:
                temporary = Path(stream.name)
                json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
            temporary.replace(args.output)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f"Retrieval evaluation failed: {exc}\n")
    metrics = report["relevance"]
    print(
        f"PROVISIONAL: Recall@5={metrics['mean_recall_at_5']:.4f}; "
        f"MRR@5={metrics['mrr_at_5']:.4f}; misses={metrics['miss_count']}/{metrics['case_count']}"
    )
    print(
        f"Access control: {'PASS' if report['access_control']['passed'] else 'FAIL'}; "
        f"saved {args.output}"
    )
    return 0 if report["access_control"]["passed"] else 1
