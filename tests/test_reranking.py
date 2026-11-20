"""Offline reranking and scorer-boundary security checks; no model downloads."""

import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from ai_project.reranking import CrossEncoderReranker, passage_text, rerank_candidates
from ai_project.retrieval import build_index, search


class FakeReranker:
    model_name = "fake-reranker"

    def __init__(self, promoted_text: str = "") -> None:
        self.promoted_text = promoted_text
        self.seen: list[str] = []

    def score(self, question: str, passages: list[str]) -> list[float]:
        self.seen.extend(passages)
        return [10.0 if self.promoted_text and self.promoted_text in p else 0.0 for p in passages]


@pytest.fixture
def rerank_index(tmp_path):
    records = [
        {
            "chunk_id": f"C01-{i:064x}",
            "document_id": "C01",
            "token_count": 2,
            "text": f"ATT-LOCK {'RESTRICTED' if i < 25 else 'PUBLIC'} record {i} end",
            "document_title": "Attendance title",
            "section_path": ["Correction section"],
            "source_reference": "C01.docx",
            "version": "2.0",
            "effective_date": None,
            "source_hash": "a" * 64,
            "content_hash": "b" * 64,
            "metadata": {"access_group": "hr_confidential" if i < 25 else "all_employees"},
            "block_indices": [],
            "locations": [],
            "pages": [],
        }
        for i in range(55)
    ]
    source = tmp_path / "chunks.jsonl"
    source.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    index = tmp_path / "index"
    embedder = Mock()
    embedder.embed.side_effect = lambda texts, model: [[1.0, 0.0] for _ in texts]
    build_index(source, index, embedder=embedder)
    return index, embedder


def test_candidate_outside_initial_five_is_scored_and_promoted(rerank_index):
    index, embedder = rerank_index
    pool = search("ATT-LOCK", index, top_k=40, mode="hybrid", embedder=embedder)
    assert len(pool) > 5
    target = pool[7]
    scorer = FakeReranker(target["text"])
    trace = {}
    final = search(
        "ATT-LOCK",
        index,
        mode="hybrid-rerank",
        embedder=embedder,
        reranker=scorer,
        diagnostics=trace,
    )
    assert final[0]["chunk_id"] == target["chunk_id"]
    assert final[0]["rrf_rank"] == 8
    assert final[0]["score"] == 10
    assert len(final) == 5
    assert len(scorer.seen) == len(pool) == len(trace["candidate_ids"])
    assert len(set(trace["candidate_ids"])) == len(pool)
    assert passage_text(target) in scorer.seen
    assert scorer.seen[0].startswith("Attendance title\nCorrection section\n\n")


def test_acl01_employee_only_restricted_text_never_reaches_scorer(rerank_index):
    index, embedder = rerank_index
    from pathlib import Path

    suite = json.loads(Path("evals/retrieval_cases.json").read_text(encoding="utf-8"))
    acl = next(case for case in suite["access_control_cases"] if case["id"] == "ACL01")
    scorer = FakeReranker()
    trace = {}
    final = search(
        acl["question"],
        index,
        mode="hybrid-rerank",
        embedder=embedder,
        access_groups=acl["allowed_access_groups"],
        reranker=scorer,
        diagnostics=trace,
    )
    assert len(scorer.seen) > 5
    assert all("RESTRICTED" not in text for text in scorer.seen)
    assert all("PUBLIC" in text for text in scorer.seen)
    assert all(hit["access_group"] == "all_employees" for hit in final)
    assert set(trace["candidate_access_groups"]) == {"all_employees"}


def test_score_ties_keep_original_rrf_order(rerank_index):
    index, embedder = rerank_index
    before = search("ATT-LOCK", index, mode="hybrid", embedder=embedder)
    after = search(
        "ATT-LOCK", index, mode="hybrid-rerank", embedder=embedder, reranker=FakeReranker()
    )
    assert [hit["chunk_id"] for hit in after] == [hit["chunk_id"] for hit in before]
    assert [hit["rrf_rank"] for hit in after] == [1, 2, 3, 4, 5]


def test_scorer_boundary_rejects_unauthorized_candidates():
    scorer = Mock()
    with pytest.raises(ValueError, match="Unauthorized"):
        rerank_candidates(
            "question", [{"access_group": "hr_confidential"}], scorer, ["all_employees"]
        )
    scorer.score.assert_not_called()


@pytest.mark.parametrize("scores", [[], [float("nan")], [True], [[1.0]]])
def test_invalid_reranker_scores_rejected(scores):
    scorer = Mock()
    scorer.score.return_value = scores
    pool = [
        {
            "document_title": "Title",
            "section_path": [],
            "text": "Body",
            "access_group": "all_employees",
            "score": 0.1,
        }
    ]
    with pytest.raises(ValueError, match="finite numeric"):
        rerank_candidates("question", pool, scorer, ["all_employees"])


def test_crossencoder_pairs_and_batches_without_importing_real_dependency():
    model = Mock()
    model.predict.return_value = [0.1, 0.2]
    factory = Mock(return_value=model)
    with patch.dict(
        sys.modules,
        {
            "sentence_transformers": SimpleNamespace(CrossEncoder=factory),
            "torch": SimpleNamespace(nn=SimpleNamespace(Identity=lambda: "identity")),
        },
    ):
        scorer = CrossEncoderReranker(batch_size=2)
        assert scorer.score("question", ["passage 1", "passage 2"]) == [0.1, 0.2]
    assert model.predict.call_args.args[0] == [
        ("question", "passage 1"),
        ("question", "passage 2"),
    ]
    assert model.predict.call_args.kwargs["batch_size"] == 2
    assert factory.call_args.kwargs["trust_remote_code"] is False
    assert factory.call_args.kwargs["token"] is False


def test_base_modes_do_not_import_or_initialize_reranker(rerank_index):
    index, embedder = rerank_index
    with patch.dict(sys.modules, {"sentence_transformers": None, "torch": None}):
        for mode in ["vector", "hybrid"]:
            assert search("ATT-LOCK", index, mode=mode, embedder=embedder)
        with pytest.raises(ValueError, match="optional reranker"):
            CrossEncoderReranker()
