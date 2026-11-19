"""Offline tests use real persistent Qdrant with deterministic fake embeddings."""

import hashlib
import json
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from qdrant_client import QdrantClient

from ai_project.cli import main
from ai_project.retrieval import (
    OllamaEmbedder,
    active_collection,
    build_index,
    embedding_text,
    load_chunks,
    search,
    validate_vectors,
)


def record(number: int, group: str = "all_employees") -> dict:
    return {
        "chunk_id": f"C01-{number:064x}",
        "document_id": "C01",
        "text": f"body {number}",
        "token_count": 2,
        "source_reference": "contracts/C01.docx",
        "document_title": "Contract",
        "section_path": ["4 Leave and sickness"],
        "version": "2.0",
        "effective_date": "2026-09-01",
        "source_hash": "a" * 64,
        "content_hash": "b" * 64,
        "metadata": {"access_group": group},
        "block_indices": [1],
        "locations": [],
        "pages": [],
    }


def write_records(path: Path, records: list[dict]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


def fake_embedder() -> Mock:
    embedder = Mock()
    embedder.embed.side_effect = lambda texts, model: [
        [1.0, 0.0] if "body 1" in t or "question" in t else [0.8, 0.6] for t in texts
    ]
    return embedder


@pytest.mark.parametrize(
    "change",
    [
        {"chunk_id": "bad"},
        {"text": " "},
        {"metadata": {}},
        {"metadata": {"access_group": "unknown"}},
        {"metadata": {"access_group": []}},
        {"token_count": "2"},
        {"token_count": 0},
        {"source_hash": "invalid"},
        {"content_hash": "invalid"},
        {"unexpected": True},
        {"section_path": [""]},
    ],
)
def test_invalid_records_rejected_before_embedding(tmp_path, change):
    source = write_records(tmp_path / "chunks.jsonl", [{**record(1), **change}])
    embedder = fake_embedder()
    with pytest.raises(ValueError, match="line 1"):
        build_index(source, tmp_path / "index", embedder=embedder)
    embedder.embed.assert_not_called()
    assert not (tmp_path / "index").exists()


@pytest.mark.parametrize("content", ["", "\n", "{}\n", "not json\n"])
def test_empty_malformed_input(tmp_path, content):
    source = tmp_path / "chunks.jsonl"
    source.write_text(content)
    with pytest.raises(ValueError):
        load_chunks(source)


def test_duplicate_ids(tmp_path):
    with pytest.raises(ValueError, match="line 2"):
        load_chunks(write_records(tmp_path / "chunks.jsonl", [record(1), record(1)]))


@pytest.mark.parametrize(
    "vectors", [[], [[0, 0]], [[float("nan"), 1]], [[True, 1]], [[1]], [[1, 0], [1, 0]]]
)
def test_invalid_vectors(vectors):
    with pytest.raises(ValueError):
        validate_vectors(vectors, 1, 2)


def test_build_reopen_filter_and_rebuild(tmp_path):
    source = write_records(
        tmp_path / "chunks.jsonl",
        [
            record(1, "hr_confidential"),
            record(2),
            record(3, "managers_hr"),
        ],
    )
    index = tmp_path / "index"
    embedder = fake_embedder()
    metadata = build_index(source, index, model="test-model", batch_size=2, embedder=embedder)
    assert metadata.chunk_count == 3
    assert metadata.source_sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert metadata.vector_dimension == 2
    assert [len(c.args[0]) for c in embedder.embed.call_args_list] == [2, 1]
    chunks, _ = load_chunks(source)
    assert embedder.embed.call_args_list[0].args[0][0] == embedding_text(chunks[0])
    assert "Contract\n4 Leave and sickness\n\nbody 1" == embedding_text(chunks[0])

    # The denied HR hit scores highest. Filtering before top-1 must find the allowed hit.
    public = search("question", index, top_k=1, embedder=embedder)
    assert public[0]["chunk_id"] == record(2)["chunk_id"]
    hr = search(
        "question", index, access_groups=["all_employees", "hr_confidential"], embedder=embedder
    )
    assert hr[0]["chunk_id"] == record(1)["chunk_id"]
    assert hr[0]["rank"] == 1
    assert hr[0]["version"] == "2.0"
    assert embedder.embed.call_args.args == (["question"], "test-model")

    build_index(source, index, embedder=embedder)
    with closing(QdrantClient(path=str(index / "qdrant"))) as client:
        assert client.count(active_collection(client)).count == 3
        assert len(client.get_collections().collections) == 1
    write_records(source, [record(2)])
    build_index(source, index, embedder=embedder)
    with closing(QdrantClient(path=str(index / "qdrant"))) as client:
        points, _ = client.scroll(active_collection(client))
        assert [p.payload["chunk_id"] for p in points] == [record(2)["chunk_id"]]


def test_failed_rebuild_keeps_previous_index(tmp_path):
    source = write_records(tmp_path / "chunks.jsonl", [record(1), record(2)])
    index = tmp_path / "index"
    build_index(source, index, embedder=fake_embedder())
    bad = Mock()
    bad.embed.side_effect = [[[1, 0]], [[1, 0, 0]]]
    with pytest.raises(ValueError, match="dimensions"):
        build_index(source, index, batch_size=1, embedder=bad)
    assert len(search("question", index, embedder=fake_embedder())) == 2
    with closing(QdrantClient(path=str(index / "qdrant"))) as client:
        assert len(client.get_collections().collections) == 1


def test_ollama_batch_request():
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = b'{"embeddings": [[1,0], [0,1]]}'
    with patch("ai_project.retrieval.build_opener") as opener:
        opener.return_value.open.return_value = response
        assert OllamaEmbedder().embed(["one", "two"], "bge-m3") == [[1, 0], [0, 1]]
        request = opener.return_value.open.call_args.args[0]
        assert request.full_url == "http://localhost:11434/api/embed"
        assert json.loads(request.data) == {
            "model": "bge-m3",
            "input": ["one", "two"],
            "truncate": False,
        }


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://example.com",
        "http://localhost:11434/path",
        "http://user@localhost",
    ],
)
def test_only_local_endpoint(url):
    with pytest.raises(ValueError):
        OllamaEmbedder(url)


def test_cli_defaults_and_hr_option(capsys):
    with patch("ai_project.retrieval.search", return_value=[]) as query:
        assert main(["search", "question"]) == 0
        assert query.call_args.kwargs["access_groups"] == ["all_employees"]
        assert query.call_args.kwargs["top_k"] == 5
        assert main(["search", "question", "--hr-access"]) == 0
        assert query.call_args.kwargs["access_groups"] == ["all_employees", "hr_confidential"]


def test_missing_index_does_not_embed(tmp_path):
    embedder = fake_embedder()
    with pytest.raises(ValueError, match="No local index"):
        search("question", tmp_path, embedder=embedder)
    embedder.embed.assert_not_called()
