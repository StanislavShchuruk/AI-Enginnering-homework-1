"""Offline Unicode, BM25, fusion, access control and mode-selection checks."""

import json
import math
from unittest.mock import Mock, patch

import pytest
from qdrant_client import QdrantClient

from ai_project.cli import main
from ai_project.lexical import BM25Index, reciprocal_rank_fusion, tokenize
from ai_project.retrieval import build_index, search


def payload(chunk_id, text="", group="all_employees", title="", section=None):
    return {
        "chunk_id": chunk_id,
        "text": text,
        "access_group": group,
        "document_title": title,
        "section_path": section or [],
    }


def test_unicode_and_compound_tokens():
    assert tokenize("ATT-LOCK v1.8 ВІДПУСТКА п’ятницю") == [
        "att-lock",
        "att",
        "lock",
        "v1.8",
        "v1",
        "8",
        "відпустка",
        "п'ятницю",
    ]
    assert tokenize("ATT‑LOCK V1.8") == tokenize("att-lock v1.8")
    assert tokenize("п’ятницю") == tokenize("п'ятницю")


def test_bm25_known_single_document_score():
    index = BM25Index([payload("a", "leave leave")])
    hit = index.search("leave", ["all_employees"])[0]
    assert hit["score"] == pytest.approx(math.log1p(0.5 / 1.5) * 2 * 2.5 / (2 + 1.5))


def test_bm25_indexes_title_section_and_body():
    index = BM25Index(
        [
            payload("a", "unrelated", title="Payroll"),
            payload("b", "unrelated", section=["Attendance"]),
            payload("c", "відпустка ATT-LOCK v1.8"),
        ]
    )
    for query, expected in [
        ("PAYROLL", "a"),
        ("attendance", "b"),
        ("ВІДПУСТКА", "c"),
        ("att-lock", "c"),
        ("v1.8", "c"),
    ]:
        assert index.search(query, ["all_employees"])[0]["chunk_id"] == expected
    assert index.search("unknown", ["all_employees"]) == []
    assert index.search("!?!", ["all_employees"]) == []


def test_bm25_filters_before_cutoff_and_breaks_ties_by_id():
    index = BM25Index(
        [
            payload("secret", "leave " * 100, "hr_confidential"),
            payload("b", "leave"),
            payload("a", "leave"),
            payload("missing-group", "leave", None),
        ]
    )
    assert index.search("leave", ["all_employees"], limit=1)[0]["chunk_id"] == "a"
    assert index.search("leave", ["hr_confidential"], limit=1)[0]["chunk_id"] == "secret"
    assert index.search("leave", [], limit=1) == []


def test_rrf_equal_weights_overlap_dedup_and_raw_score_independence():
    vector = [dict(payload("a"), score=0.99), dict(payload("b"), score=0.01)]
    lexical = [dict(payload("b"), score=1000), dict(payload("c"), score=999)]
    fused = reciprocal_rank_fusion(vector, lexical)
    assert [hit["chunk_id"] for hit in fused] == ["b", "a", "c"]
    assert fused[0]["score"] == pytest.approx(1 / 62 + 1 / 61)
    assert fused[1]["score"] == pytest.approx(1 / 61)
    assert [hit["rank"] for hit in fused] == [1, 2, 3]
    assert reciprocal_rank_fusion([vector[0], vector[0], vector[1]], lexical) == fused


def test_rrf_deterministic_ties_empty_branch_and_top_k():
    a, b = payload("a"), payload("b")
    fused = reciprocal_rank_fusion([a, b], [b, a])
    assert [hit["chunk_id"] for hit in fused] == ["a", "b"]
    assert fused == reciprocal_rank_fusion([b, a], [a, b])
    assert reciprocal_rank_fusion([], [], top_k=5) == []
    assert len(reciprocal_rank_fusion([a, b], [], top_k=1)) == 1


@pytest.fixture
def hybrid_index(tmp_path):
    records = [
        {
            "chunk_id": f"C01-{i:064x}",
            "document_id": "C01",
            "text": "ATT-LOCK correction",
            "document_title": "Attendance Guide",
            "section_path": ["Corrections"],
            "source_reference": "C01.docx",
            "token_count": 3,
            "version": "2.0",
            "effective_date": "2026-09-01",
            "source_hash": "a" * 64,
            "content_hash": "b" * 64,
            "metadata": {"access_group": "hr_confidential" if i < 25 else "all_employees"},
            "block_indices": [],
            "locations": [],
            "pages": [],
        }
        for i in range(50)
    ]
    source = tmp_path / "chunks.jsonl"
    source.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    embedder = Mock()
    embedder.embed.side_effect = lambda texts, model: [[1.0, 0.0] for _ in texts]
    index = tmp_path / "index"
    build_index(source, index, embedder=embedder)
    embedder.reset_mock()
    return index, source, embedder


def test_hybrid_both_branches_filter_before_twenty_candidates(hybrid_index):
    index, _, embedder = hybrid_index
    vector_search = QdrantClient.query_points
    lexical_search = BM25Index.search
    captured = {}

    def capture_vector(client, *args, **kwargs):
        result = vector_search(client, *args, **kwargs)
        captured["vector"] = result.points
        return result

    def capture_bm25(instance, *args, **kwargs):
        result = lexical_search(instance, *args, **kwargs)
        captured["bm25"] = result
        return result

    with (
        patch.object(
            QdrantClient, "query_points", autospec=True, side_effect=capture_vector
        ) as vector,
        patch.object(BM25Index, "search", autospec=True, side_effect=capture_bm25) as lexical,
    ):
        results = search("ATT-LOCK", index, mode="hybrid", embedder=embedder)
    assert len(results) == 5
    assert all(hit["access_group"] == "all_employees" for hit in results)
    assert vector.call_args.kwargs["limit"] == 20
    assert lexical.call_args.kwargs["limit"] == 20
    assert len(captured["vector"]) == len(captured["bm25"]) == 20
    assert all(hit.payload["access_group"] == "all_employees" for hit in captured["vector"])
    assert all(hit["access_group"] == "all_employees" for hit in captured["bm25"])
    assert results == search("ATT-LOCK", index, mode="hybrid", embedder=embedder)
    hr = search(
        "ATT-LOCK", index, mode="hybrid", access_groups=["hr_confidential"], embedder=embedder
    )
    assert all(hit["access_group"] == "hr_confidential" for hit in hr)


def test_vector_default_and_hybrid_cli_dispatch():
    with patch("ai_project.retrieval.search", return_value=[]) as query:
        assert main(["search", "ATT-LOCK"]) == 0
        assert query.call_args.kwargs["mode"] == "vector"
        assert main(["search", "ATT-LOCK", "--mode", "hybrid"]) == 0
        assert query.call_args.kwargs["mode"] == "hybrid"


def test_hybrid_refuses_changed_canonical_source_before_embedding(hybrid_index):
    index, source, embedder = hybrid_index
    source.write_text(
        source.read_text(encoding="utf-8").replace("ATT-LOCK", "ATT-422"), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="Canonical chunks differ"):
        search("ATT-LOCK", index, mode="hybrid", embedder=embedder)
    embedder.embed.assert_not_called()
