"""Offline replay of saved generator outputs with current deterministic scorers."""

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ai_project.ingestion import process_corpus
from ai_project.rag import PROMPT_PATH
from ai_project.rag_evaluation import RagCases, score_answer, summary, validate_labels
from ai_project.retrieval import load_chunks


def replay(baseline_path: Path, cases_path: Path) -> dict[str, Any]:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    raw_cases = cases_path.read_bytes()
    suite = RagCases.model_validate_json(raw_cases)
    if baseline.get("cases_sha256") != hashlib.sha256(raw_cases).hexdigest():
        raise ValueError("Stale test-set hash: regenerate and review baseline for current labels.")
    if baseline.get("completed") is not True or len(suite.cases) != 20:
        raise ValueError("A completed baseline and the current 20-case suite are required.")
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    digest = hashlib.sha256(prompt.encode()).hexdigest()
    settings = baseline["settings"]
    if settings["prompt_sha256"] != digest or settings["system_prompt"] != prompt:
        raise ValueError("Stale rag-v1 prompt: regenerate and review the baseline.")
    # Rebuild from tracked raw sources, without embeddings, Qdrant or model downloads.
    with TemporaryDirectory() as directory:
        output = Path(directory) / "corpus"
        report = process_corpus(Path.cwd(), Path("data/manifest.json"), output)
        if report["errors"] or report["withheld_documents"]:
            raise ValueError("Corpus ingestion failed: inspect ingest-corpus report.json.")
        chunks, corpus_hash = load_chunks(output / "chunks.jsonl")
    if not (corpus_hash == suite.source_sha256 == settings["index_metadata"]["source_sha256"]):
        raise ValueError("Stale corpus hash: rebuild index, review labels and regenerate baseline.")
    corpus = {chunk.chunk_id: chunk for chunk in chunks}
    validate_labels(suite, corpus)
    saved = baseline["cases"]
    ids = [row["id"] for row in saved]
    if len(ids) != len(set(ids)) or set(ids) != {case.id for case in suite.cases}:
        raise ValueError("Baseline must contain each test-set case exactly once.")
    by_id = {row["id"]: row for row in saved}
    rows = []
    for case in suite.cases:
        row = by_id[case.id]
        generation = row.get("generation", {})
        sources = generation.get("sources", [])
        request = json.loads(generation.get("generation_request", "{}"))
        if (
            row["question"] != case.question
            or row["allowed_access_groups"] != case.allowed_access_groups
            or generation.get("question") != case.question
            or request.get("question") != case.question
            or request.get("excerpts") != sources
            or row.get("sources") != sources
            or generation.get("prompt_sha256") != digest
        ):
            raise ValueError(f"{case.id}: missing or inconsistent exact generation context/prompt.")
        if len({s["source_id"] for s in sources}) != len(sources):
            raise ValueError(f"{case.id}: duplicate context source IDs.")
        for source in sources:
            chunk = corpus.get(source["chunk_id"])
            if (
                chunk is None
                or {k: v for k, v in source.items() if k != "source_id"}
                != chunk.model_dump(mode="json")
                or chunk.metadata["access_group"] not in case.allowed_access_groups
            ):
                raise ValueError(f"{case.id}: saved source differs from authorized corpus.")
        if "raw_response" not in generation:
            raise ValueError(f"{case.id}: missing raw response; regenerate baseline.")
        try:
            answer = json.loads(generation["raw_response"])
        except (ValueError, TypeError):
            answer = None
        # Ignore saved scores/outcomes; parse raw output, including invalid responses.
        scores = score_answer(case, answer, sources)
        if "answer" in generation and generation["answer"] != answer:
            raise ValueError(f"{case.id}: saved parsed answer differs from raw response.")
        rows.append(
            {
                "id": case.id,
                "scores": scores,
                "outcome": "valid_answer" if scores["schema_valid"] else "invalid_response",
            }
        )
    counts = summary(rows)
    failures = {
        "schema": [r["id"] for r in rows if not r["scores"]["schema_valid"]],
        "status": [r["id"] for r in rows if r["scores"].get("status_match") is not True],
        "citation_membership": [
            r["id"]
            for r in rows
            if r["scores"]["schema_valid"] and r["scores"]["citation_membership"] != "pass"
        ],
    }
    passed = (
        counts["valid_structured_responses"] >= 19
        and counts["status"]["matched"] >= 16
        and not failures["citation_membership"]
    )
    return {
        "passed": passed,
        "thresholds": {
            "schema_min": 19,
            "status_min": 16,
            "total_cases": 20,
            "citation_membership": "every schema-valid response",
        },
        "status_denominator": 20,
        "summary": counts,
        "failing_cases": failures,
        "cases": rows,
    }


def ci_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=Path("results/rag_baseline.json"))
    parser.add_argument("--cases", type=Path, default=Path("evals/rag_cases.json"))
    args = parser.parse_args(argv)
    try:
        report = replay(args.baseline, args.cases)
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        # Avoid echoing validation payloads or document content.
        message = str(exc) if type(exc) is ValueError else "Required artifact missing or malformed."
        print(f"RAG CI setup failed: {message} Check tracked corpus, cases, prompt and baseline.")
        return 1
    print(
        json.dumps({k: v for k, v in report.items() if k != "cases"}, ensure_ascii=False, indent=2)
    )
    return 0 if report["passed"] else 1
