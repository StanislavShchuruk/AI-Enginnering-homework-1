"""Focused offline scoring and error-isolation tests; all generation is mocked."""

import hashlib
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError
from test_retrieval import record

from ai_project.cli import main
from ai_project.config import Settings
from ai_project.providers import GenerationResult, ProviderError
from ai_project.rag_evaluation import (
    AnswerCase,
    RagCases,
    evaluate_rag,
    review_sheet,
    score_answer,
    summary,
    validate_labels,
)
from ai_project.retrieval import IndexChunk, IndexMetadata


def labeled_case(status="answered", mode="regex") -> AnswerCase:
    chunk = record(1)
    return AnswerCase.model_validate(
        {
            "id": "X1",
            "question": "What is the correction window?",
            "allowed_access_groups": ["all_employees"],
            "expected_status": status,
            "required_facts": []
            if status == "unavailable"
            else [
                {
                    "id": "window",
                    "required_fact": "14 calendar days from the affected workday.",
                    "qualifications": ["Payroll must be unlocked."],
                    "acceptable_sources": [
                        {
                            k: chunk[k]
                            for k in [
                                "chunk_id",
                                "document_title",
                                "section_path",
                                "version",
                            ]
                        }
                        | {"excerpt": chunk["text"]}
                    ],
                    "check_mode": mode,
                    "patterns": [r"\b14 calendar days\b"] if mode == "regex" else [],
                }
            ],
            "unsupported_parts": ["Unspecified benefit amount."] if status != "answered" else [],
            "label_note": "Synthetic scoring fixture.",
        }
    )


def answer(text="14 calendar days", ids=None, status="answered", missing=None) -> dict:
    return {
        "status": status,
        "claims": []
        if status == "unavailable"
        else [
            {"text": text, "source_ids": ids if ids is not None else ["S1"]},
        ],
        "missing_information": missing,
    }


def context() -> list[dict]:
    return [{"source_id": "S1", **record(1)}, {"source_id": "S2", **record(2)}]


def test_status_membership_key_fact_and_expected_source_are_independent():
    scored = score_answer(labeled_case("partial"), answer(), context())
    assert scored["schema_valid"] and not scored["status_match"]
    assert scored["citation_membership"] == "pass"
    assert scored["facts"][0]["key_fact"] == "matched"
    assert scored["facts"][0]["expected_sources"] == "matched"
    assert scored["facts"][0]["semantic_review_required"]


def test_known_but_wrong_source_does_not_support_matched_fact():
    scored = score_answer(labeled_case(), answer(ids=["S2"]), context())
    assert scored["citation_membership"] == "pass"
    assert scored["facts"][0]["expected_sources"] == "wrong_sources"
    assert "window:expected_source_not_cited_for_matched_fact" in scored["observed_failures"]


def test_unknown_id_rejected_against_context_not_corpus():
    scored = score_answer(labeled_case(), answer(ids=["S99"]), context())
    assert scored["citation_membership"] == "fail"
    assert scored["unknown_source_ids"] == ["S99"]


def test_equivalent_acceptable_source_is_allowed():
    case = labeled_case()
    extra = (
        case.required_facts[0]
        .acceptable_sources[0]
        .model_copy(
            update={"chunk_id": record(2)["chunk_id"]},
        )
    )
    case.required_facts[0].acceptable_sources.append(extra)
    assert (
        score_answer(case, answer(ids=["S2"]), context())["facts"][0]["expected_sources"]
        == "matched"
    )


def test_citing_right_source_elsewhere_does_not_repair_wrong_fact_citation():
    response = answer(ids=["S2"])
    response["claims"].append({"text": "Unrelated claim", "source_ids": ["S1"]})
    fact = score_answer(labeled_case(), response, context())["facts"][0]
    assert fact["matching_claim_indices"] == [0]
    assert fact["acceptable_source_claim_indices"] == [1]
    assert fact["expected_sources"] == "wrong_sources"


def test_keywords_in_question_sources_or_missing_information_do_not_count():
    case = labeled_case("partial")
    case.question = "Is it 14 calendar days?"
    sources = context()
    sources[0]["text"] = "14 calendar days"
    scored = score_answer(
        case,
        answer("No numeric fact", status="partial", missing="14 calendar days is missing."),
        sources,
    )
    assert scored["facts"][0]["key_fact"] == "missing_or_paraphrased"


def test_semantic_only_fact_never_gets_an_automatic_content_pass():
    fact = score_answer(labeled_case(mode="semantic"), answer(), context())["facts"][0]
    assert fact["key_fact"] == "not_scored"
    assert fact["expected_sources"] == "requires_semantic_alignment"
    assert fact["acceptable_source_claim_indices"] == [0]


def test_negation_and_qualifications_are_explicitly_left_for_review():
    scored = score_answer(labeled_case(), answer("It is NOT 14 calendar days."), context())
    assert scored["facts"][0]["key_fact"] == "matched"
    assert scored["facts"][0]["qualifications"] == ["Payroll must be unlocked."]
    assert any("negation" in note for note in scored["semantic_review"])


def test_valid_unavailable_has_no_citation_obligations_and_is_not_error():
    scored = score_answer(
        labeled_case("unavailable"),
        answer(
            status="unavailable",
            missing="Information unavailable in accessible documents.",
        ),
        [],
    )
    assert scored["status_match"] and scored["citation_membership"] == "pass"
    assert scored["cited_claim_count"] == 0 and not scored["facts"]
    assert any("corpus-wide absence" in note for note in scored["semantic_review"])


@pytest.mark.parametrize(
    "value",
    [
        {"status": "answered"},
        answer(ids=[]),
        answer(status="partial"),
        {**answer(), "extra": "uncited"},
    ],
)
def test_schema_errors_are_not_valid_unavailable(value):
    scored = score_answer(labeled_case(), value, context())
    assert not scored["schema_valid"] and scored["status_match"] is None
    assert scored["citation_membership"] == "not_scored"


def test_summary_denominators_keep_errors_separate():
    valid = score_answer(
        labeled_case("unavailable"),
        answer(
            status="unavailable",
            missing="Unavailable.",
        ),
        [],
    )
    result = summary(
        [
            {"outcome": "valid_answer", "scores": valid},
            {"outcome": "provider_error"},
            {"outcome": "retrieval_error"},
        ]
    )
    assert result["attempted_cases"] == 3
    assert result["valid_structured_responses"] == 1
    assert result["status"] == {"matched": 1, "scored": 1}
    assert result["key_facts"]["scored"] == 0
    assert result["outcomes"]["provider_error"] == 1


@pytest.fixture
def run_setup(tmp_path):
    cases = [labeled_case(), labeled_case("unavailable"), labeled_case("unavailable")]
    cases[1].id, cases[2].id = "X2", "X3"
    suite = RagCases(
        schema_version="1.0",
        status="draft",
        source_sha256="a" * 64,
        labeling_method="Before generation.",
        cases=cases,
    )
    path = tmp_path / "cases.json"
    path.write_text(suite.model_dump_json(), encoding="utf-8")
    metadata = IndexMetadata(
        embedding_model="bge-m3",
        vector_dimension=2,
        source_file="synthetic.jsonl",
        source_sha256="a" * 64,
        chunk_count=1,
    )
    corpus = {record(1)["chunk_id"]: IndexChunk.model_validate(record(1))}
    fake_provider = Mock()
    fake_provider.generate.return_value = GenerationResult(json.dumps(answer()), "qwen3:8b")
    fake_reranker = Mock(model_name="fake-reranker")
    return path, suite, metadata, corpus, fake_provider, fake_reranker


def test_runner_reuses_generation_preserves_errors_and_saves_exact_context(run_setup, tmp_path):
    path, suite, metadata, corpus, provider, reranker = run_setup
    provider.generate.side_effect = [
        GenerationResult(json.dumps(answer()), "qwen3:8b"),
        ProviderError("private provider body"),
    ]
    output = tmp_path / "run.json"
    with (
        patch("ai_project.rag_evaluation.index_context", return_value=("col", metadata, corpus)),
        patch("ai_project.rag_evaluation.search", side_effect=[[record(1)], [], ValueError("bad")]),
    ):
        result = evaluate_rag(
            path,
            tmp_path,
            output,
            provider=provider,
            settings=Settings(provider="ollama", model="qwen3:8b"),
            reranker=reranker,
        )
    assert result["status"] == "provisional" and result["completed"]
    assert [r["outcome"] for r in result["cases"]] == [
        "valid_answer",
        "provider_error",
        "retrieval_error",
    ]
    generated = result["cases"][0]["generation"]
    assert json.loads(generated["generation_request"])["excerpts"] == generated["sources"]
    assert generated["sources"][0]["chunk_id"] == record(1)["chunk_id"]
    assert generated["answer"] == answer()
    assert result["cases"][1]["sources"] == []
    assert "private provider body" not in output.read_text(encoding="utf-8")
    assert output.with_suffix(".md").exists()
    assert result["cases_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_runner_saves_invalid_citation_response_without_accepting_it(run_setup, tmp_path):
    path, _, metadata, corpus, provider, reranker = run_setup
    provider.generate.return_value = GenerationResult(json.dumps(answer(ids=["S99"])), "qwen3:8b")
    with (
        patch("ai_project.rag_evaluation.index_context", return_value=("col", metadata, corpus)),
        patch("ai_project.rag_evaluation.search", return_value=[record(1)]),
    ):
        result = evaluate_rag(
            path,
            tmp_path,
            tmp_path / "run.json",
            provider=provider,
            settings=Settings(provider="ollama", model="qwen3:8b"),
            reranker=reranker,
        )
    row = result["cases"][0]
    assert row["outcome"] == "response_validation_error"
    assert row["generation"]["raw_response"] == json.dumps(answer(ids=["S99"]))
    assert row["scores"]["citation_membership"] == "fail"
    assert "answer" not in row["generation"]


def test_labels_checked_before_provider_or_retrieval(run_setup, tmp_path):
    path, suite, metadata, corpus, provider, reranker = run_setup
    suite.cases[0].required_facts[0].acceptable_sources[0].excerpt = "not in corpus"
    path.write_text(suite.model_dump_json(), encoding="utf-8")
    with (
        patch("ai_project.rag_evaluation.index_context", return_value=("col", metadata, corpus)),
        patch("ai_project.rag_evaluation.search") as search,
        pytest.raises(ValueError, match="evidence"),
    ):
        evaluate_rag(path, tmp_path, tmp_path / "run.json", provider=provider, reranker=reranker)
    search.assert_not_called()
    provider.generate.assert_not_called()


def test_review_sheet_is_offline_and_contains_all_evidence(run_setup, tmp_path):
    path, suite, metadata, corpus, provider, _ = run_setup
    sheet = tmp_path / "review.md"
    with patch("ai_project.rag_evaluation.index_context", return_value=("col", metadata, corpus)):
        assert main(["eval-rag", "--cases", str(path), "--review-sheet", str(sheet)]) == 0
    content = sheet.read_text(encoding="utf-8")
    assert all(c.question in content for c in suite.cases)
    assert "Payroll must be unlocked" in content and "body 1" in content
    assert "Confirm absence" in content
    provider.generate.assert_not_called()


def test_real_draft_has_twenty_cases_and_three_distinct_r05_facts():
    suite = RagCases.model_validate_json(Path("evals/rag_cases.json").read_bytes())
    assert suite.status == "draft" and len(suite.cases) == 20
    r05 = next(c for c in suite.cases if c.id == "R05")
    assert [f.id for f in r05.required_facts] == ["window", "unlocked", "locked_route"]
    assert "14" not in r05.question
    assert {c.expected_status for c in suite.cases} == {"answered", "partial", "unavailable"}
    assert "draft" in review_sheet(suite)


def test_label_access_and_status_consistency(run_setup):
    _, suite, _, corpus, _, _ = run_setup
    corpus[record(1)["chunk_id"]].metadata["access_group"] = "hr_confidential"
    with pytest.raises(ValueError, match="inaccessible"):
        validate_labels(suite, corpus)
    with pytest.raises(ValidationError):
        AnswerCase.model_validate({**labeled_case().model_dump(), "expected_status": "unavailable"})
