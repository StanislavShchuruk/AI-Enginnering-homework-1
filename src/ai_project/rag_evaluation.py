"""Provisional RAG baseline: structural and lexical checks, with explicit human review."""

import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Literal

from pydantic import Field, ValidationError, model_validator

from ai_project.config import Settings
from ai_project.providers import AIProvider, ProviderError
from ai_project.rag import (
    PROMPT_PATH,
    RagAnswer,
    RagOllamaProvider,
    RagResponseError,
    StrictModel,
    assemble_context,
    generate_answer,
)
from ai_project.reranking import CrossEncoderReranker, Reranker
from ai_project.retrieval import DEFAULT_INDEX, IndexChunk, OllamaEmbedder, search
from ai_project.retrieval_evaluation import Evidence, QueryCase, Text, index_context

DEFAULT_CASES = Path("evals/rag_cases.json")
DEFAULT_OUTPUT = Path("results/rag_baseline.json")


class RequiredFact(StrictModel):
    id: Text
    required_fact: Text
    qualifications: list[Text]
    acceptable_sources: list[Evidence] = Field(min_length=1)
    check_mode: Literal["regex", "semantic"]
    patterns: list[Text]

    @model_validator(mode="after")
    def check_patterns(self) -> "RequiredFact":
        if bool(self.patterns) != (self.check_mode == "regex"):
            raise ValueError("Only regex facts require nonempty patterns")
        for pattern in self.patterns:
            try:
                re.compile(pattern)
            except re.error:
                raise ValueError("Invalid fact pattern") from None
        ids = [e.chunk_id for e in self.acceptable_sources]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate acceptable sources")
        return self


class AnswerCase(QueryCase):
    expected_status: Literal["answered", "partial", "unavailable"]
    required_facts: list[RequiredFact]
    unsupported_parts: list[Text]
    label_note: Text

    @model_validator(mode="after")
    def check_expectations(self) -> "AnswerCase":
        if (self.expected_status == "unavailable") != (not self.required_facts):
            raise ValueError("Unavailable cases have no required positive facts")
        if bool(self.unsupported_parts) != (self.expected_status != "answered"):
            raise ValueError("Partial/unavailable cases require unsupported parts")
        ids = [f.id for f in self.required_facts]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate fact IDs")
        return self


class RagCases(StrictModel):
    schema_version: Literal["1.0"]
    status: Literal["draft", "reviewed"]
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    labeling_method: Text
    cases: list[AnswerCase] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self) -> "RagCases":
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate case IDs")
        return self


def validate_labels(suite: RagCases, corpus: dict[str, IndexChunk]) -> None:
    """Verify references, access and verbatim evidence before any inference."""
    for case in suite.cases:
        for fact in case.required_facts:
            for evidence in fact.acceptable_sources:
                chunk = corpus.get(evidence.chunk_id)
                if (
                    chunk is None
                    or chunk.metadata["access_group"] not in case.allowed_access_groups
                ):
                    raise ValueError(f"{case.id}/{fact.id}: missing or inaccessible evidence")
                if (
                    evidence.document_title != chunk.document_title
                    or evidence.section_path != chunk.section_path
                    or evidence.version != chunk.version
                    or evidence.excerpt not in chunk.text
                ):
                    raise ValueError(f"{case.id}/{fact.id}: evidence differs from canonical corpus")


def score_answer(
    case: AnswerCase,
    answer: dict[str, Any],
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    """Lexical signals are not semantic truth, entailment or qualification checks."""
    try:
        parsed = RagAnswer.model_validate(answer)
    except ValidationError:
        return {
            "schema_valid": False,
            "status_match": None,
            "citation_membership": "not_scored",
            "facts": [],
            "observed_failures": ["response_schema_invalid"],
            "semantic_review": ["Review invalid raw response; no valid answer was scored."],
        }
    mapping = {s["source_id"]: s["chunk_id"] for s in sources}
    unknown = sorted(
        {sid for claim in parsed.claims for sid in claim.source_ids if sid not in mapping}
    )
    failures = []
    if parsed.status != case.expected_status:
        failures.append("status_mismatch")
    if unknown:
        failures.append("citation_id_absent_from_context")
    facts = []
    for fact in case.required_facts:
        expected = {e.chunk_id for e in fact.acceptable_sources}
        # Match only claim text, never the question, missing_information or source text.
        matched = [
            i
            for i, c in enumerate(parsed.claims)
            if fact.check_mode == "regex"
            and all(re.search(p, c.text, flags=re.IGNORECASE) for p in fact.patterns)
        ]
        candidates = [
            i
            for i, c in enumerate(parsed.claims)
            if any(mapping.get(sid) in expected for sid in c.source_ids)
        ]
        linked = [i for i in matched if i in candidates]
        lexical = (
            "not_scored"
            if fact.check_mode == "semantic"
            else ("matched" if matched else "missing_or_paraphrased")
        )
        source_result = (
            "requires_semantic_alignment"
            if fact.check_mode == "semantic"
            else ("matched" if linked else "wrong_sources" if matched else "not_scored")
        )
        if lexical == "missing_or_paraphrased":
            failures.append(f"{fact.id}:key_fact_not_matched")
        if source_result == "wrong_sources":
            failures.append(f"{fact.id}:expected_source_not_cited_for_matched_fact")
        extra_sources = sorted(
            {
                mapping[sid]
                for i in matched
                for sid in parsed.claims[i].source_ids
                if sid in mapping and mapping[sid] not in expected
            }
        )
        facts.append(
            {
                "fact_id": fact.id,
                "required_fact": fact.required_fact,
                "qualifications": fact.qualifications,
                "check_mode": fact.check_mode,
                "key_fact": lexical,
                "expected_sources": source_result,
                "matching_claim_indices": matched,
                "acceptable_source_claim_indices": candidates,
                "matching_claims_with_acceptable_source": linked,
                "extra_cited_chunk_ids_for_matched_claims": extra_sources,
                "acceptable_chunk_ids": sorted(expected),
                "context_has_acceptable_source": any(s["chunk_id"] in expected for s in sources),
                "semantic_review_required": True,
            }
        )
    return {
        "schema_valid": True,
        "expected_status": case.expected_status,
        "actual_status": parsed.status,
        "status_match": parsed.status == case.expected_status,
        "citation_membership": "fail" if unknown else "pass",
        "unknown_source_ids": unknown,
        "cited_claim_count": len(parsed.claims),
        "facts": facts,
        "observed_failures": failures,
        "semantic_review": [
            "Check entailment, negation, contradictions and omitted qualifications "
            "even for lexical matches.",
            "Align semantic-only facts to cited claims; "
            "citation proximity alone is not fact coverage.",
            "Check language, named version, additional claims "
            "and completeness of the requested answer.",
            *(
                [
                    "Check that missing_information identifies the labeled unsupported parts "
                    "without inventing facts."
                ]
                if case.unsupported_parts
                else []
            ),
            *(
                ["Confirm corpus-wide absence; unavailable is not proved by top-five retrieval."]
                if case.expected_status == "unavailable"
                else []
            ),
        ],
    }


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [r for r in rows if r.get("scores", {}).get("schema_valid")]
    facts = [f for r in valid for f in r["scores"]["facts"]]
    regex = [f for f in facts if f["check_mode"] == "regex"]
    source_scored = [f for f in regex if f["key_fact"] == "matched"]
    return {
        "attempted_cases": len(rows),
        "valid_structured_responses": len(valid),
        "outcomes": dict(Counter(r["outcome"] for r in rows)),
        "status": {
            "matched": sum(r["scores"]["status_match"] for r in valid),
            "scored": len(valid),
        },
        "citation_membership": {
            "passed": sum(r["scores"]["citation_membership"] == "pass" for r in valid),
            "scored": len(valid),
            "note": "No claims means zero citation obligations; membership does not prove support.",
        },
        "key_facts": {
            "lexically_matched": sum(f["key_fact"] == "matched" for f in regex),
            "scored": len(regex),
            "semantic_only_not_scored": len(facts) - len(regex),
        },
        "expected_sources_for_lexical_facts": {
            "matched": sum(f["expected_sources"] == "matched" for f in source_scored),
            "scored": len(source_scored),
        },
        "semantic_review_required_cases": len(valid),
        "warning": "Separate provisional signals; "
        "no aggregate answer-accuracy or semantic pass score.",
    }


def review_sheet(suite: RagCases) -> str:
    lines = [
        "# PeopleFlow RAG case review — draft",
        "",
        "Labels derived before Task 9A generation. "
        "Review facts, qualifications, source alternatives",
        "and negative-case absence before changing suite status to reviewed.",
        "",
        "Regex checks are lexical proxies; "
        "semantic-only facts and every qualification need review.",
        "",
    ]
    for case in suite.cases:
        lines += [
            f"## {case.id} · {case.expected_status}",
            "",
            case.question,
            "",
            f"Access: {', '.join(case.allowed_access_groups)}.",
            "",
        ]
        used = {}
        for fact in case.required_facts:
            labels = []
            for evidence in fact.acceptable_sources:
                if evidence.chunk_id not in used:
                    used[evidence.chunk_id] = (f"E{len(used) + 1}", evidence)
                labels.append(used[evidence.chunk_id][0])
            qualifiers = (
                " Qualifications: " + "; ".join(fact.qualifications) if fact.qualifications else ""
            )
            lines += [
                f"- **{fact.id}**: {fact.required_fact}{qualifiers} "
                f"Sources: {', '.join(labels)}. Check: {fact.check_mode}."
            ]
        for part in case.unsupported_parts:
            lines += [f"- **Must identify as unavailable:** {part}"]
        lines += ["", f"Label note: {case.label_note}", ""]
        for label, evidence in used.values():
            text = evidence.excerpt.replace("\n", " ")
            lines += [
                f"**{label}: {evidence.document_title} / {' > '.join(evidence.section_path)} "
                f"(v{evidence.version})** · `{evidence.chunk_id}`",
                "",
                f"> {text}",
                "",
            ]
        if not used:
            lines += [
                "No positive evidence is labeled. Confirm absence across the canonical corpus,",
                "not only among retrieved excerpts.",
                "",
            ]
    return "\n".join(lines)


def report_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# PeopleFlow RAG baseline — " + report["status"],
        "",
        f"Label status: {report['labels_status']}. Semantic review is required.",
        "",
        f"Cases attempted: {s['attempted_cases']}; "
        f"valid structures: {s['valid_structured_responses']}; "
        f"outcomes: {s['outcomes']}.",
        "",
        f"Status matches: {s['status']['matched']}/{s['status']['scored']}.",
        "",
        f"Citation membership: {s['citation_membership']['passed']}/"
        f"{s['citation_membership']['scored']}.",
        "",
        f"Lexical key-fact matches: {s['key_facts']['lexically_matched']}/"
        f"{s['key_facts']['scored']}; "
        f"semantic-only facts unscored: {s['key_facts']['semantic_only_not_scored']}.",
        "",
        f"Expected-source matches on lexically matched facts: "
        f"{s['expected_sources_for_lexical_facts']['matched']}/"
        f"{s['expected_sources_for_lexical_facts']['scored']}.",
        "",
        "These are separate signals, not answer accuracy. Lexical misses can be paraphrases;",
        "lexical matches can omit qualifications or express negation. "
        "All cases need semantic review.",
        "",
        "| Case | Outcome | Status match | Citation IDs | "
        "Key facts (lexical) | Observed failures |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["cases"]:
        scores = row.get("scores", {})
        facts = [f for f in scores.get("facts", []) if f["check_mode"] == "regex"]
        failures = row.get("observed_failures", [])
        lines.append(
            f"| {row['id']} | {row['outcome']} | {scores.get('status_match', '—')} | "
            f"{scores.get('citation_membership', 'not scored')} | "
            f"{sum(f['key_fact'] == 'matched' for f in facts)}/{len(facts)} | "
            f"{'; '.join(failures) or 'None detected automatically; review required'} |"
        )
    return "\n".join(lines) + "\n"


def write_report(path: Path, report: dict[str, Any]) -> None:
    """Atomic progress saves protect completed cases if a later request fails."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, suffix=".json.tmp", delete=False
    ) as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        temp = Path(stream.name)
    temp.replace(path)


def evaluate_rag(
    cases_path: Path = DEFAULT_CASES,
    index_path: Path = DEFAULT_INDEX,
    output: Path = DEFAULT_OUTPUT,
    *,
    provider: AIProvider | None = None,
    settings: Settings | None = None,
    reranker: Reranker | None = None,
    token_budget: int = 3200,
) -> dict[str, Any]:
    if cases_path.suffix.lower() != ".json" or cases_path.name.startswith(".env"):
        raise ValueError("Cases must be a JSON file")
    if output.suffix.lower() != ".json" or output.exists() or output.with_suffix(".md").exists():
        raise ValueError("Report JSON and Markdown outputs must be new files")
    if token_budget < 2:
        raise ValueError("Context budget must be at least two")
    raw_cases = cases_path.read_bytes()
    suite = RagCases.model_validate_json(raw_cases)
    collection, metadata, corpus = index_context(index_path)
    if suite.source_sha256 != metadata.source_sha256:
        raise ValueError("Labels and active index use different canonical corpora")
    validate_labels(suite, corpus)
    settings = settings or replace(Settings.ollama_from_env(), model="qwen3:8b")
    if settings.provider != "ollama" or settings.model != "qwen3:8b":
        raise ValueError("Task 9A baseline requires local Ollama qwen3:8b")
    provider = provider or RagOllamaProvider(settings)
    reranker = reranker or CrossEncoderReranker()
    system = PROMPT_PATH.read_text(encoding="utf-8")
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "status": "provisional" if suite.status == "draft" else "evaluated",
        "labels_status": suite.status,
        "review_required": True,
        "started_at": datetime.now(UTC).isoformat(),
        "completed": False,
        "cases_file": str(cases_path),
        "cases_sha256": hashlib.sha256(raw_cases).hexdigest(),
        "settings": {
            "model": settings.model,
            "provider": settings.provider,
            "base_url": settings.base_url,
            "temperature": settings.temperature,
            "top_p": settings.top_p,
            "timeout_seconds": settings.timeout,
            "prompt_version": "rag-v1",
            "system_prompt": system,
            "prompt_sha256": hashlib.sha256(system.encode()).hexdigest(),
            "mode": "hybrid-rerank",
            "top_k": 5,
            "context_token_budget": token_budget,
            "reranker_model": reranker.model_name,
            "index": str(index_path),
            "collection": collection,
            "index_metadata": metadata.model_dump(mode="json"),
        },
        "cases": [],
        "summary": {},
    }
    for case in suite.cases:
        row: dict[str, Any] = {
            "id": case.id,
            "question": case.question,
            "allowed_access_groups": case.allowed_access_groups,
            "expected_status": case.expected_status,
        }
        try:
            hits = search(
                case.question,
                index_path,
                top_k=5,
                access_groups=case.allowed_access_groups,
                mode="hybrid-rerank",
                reranker=reranker,
                embedder=OllamaEmbedder(),
            )
            sources, tokens = assemble_context(hits, case.allowed_access_groups, token_budget)
            row.update(
                sources=sources,
                context_tokens=tokens,
                retrieved_chunk_ids=[h["chunk_id"] for h in hits],
            )
        except (ValueError, OSError, RuntimeError):
            row.update(outcome="retrieval_error", observed_failures=["retrieval_or_context_failed"])
        else:
            try:
                row["generation"] = generate_answer(
                    case.question,
                    hits,
                    provider,
                    access_groups=case.allowed_access_groups,
                    token_budget=token_budget,
                )
            except RagResponseError as exc:
                row["generation"] = exc.artifact
                row.update(
                    outcome="response_validation_error",
                    observed_failures=["response_schema_or_citation_validation_failed"],
                )
                try:
                    invalid = json.loads(exc.artifact["raw_response"])
                    row["scores"] = score_answer(case, invalid, sources)
                    row["observed_failures"] += row["scores"]["observed_failures"]
                except (ValueError, TypeError):
                    pass
            except (ProviderError, ValueError, OSError, RuntimeError):
                row.update(
                    outcome="provider_error", observed_failures=["generation_request_failed"]
                )
            else:
                row["scores"] = score_answer(case, row["generation"]["answer"], sources)
                row.update(
                    outcome="valid_answer", observed_failures=row["scores"]["observed_failures"]
                )
        report["cases"].append(row)
        report["summary"] = summary(report["cases"])
        write_report(output, report)
        print(f"{case.id}: {row['outcome']}", flush=True)
    report["completed"] = True
    report["finished_at"] = datetime.now(UTC).isoformat()
    write_report(output, report)
    output.with_suffix(".md").write_text(report_markdown(report), encoding="utf-8")
    return report


def evaluation_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Provisional local PeopleFlow RAG answer baseline."
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--context-token-budget", type=int, default=3200)
    parser.add_argument(
        "--review-sheet", type=Path, help="Write a label-only Markdown sheet without inference."
    )
    args = parser.parse_args(argv)
    try:
        if args.cases.suffix.lower() != ".json" or args.cases.name.startswith(".env"):
            raise ValueError("Cases must be a JSON file")
        if args.review_sheet:
            if args.review_sheet.suffix.lower() != ".md" or args.review_sheet.exists():
                raise ValueError("Review sheet must be a new Markdown file")
            suite = RagCases.model_validate_json(args.cases.read_bytes())
            _, metadata, corpus = index_context(args.index)
            if suite.source_sha256 != metadata.source_sha256:
                raise ValueError("Labels and index corpus differ")
            validate_labels(suite, corpus)
            args.review_sheet.parent.mkdir(parents=True, exist_ok=True)
            args.review_sheet.write_text(review_sheet(suite), encoding="utf-8")
            print(f"Saved label review sheet to {args.review_sheet}; no inference performed.")
            return 0
        report = evaluate_rag(
            args.cases, args.index, args.output, token_budget=args.context_token_budget
        )
    except (ValueError, OSError, RuntimeError):
        parser.exit(
            1,
            "RAG evaluation setup/persistence failed; check cases, index, local models "
            "and new output paths.\n",
        )
    print(json.dumps(report["summary"], indent=2))
    return 1 if any(r["outcome"] != "valid_answer" for r in report["cases"]) else 0
