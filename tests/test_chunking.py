"""Offline chunk boundaries, content preservation and canonical-source regressions."""

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_project.chunking import (
    ChunkingConfig,
    chunk_document,
    count_tokens,
    fixed_size_baseline,
    render_block,
    semantic_blocks,
)
from ai_project.extraction.common import assign_sections
from ai_project.extraction.models import ContentBlock, ExtractedDocument, SourceLocation
from ai_project.ingestion import process_corpus
from ai_project.sanitization import sanitize_document


def payload(blocks: list[ContentBlock]) -> dict:
    assign_sections(blocks)
    document = ExtractedDocument(
        document_id="T01",
        title="Policy",
        source_path="data/documents/T01.md",
        format="markdown",
        metadata={
            "version": "1",
            "effective_date": "2026-01-01",
            "access_group": "hr_confidential",
            "status": "superseded",
        },
        blocks=blocks,
    )
    return {
        **sanitize_document(document).model_dump(),
        "source_hash": "source",
        "content_hash": "pre-redaction-content",
    }


def heading(text: str, level: int = 1) -> ContentBlock:
    return ContentBlock(type="heading", text=text, heading_level=level)


def test_sections_metadata_flags_and_stable_ids() -> None:
    data = payload(
        [
            heading("Policy"),
            heading("Leave", 2),
            ContentBlock(type="paragraph", text="Request leave.", location=SourceLocation(page=2)),
            ContentBlock(type="footer", text="FURNITURE"),
            ContentBlock(type="paragraph", text="EXPLICITLY EXCLUDED"),
            heading("Pay", 2),
            ContentBlock(type="paragraph", text="Check payment."),
        ]
    )
    data["blocks"][4]["is_semantic"] = False
    chunks = chunk_document(data)
    assert chunks == chunk_document(data)
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
    assert [chunk.section_path for chunk in chunks] == [
        ["Policy"],
        ["Policy", "Leave"],
        ["Policy", "Pay"],
    ]
    assert "FURNITURE" not in str(chunks) and "EXPLICITLY EXCLUDED" not in str(chunks)
    assert chunks[1].pages == [2]
    assert chunks[1].locations[-1].page == 2
    for chunk in chunks:
        assert chunk.source_hash == "source" and chunk.content_hash == "pre-redaction-content"
        assert chunk.metadata == data["metadata"]
        assert chunk.source_reference == data["source_path"]
        assert chunk.version == "1" and chunk.effective_date == "2026-01-01"
    data["blocks"][2]["text"] += " Changed."
    assert chunk_document(data)[1].chunk_id != chunks[1].chunk_id
    data["excluded_as_duplicate_of"] = "T00"
    assert chunk_document(data) == []


def test_fitting_procedure_and_table_remain_whole() -> None:
    data = payload(
        [
            heading("Procedure"),
            ContentBlock(type="paragraph", text="Context " * 18),
            *[
                ContentBlock(
                    type="list_item", text=f"Perform operation {i}", ordered=True, marker=f"{i}."
                )
                for i in range(7, 11)
            ],
            ContentBlock(type="table", text="placeholder", rows=[["Item", "Value"], ["A", "10"]]),
        ]
    )
    chunks = chunk_document(data, ChunkingConfig(target_tokens=20, max_tokens=40))
    procedure = next(chunk for chunk in chunks if "7." in chunk.text)
    assert all(f"{i}. Perform operation {i}" in procedure.text for i in range(7, 11))
    assert any("Item\tValue\nA\t10" in chunk.text for chunk in chunks)
    assert all(chunk.token_count <= 40 for chunk in chunks)


def test_long_lists_preserve_numbering_and_every_item() -> None:
    data = payload(
        [
            ContentBlock(
                type="list_item",
                text=f"Operation number {i} then confirm",
                ordered=True,
                marker=f"{i}.",
            )
            for i in range(12, 30)
        ]
    )
    chunks = chunk_document(data, ChunkingConfig(target_tokens=20, max_tokens=25))
    joined = "\n".join(chunk.text for chunk in chunks)
    for i in range(12, 30):
        assert joined.count(f"{i}. Operation number {i} then confirm") == 1
    assert all(chunk.token_count <= 25 for chunk in chunks)


def test_packing_approaches_target_and_settings_affect_ids() -> None:
    data = payload([ContentBlock(type="paragraph", text="word " * 190) for _ in range(3)])
    chunks = chunk_document(data)
    assert [chunk.token_count for chunk in chunks] == [380, 190]
    changed = chunk_document(data, ChunkingConfig(target_tokens=300))
    assert [chunk.chunk_id for chunk in changed] != [chunk.chunk_id for chunk in chunks]


def test_header_without_row_budget_fails_instead_of_exceeding_maximum() -> None:
    data = payload(
        [ContentBlock(type="table", text="placeholder", rows=[["header " * 10], ["row " * 10]])]
    )
    with pytest.raises(ValueError, match="header"):
        chunk_document(data, ChunkingConfig(target_tokens=5, max_tokens=10))


def test_tables_repeat_headers_and_preserve_rows() -> None:
    rows = [["Code", "Description"], *[[f"R{i}", f"Value for row {i}"] for i in range(20)]]
    data = payload([ContentBlock(type="table", text="placeholder", rows=rows)])
    chunks = chunk_document(data, ChunkingConfig(target_tokens=20, max_tokens=25))
    assert len(chunks) > 1
    assert all(chunk.text.startswith("Code\tDescription\n") for chunk in chunks)
    assert all(chunk.token_count <= 25 for chunk in chunks)
    actual = [line for chunk in chunks for line in chunk.text.splitlines()[1:]]
    assert actual == ["\t".join(row) for row in rows[1:]]


@pytest.mark.parametrize("kind", ["paragraph", "list_item", "table"])
def test_pathological_single_block_is_bounded_and_lossless(kind: str) -> None:
    text = " ".join(f"word{i}." for i in range(75))
    args = {"type": kind, "text": text}
    if kind == "list_item":
        args.update(ordered=True, marker="9.")
    if kind == "table":
        args["rows"] = [["Header"], [text]]
    data = payload([ContentBlock(**args)])
    chunks = chunk_document(data, ChunkingConfig(target_tokens=20, max_tokens=30))
    assert len(chunks) > 1 and all(chunk.token_count <= 30 for chunk in chunks)
    joined = " ".join(chunk.text for chunk in chunks)
    assert all(joined.count(f"word{i}.") == 1 for i in range(75))
    if kind == "table":
        assert all(chunk.text.startswith("Header\n") for chunk in chunks)
    if kind == "list_item":
        assert all(chunk.text.startswith("9. ") for chunk in chunks)


def test_counter_baseline_and_configuration() -> None:
    assert count_tokens("Привіт, PeopleFlow! [EMAIL] 12.5") == 10
    data = payload([ContentBlock(type="paragraph", text="Check settings. " * 450)])
    baseline = fixed_size_baseline(data)
    assert [count_tokens(text) for text in baseline] == [400, 400, 400, 150]
    original = "\n\n".join(render_block(block) for _, block in semantic_blocks(data))
    assert re.findall(r"\w+|[^\w\s]", " ".join(baseline)) == re.findall(r"\w+|[^\w\s]", original)
    for options in [{"target_tokens": 0}, {"max_tokens": 399}, {"target_tokens": True}]:
        with pytest.raises(ValidationError):
            ChunkingConfig(**options)
    del data["sanitization_version"]
    with pytest.raises(ValueError, match="sanitized"):
        chunk_document(data)


def test_pipeline_excludes_copies_keeps_history_and_is_repeatable(tmp_path: Path) -> None:
    (tmp_path / "data/documents").mkdir(parents=True)
    entries = []
    for identifier, status in [("T01", "active"), ("T02", "active"), ("T03", "superseded")]:
        entry = {
            "document_id": identifier,
            "title": "Policy",
            "format": "html",
            "path": f"data/documents/{identifier}.html",
            "access_group": "all_employees",
            "version": "1",
            "effective_date": "2026-01-01",
            "status": status,
        }
        entries.append(entry)
        (tmp_path / entry["path"]).write_text(
            "<header>FURNITURE</header><h1>Policy</h1><p>Employee: Alice Morgan. "
            "alice.morgan@example.com</p><footer>FOOTER</footer>",
            encoding="utf-8",
        )
    manifest = tmp_path / "data/manifest.json"
    manifest.write_text(json.dumps(entries), encoding="utf-8")
    report = process_corpus(tmp_path, manifest, tmp_path / "run1")
    manifest.write_text(json.dumps(list(reversed(entries))), encoding="utf-8")
    process_corpus(tmp_path, manifest, tmp_path / "run2")
    assert report["included_documents"] == report["chunking"]["document_count"] == 2
    assert report["excluded_documents"][0]["document_id"] == "T02"
    for name in [
        "chunks.jsonl",
        "chunking_manifest.json",
        "chunking_comparison.json",
        "report.json",
    ]:
        assert (tmp_path / "run1" / name).read_bytes() == (tmp_path / "run2" / name).read_bytes()
    content = (tmp_path / "run1/chunks.jsonl").read_text(encoding="utf-8")
    chunks = [json.loads(line) for line in content.splitlines()]
    assert {chunk["document_id"] for chunk in chunks} == {"T01", "T03"}
    assert all(secret not in content for secret in ["FURNITURE", "FOOTER", "Alice", "@example"])
    assert "[PERSON]" in content and "[EMAIL]" in content


def test_full_corpus_chunk_invariants(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    report = process_corpus(root, root / "data/manifest.json", tmp_path / "corpus")
    assert report["withheld_documents"] == 0
    assert report["chunking"]["document_count"] == report["included_documents"] == 32
    chunks = [
        json.loads(line)
        for line in (tmp_path / "corpus/chunks.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len({c["chunk_id"] for c in chunks}) == len(chunks)
    assert all(0 < c["token_count"] <= 600 for c in chunks)
    assert {"M06", "F03", "F05"} <= {c["document_id"] for c in chunks}
    for identifier in {c["document_id"] for c in chunks}:
        data = json.loads(
            (tmp_path / f"corpus/documents/{identifier}.json").read_text(encoding="utf-8")
        )
        included = [c for c in chunks if c["document_id"] == identifier]
        original = "\n\n".join(render_block(block) for _, block in semantic_blocks(data))
        actual = "\n\n".join(c["text"] for c in included)
        assert re.findall(r"\w+|[^\w\s]", actual) == re.findall(r"\w+|[^\w\s]", original)
        indices = {i for c in included for i in c["block_indices"]}
        assert indices == {i for i, _ in semantic_blocks(data)}
        for chunk in included:
            assert all(
                data["blocks"][i]["section_path"] == chunk["section_path"]
                for i in chunk["block_indices"]
            )
            assert chunk["source_hash"] == data["source_hash"]
            assert chunk["content_hash"] == data["content_hash"]
    comparison = json.loads((tmp_path / "corpus/chunking_comparison.json").read_text())
    assert {d["document_id"] for d in comparison["documents"]} == {"M11", "C02", "S03"}
    assert all(d["baseline_boundary"] for d in comparison["documents"])
