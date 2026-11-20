"""Offline metric, label-validation, persistence, and CLI tests."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from ai_project.cli import main
from ai_project.retrieval import build_index
from ai_project.retrieval_evaluation import (
    RetrievalCases,
    evaluate_retrieval,
    index_context,
    score_case,
)


@pytest.mark.parametrize(
    "expected,ranked,recall,rr,first,missing",
    [
        (["a", "b"], ["x", "b", "y", "a"], 1.0, 0.5, 2, []),
        (["a", "b"], ["x", "b"], 0.5, 0.5, 2, ["a"]),
        (["a"], ["x", "y", "z", "w", "v", "a"], 0.0, 0.0, None, ["a"]),
        (["a"], ["v", "w", "x", "y", "a"], 1.0, 0.2, 5, []),
        (["a"], [], 0.0, 0.0, None, ["a"]),
    ],
)
def test_metrics(expected, ranked, recall, rr, first, missing):
    result = score_case(expected, ranked)
    assert result["recall_at_5"] == recall
    assert result["reciprocal_rank_at_5"] == rr
    assert result["first_relevant_rank"] == first
    assert result["missing_expected_chunk_ids"] == missing
    assert result["miss"] == (first is None)


@pytest.mark.parametrize("expected,ranked", [([], []), (["a", "a"], []), (["a"], ["a", "a"])])
def test_metric_input_validation(expected, ranked):
    with pytest.raises(ValueError):
        score_case(expected, ranked)


@pytest.fixture
def evaluation_fixture(tmp_path):
    records = [
        {
            "chunk_id": f"C01-{i:064x}",
            "document_id": "C01",
            "text": f"evidence {i}",
            "token_count": 2,
            "source_reference": "C01.docx",
            "document_title": "Contract A",
            "section_path": [f"Section {i}"],
            "version": "2.0",
            "effective_date": "2026-09-01",
            "source_hash": "a" * 64,
            "content_hash": "b" * 64,
            "metadata": {"access_group": group},
            "block_indices": [],
            "locations": [],
            "pages": [],
        }
        for i, group in enumerate(["all_employees", "hr_confidential", "all_employees"], 1)
    ]
    source = tmp_path / "chunks.jsonl"
    source.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    index = tmp_path / "index"
    embedder = Mock()
    embedder.embed.side_effect = lambda texts, model: [[1.0, 0.0] for _ in texts]
    build_index(source, index, model="test-embedding", embedder=embedder)
    suite = {
        "schema_version": "1.0",
        "status": "draft",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "labeling_method": "Chosen from text before search",
        "cases": [
            {
                "id": "R01",
                "question": "question",
                "topic": "leave",
                "label_note": "draft",
                "allowed_access_groups": ["all_employees", "hr_confidential"],
                "expected_chunk_ids": [r["chunk_id"] for r in records[:2]],
                "evidence": [
                    {
                        "chunk_id": r["chunk_id"],
                        "document_title": r["document_title"],
                        "section_path": r["section_path"],
                        "version": r["version"],
                        "excerpt": r["text"],
                    }
                    for r in records[:2]
                ],
            }
        ],
        "access_control_cases": [
            {
                "id": "ACL01",
                "question": "question",
                "allowed_access_groups": ["all_employees"],
                "forbidden_access_groups": ["hr_confidential"],
                "note": "separate check",
            }
        ],
    }
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps(suite), encoding="utf-8")
    embedder.reset_mock()
    return cases_path, index, source, suite, records, embedder


def test_evaluation_calls_existing_search_at_five_and_separates_access(evaluation_fixture):
    path, index, _, _, records, embedder = evaluation_fixture
    denied = {"chunk_id": records[1]["chunk_id"], "access_group": "hr_confidential"}
    public = {"chunk_id": records[2]["chunk_id"], "access_group": "all_employees"}
    with patch(
        "ai_project.retrieval_evaluation.search",
        side_effect=[
            [public, denied],
            [public],
        ],
    ) as query:
        report = evaluate_retrieval(path, index, embedder=embedder)
    relevance = report["relevance"]
    assert relevance["case_count"] == 1
    assert relevance["mean_recall_at_5"] == 0.5
    assert relevance["mrr_at_5"] == 0.5
    assert report["access_control"]["passed"] is True
    assert report["status"] == "provisional"
    assert report["embedding_model"] == "test-embedding"
    assert all(call.kwargs["top_k"] == 5 for call in query.call_args_list)
    assert query.call_args_list[0].kwargs["access_groups"] == ["all_employees", "hr_confidential"]
    assert query.call_args_list[1].kwargs["access_groups"] == ["all_employees"]


@pytest.mark.parametrize("mode", ["vector", "hybrid", "hybrid-rerank"])
def test_real_local_search_integration(evaluation_fixture, mode):
    path, index, _, _, _, embedder = evaluation_fixture
    scorer = Mock(model_name="fake-reranker")
    scorer.score.side_effect = lambda question, passages: [0.0] * len(passages)
    scorer.batch_size = 8
    scorer.device = "cpu"
    report = evaluate_retrieval(path, index, embedder=embedder, mode=mode, reranker=scorer)
    assert report["relevance"]["mean_recall_at_5"] == 1
    assert report["access_control"]["passed"]
    assert report["retriever"] == mode
    assert embedder.embed.call_count == 2
    assert all(call.args[1] == "test-embedding" for call in embedder.embed.call_args_list)
    assert all(report["relevance"]["cases"][0]["expected_in_candidate_pool"].values())
    assert report["median_query_seconds"] >= 0


def test_reviewed_status_and_labels_are_preserved(evaluation_fixture):
    path, index, _, suite, _, embedder = evaluation_fixture
    suite["status"] = "reviewed"
    path.write_text(json.dumps(suite), encoding="utf-8")
    report = evaluate_retrieval(path, index, embedder=embedder)
    assert report["cases_status"] == "reviewed"
    assert report["status"] == "evaluated"
    assert report["review_required"] is False
    assert (
        report["relevance"]["cases"][0]["expected_chunk_ids"]
        == (suite["cases"][0]["expected_chunk_ids"])
    )


def test_expected_candidate_coverage_is_recorded(evaluation_fixture):
    path, index, _, _, records, embedder = evaluation_fixture
    present, absent = [r["chunk_id"] for r in records[:2]]

    def fake_search(question, index_path, **kwargs):
        kwargs["diagnostics"].update(
            candidate_ids=[present], candidate_access_groups=["all_employees"]
        )
        return [{"chunk_id": present, "access_group": "all_employees"}]

    with patch("ai_project.retrieval_evaluation.search", side_effect=fake_search):
        report = evaluate_retrieval(path, index, embedder=embedder, mode="hybrid")
    case = report["relevance"]["cases"][0]
    assert case["expected_in_candidate_pool"] == {present: True, absent: False}
    assert case["expected_candidate_ranks"] == {present: 1, absent: None}


def test_macro_averages_include_misses_and_exclude_access_case(evaluation_fixture):
    path, index, _, suite, records, embedder = evaluation_fixture
    second = deepcopy(suite["cases"][0])
    second["id"] = "R02"
    second["expected_chunk_ids"] = second["expected_chunk_ids"][:1]
    second["evidence"] = second["evidence"][:1]
    suite["cases"].append(second)
    path.write_text(json.dumps(suite), encoding="utf-8")
    with patch(
        "ai_project.retrieval_evaluation.search",
        side_effect=[
            [{"chunk_id": records[2]["chunk_id"]}, {"chunk_id": records[0]["chunk_id"]}],
            [],
            [],
        ],
    ):
        report = evaluate_retrieval(path, index, embedder=embedder)
    assert report["relevance"]["mean_recall_at_5"] == 0.25
    assert report["relevance"]["mrr_at_5"] == 0.25
    assert report["relevance"]["miss_count"] == 1
    assert report["relevance"]["case_count"] == 2


@pytest.mark.parametrize(
    "problem", ["unknown_id", "invisible", "excerpt", "title", "section", "version", "hash"]
)
def test_invalid_labels_fail_before_search(evaluation_fixture, problem):
    path, index, _, suite, _, embedder = evaluation_fixture
    case = suite["cases"][0]
    if problem == "unknown_id":
        unknown = "C99-" + "a" * 64
        case["expected_chunk_ids"][0] = unknown
        case["evidence"][0]["chunk_id"] = unknown
    elif problem == "invisible":
        case["allowed_access_groups"] = ["all_employees"]
    elif problem == "hash":
        suite["source_sha256"] = "0" * 64
    else:
        field = {
            "excerpt": "excerpt",
            "title": "document_title",
            "section": "section_path",
            "version": "version",
        }[problem]
        case["evidence"][0][field] = ["wrong"] if problem == "section" else "wrong"
    path.write_text(json.dumps(suite))
    with patch("ai_project.retrieval_evaluation.search") as query, pytest.raises(ValueError):
        evaluate_retrieval(path, index, embedder=embedder)
    query.assert_not_called()
    embedder.embed.assert_not_called()


def test_changed_canonical_file_rejected(evaluation_fixture):
    path, index, source, _, _, embedder = evaluation_fixture
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(ValueError):
        evaluate_retrieval(path, index, embedder=embedder)
    embedder.embed.assert_not_called()


def test_missing_indexed_point_rejected(evaluation_fixture):
    _, index, _, _, _, _ = evaluation_fixture
    from qdrant_client import QdrantClient, models

    from ai_project.retrieval import active_collection

    client = QdrantClient(path=str(index / "qdrant"))
    try:
        collection = active_collection(client)
        points, _ = client.scroll(collection)
        client.delete(collection, models.PointIdsList(points=[points[0].id]))
    finally:
        client.close()
    with pytest.raises(ValueError, match="Indexed chunk IDs"):
        index_context(index)


@pytest.mark.parametrize(
    "problem",
    ["duplicate_case", "duplicate_expected", "missing_evidence", "unknown_group", "overlap_groups"],
)
def test_case_schema(evaluation_fixture, problem):
    _, _, _, suite, _, _ = evaluation_fixture
    suite = deepcopy(suite)
    case = suite["cases"][0]
    if problem == "duplicate_case":
        suite["access_control_cases"][0]["id"] = case["id"]
    elif problem == "duplicate_expected":
        case["expected_chunk_ids"].append(case["expected_chunk_ids"][0])
    elif problem == "missing_evidence":
        case["evidence"].pop()
    elif problem == "unknown_group":
        case["allowed_access_groups"] = ["unknown"]
    else:
        suite["access_control_cases"][0]["allowed_access_groups"].append("hr_confidential")
    with pytest.raises(ValidationError):
        RetrievalCases.model_validate(suite)


def test_access_failure_is_saved_and_cli_exits_one(evaluation_fixture, tmp_path):
    path, index, _, _, records, embedder = evaluation_fixture
    hit = {"chunk_id": records[1]["chunk_id"], "access_group": "hr_confidential"}
    output = tmp_path / "report.json"
    with (
        patch("ai_project.retrieval_evaluation.search", return_value=[hit]),
        patch("ai_project.retrieval_evaluation.OllamaEmbedder", return_value=embedder),
    ):
        assert (
            main(
                [
                    "eval-retrieval",
                    "--cases",
                    str(path),
                    "--index",
                    str(index),
                    "--output",
                    str(output),
                ]
            )
            == 1
        )
    saved = json.loads(output.read_text())
    assert not saved["access_control"]["passed"]
    assert saved["access_control"]["cases"][0]["forbidden_chunk_count"] == 1
    assert saved["relevance"]["mean_recall_at_5"] == 0.5


def test_cli_protects_cases_before_search(evaluation_fixture):
    path, index, _, _, _, _ = evaluation_fixture
    with patch("ai_project.retrieval_evaluation.evaluate_retrieval") as evaluate:
        with pytest.raises(SystemExit) as error:
            main(
                [
                    "eval-retrieval",
                    "--cases",
                    str(path),
                    "--index",
                    str(index),
                    "--output",
                    str(path),
                ]
            )
    assert error.value.code == 1
    evaluate.assert_not_called()


def test_hybrid_cli_default_output_is_separate(evaluation_fixture, tmp_path, monkeypatch):
    path, index, _, _, _, embedder = evaluation_fixture
    monkeypatch.chdir(tmp_path)
    with patch("ai_project.retrieval_evaluation.OllamaEmbedder", return_value=embedder):
        assert (
            main(
                ["eval-retrieval", "--cases", str(path), "--index", str(index), "--mode", "hybrid"]
            )
            == 0
        )
    report = json.loads((tmp_path / "results/retrieval_hybrid.json").read_text(encoding="utf-8"))
    assert report["retriever"] == "hybrid"
    assert report["retrieval_config"]["rrf_k"] == 60
    assert not (tmp_path / "results/retrieval_vector_baseline.json").exists()


def test_committed_suite_shape():
    suite = RetrievalCases.model_validate_json(
        Path("evals/retrieval_cases.json").read_text(encoding="utf-8")
    )
    assert len(suite.cases) == 12
    assert len(suite.access_control_cases) == 1
    assert suite.cases[0].question == suite.access_control_cases[0].question
    assert suite.cases[0].question == (
        "До якого числа треба використати перенесену відпустку за контрактом A?"
    )
    assert (
        sum(any("\u0400" <= char <= "\u04ff" for char in case.question) for case in suite.cases)
        == 6
    )
    assert suite.access_control_cases[0].allowed_access_groups == ["all_employees"]
    assert "hr_confidential" in suite.cases[0].allowed_access_groups
    assert {case.topic for case in suite.cases} == {
        "leave",
        "payroll",
        "attendance",
        "shifts",
        "support",
    }
