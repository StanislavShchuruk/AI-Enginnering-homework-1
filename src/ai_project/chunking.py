"""Deterministic section-aware chunking of canonical sanitized documents only."""

import hashlib
import json
import re
from itertools import groupby
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from ai_project.deduplication import stable_json
from ai_project.extraction.models import ContentBlock, ExtractedDocument, SourceLocation

VERSION = "1.0"
TOKEN_COUNTER = "unicode-word-or-punctuation-v1"
TOKEN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def count_tokens(text: str) -> int:
    """Count Unicode word runs and individual punctuation; whitespace costs zero."""
    return sum(1 for _ in TOKEN.finditer(text))


class ChunkingConfig(BaseModel):
    target_tokens: int = Field(default=400, ge=1, strict=True)
    max_tokens: int = Field(default=600, ge=1, strict=True)

    @model_validator(mode="after")
    def check_limits(self) -> "ChunkingConfig":
        if self.target_tokens > self.max_tokens:
            raise ValueError("Target tokens must not exceed maximum tokens")
        return self


class Chunk(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    token_count: int
    source_reference: str
    document_title: str
    section_path: list[str]
    version: str | None
    effective_date: str | None
    source_hash: str
    content_hash: str
    metadata: dict[str, Any]
    block_indices: list[int]
    locations: list[SourceLocation]
    pages: list[int]


def render_block(block: ContentBlock) -> str:
    if block.rows is not None:
        return "\n".join("\t".join(row) for row in block.rows)
    if block.type == "list_item":
        marker = block.marker or ("1." if block.ordered else "•")
        return "  " * (block.list_level or 0) + marker + " " + block.text
    return block.text


def split_text(text: str, limit: int) -> list[str]:
    """Prefer paragraph/line, then sentence, then word boundaries; never drop text."""
    pieces: list[str] = []
    while count_tokens(text) > limit:
        matches = list(TOKEN.finditer(text))
        end = matches[limit].start()
        # Avoid tiny fragments when there is a useful boundary in the latter half.
        minimum = matches[max(0, limit // 2 - 1)].end()
        candidates = [m.end() for m in re.finditer(r"\n+|[.!?](?:[ \t]+|$)", text[:end])]
        boundary = max((p for p in candidates if p >= minimum), default=end)
        pieces.append(text[:boundary].strip())
        text = text[boundary:].strip()
    if text:
        pieces.append(text)
    return pieces


def split_table(block: ContentBlock, limit: int, target: int) -> list[str]:
    rows = block.rows or []
    header = "\t".join(rows[0])
    budget = limit - count_tokens(header)
    if budget < 1:
        raise ValueError("Table header leaves no token budget for rows")
    pieces: list[str] = []
    current = header
    for row in rows[1:]:
        # A pathological single row is continued with the same column header.
        row_text = "\t".join(row)
        row_parts = (
            [row_text]
            if count_tokens(row_text) <= budget
            else split_text(row_text, max(1, min(budget, target - count_tokens(header))))
        )
        for part in row_parts:
            combined_size = count_tokens(current + "\n" + part)
            if current != header and (
                combined_size > limit
                or abs(combined_size - target) > abs(count_tokens(current) - target)
            ):
                pieces.append(current)
                current = header
            current += "\n" + part
    if current != header or not pieces:
        pieces.append(current)
    return pieces


def split_item(block: ContentBlock, limit: int) -> list[str]:
    marker = block.marker or ("1." if block.ordered else "•")
    prefix = "  " * (block.list_level or 0) + marker + " "
    budget = limit - count_tokens(prefix)
    if budget < 1:
        raise ValueError("List marker leaves no token budget for item text")
    return [prefix + part for part in split_text(block.text, budget)]


def semantic_blocks(payload: dict[str, Any]) -> list[tuple[int, ContentBlock]]:
    document = ExtractedDocument.model_validate(payload)
    # Honor explicit flags even for paragraph types whose extraction validator
    # derives is_semantic from type. Never allow furniture back into the stream.
    return [
        (index, block)
        for index, block in enumerate(document.blocks)
        if block.is_semantic and payload["blocks"][index].get("is_semantic", True)
    ]


def section_units(
    blocks: list[tuple[int, ContentBlock]], limit: int, target: int
) -> list[tuple[str, list[int]]]:
    """Make fitting lists/tables atomic before packing other blocks around them."""
    units: list[tuple[str, list[int]]] = []
    position = 0
    while position < len(blocks):
        index, block = blocks[position]
        if block.type == "list_item":
            items = []
            while position < len(blocks) and blocks[position][1].type == "list_item":
                items.append(blocks[position])
                position += 1
            whole = "\n".join(render_block(item) for _, item in items)
            if count_tokens(whole) <= limit:
                units.append((whole, [i for i, _ in items]))
            else:
                current, indices = "", []
                for i, item in items:
                    parts = (
                        split_item(
                            item, min(limit, max(target, count_tokens(item.marker or "1.") + 1))
                        )
                        if count_tokens(render_block(item)) > limit
                        else [render_block(item)]
                    )
                    for part in parts:
                        size = count_tokens(current + "\n" + part)
                        if current and (
                            size > limit or abs(size - target) > abs(count_tokens(current) - target)
                        ):
                            units.append((current, indices))
                            current, indices = "", []
                        current = current + "\n" + part if current else part
                        indices = list(dict.fromkeys([*indices, i]))
                if current:
                    units.append((current, indices))
            continue
        text = render_block(block)
        parts = (
            [text]
            if count_tokens(text) <= limit
            else split_table(block, limit, target)
            if block.type == "table"
            else split_text(text, target)
        )
        units.extend((part, [index]) for part in parts)
        position += 1
    return units


def chunk_document(payload: dict[str, Any], config: ChunkingConfig | None = None) -> list[Chunk]:
    config = config or ChunkingConfig()
    if payload.get("excluded_as_duplicate_of"):
        return []
    if not payload.get("sanitization_version"):
        raise ValueError("Chunking requires sanitized input")
    document = ExtractedDocument.model_validate(payload)
    chunks: list[Chunk] = []
    # Extraction already tracks hierarchy; use it without rewriting source headings.
    for section, group in groupby(semantic_blocks(payload), key=lambda pair: pair[1].section_path):
        blocks = list(group)
        current = ""
        indices: list[int] = []

        def emit(current: str, indices: list[int], section: list[str]) -> None:
            if not current:
                return
            locations = [document.blocks[i].location for i in indices]
            identity = {
                "algorithm": VERSION,
                "counter": TOKEN_COUNTER,
                "config": config.model_dump(),
                "document_id": document.document_id,
                "source_hash": payload["source_hash"],
                "content_hash": payload["content_hash"],
                "metadata": document.metadata,
                "section_path": section,
                "ordinal": len(chunks),
                "text": current,
                "block_indices": indices,
            }
            digest = hashlib.sha256(stable_json(identity).encode("utf-8")).hexdigest()
            chunks.append(
                Chunk(
                    chunk_id=f"{document.document_id}-{digest}",
                    document_id=document.document_id,
                    text=current,
                    token_count=count_tokens(current),
                    source_reference=document.source_path,
                    document_title=document.title,
                    section_path=section,
                    version=document.metadata.get("version"),
                    effective_date=document.metadata.get("effective_date"),
                    source_hash=payload["source_hash"],
                    content_hash=payload["content_hash"],
                    metadata=document.metadata,
                    block_indices=indices.copy(),
                    locations=locations,
                    pages=sorted({loc.page for loc in locations if loc.page is not None}),
                )
            )

        for text, unit_indices in section_units(blocks, config.max_tokens, config.target_tokens):
            combined = current + "\n\n" + text if current else text
            size = count_tokens(combined)
            if current and (
                size > config.max_tokens
                or abs(size - config.target_tokens)
                > abs(count_tokens(current) - config.target_tokens)
            ):
                emit(current, indices, section)
                current, indices = "", []
            current = current + "\n\n" + text if current else text
            indices = list(dict.fromkeys([*indices, *unit_indices]))
        emit(current, indices, section)
    return chunks


def fixed_size_baseline(payload: dict[str, Any], size: int = 400) -> list[str]:
    """Hard token windows over exactly the same rendered semantic input stream."""
    if size < 1:
        raise ValueError("Baseline size must be positive")
    text = "\n\n".join(render_block(block) for _, block in semantic_blocks(payload))
    matches = list(TOKEN.finditer(text))
    return [
        text[
            matches[i].start() : matches[i + size].start() if i + size < len(matches) else len(text)
        ].strip()
        for i in range(0, len(matches), size)
    ]


def write_chunks(
    payloads: list[dict[str, Any]], output: Path, config: ChunkingConfig
) -> dict[str, Any]:
    chunks: list[Chunk] = []
    documents = []
    for payload in sorted(payloads, key=lambda value: value["document_id"]):
        if payload.get("excluded_as_duplicate_of"):
            continue
        generated = chunk_document(payload, config)
        chunks.extend(generated)
        documents.append(
            {
                "document_id": payload["document_id"],
                "chunk_count": len(generated),
                "source_hash": payload["source_hash"],
                "content_hash": payload["content_hash"],
            }
        )
    with (output / "chunks.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for chunk in chunks:
            stream.write(
                json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n"
            )
    manifest = {
        "chunking_version": VERSION,
        "token_counter": TOKEN_COUNTER,
        **config.model_dump(),
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "documents": documents,
        "chunks_file": "chunks.jsonl",
        "hash_types": {
            "source_hash": "SHA-256 of original source bytes",
            "content_hash": "SHA-256 of normalized semantic content before redaction",
        },
    }
    (output / "chunking_manifest.json").write_text(stable_json(manifest), encoding="utf-8")
    comparison = compare_chunking(payloads, config)
    (output / "chunking_comparison.json").write_text(stable_json(comparison), encoding="utf-8")
    return manifest


def compare_chunking(payloads: list[dict[str, Any]], config: ChunkingConfig) -> dict[str, Any]:
    """Record real boundaries, rather than infer quality from chunk counts alone."""
    examples = []
    roles = {
        "M11": "step-by-step manual",
        "C02": "contract with table",
        "S03": "short support guide",
    }
    for payload in sorted(payloads, key=lambda value: value["document_id"]):
        identifier = payload["document_id"]
        if identifier not in roles or payload.get("excluded_as_duplicate_of"):
            continue
        structured = chunk_document(payload, config)
        baseline = fixed_size_baseline(payload)
        blocks = semantic_blocks(payload)
        # Locate the first fixed-size boundary in the original semantic blocks.
        token_blocks = [
            index for index, block in blocks for _ in range(count_tokens(render_block(block)))
        ]
        boundary = None
        if len(baseline) > 1:
            left, right = token_blocks[399], token_blocks[400]
            by_index = dict(blocks)
            boundary = {
                "after_token": 400,
                "left_block_index": left,
                "right_block_index": right,
                "left_type": by_index[left].type,
                "right_type": by_index[right].type,
                "left_section": by_index[left].section_path,
                "right_section": by_index[right].section_path,
                "splits_block": left == right,
                "left_text": baseline[0][-180:],
                "right_text": baseline[1][:180],
            }
        relevant = next(
            (
                chunk
                for chunk in structured
                if boundary and boundary["left_block_index"] in chunk.block_indices
            ),
            structured[0] if structured else None,
        )
        protected = []
        for kind, members in groupby(blocks, key=lambda pair: pair[1].type):
            members = list(members)
            if kind not in {"table", "list_item"}:
                continue
            indices = {index for index, _ in members}
            protected.append(
                {
                    "type": kind,
                    "block_indices": sorted(indices),
                    "token_count": sum(count_tokens(render_block(block)) for _, block in members),
                    "structured_chunk_ids": [
                        chunk.chunk_id
                        for chunk in structured
                        if indices.intersection(chunk.block_indices)
                    ],
                    "row_count": sum(len(block.rows or []) for _, block in members),
                    "markers": [block.marker for _, block in members if block.marker],
                }
            )
        examples.append(
            {
                "document_id": identifier,
                "title": payload["title"],
                "role": roles[identifier],
                "semantic_tokens": sum(count_tokens(render_block(block)) for _, block in blocks),
                "structured_count": len(structured),
                "baseline_count": len(baseline),
                "baseline_boundary": boundary,
                "protected_structures": protected,
                "structured_boundary": {
                    "section_path": relevant.section_path,
                    "block_indices": relevant.block_indices,
                    "token_count": relevant.token_count,
                    "start": relevant.text[:180],
                    "end": relevant.text[-180:],
                }
                if relevant
                else None,
            }
        )
    return {
        "token_counter": TOKEN_COUNTER,
        "baseline_tokens": 400,
        "structure_config": config.model_dump(),
        "documents": examples,
    }
