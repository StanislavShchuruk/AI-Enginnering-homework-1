"""Exact, deterministic deduplication using original bytes and pre-redaction content."""

import hashlib
import json
import re
from collections import defaultdict
from typing import Any

from ai_project.extraction.models import ExtractedDocument


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def source_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_content(document: ExtractedDocument) -> bytes:
    def clean(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    blocks = []
    for block in document.semantic_blocks:
        blocks.append(
            {
                "type": block.type,
                "text": clean(block.text) if block.rows is None else None,
                "rows": [[clean(cell) for cell in row] for row in block.rows]
                if block.rows is not None
                else None,
                "section_path": [clean(value) for value in block.section_path],
                "heading_level": block.heading_level,
                "ordered": block.ordered,
                "list_level": block.list_level,
                "marker": clean(block.marker) if block.marker else None,
            }
        )
    return stable_json({"title": clean(document.title), "blocks": blocks}).encode("utf-8")


def content_hash(document: ExtractedDocument) -> str:
    return source_hash(canonical_content(document))


def deduplicate(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Report global matches, excluding only active documents with equal policy metadata.

    Hashes must be calculated before redaction. Historical versions always remain.
    Differences in any non-identity metadata prevent exclusion, particularly access.
    """
    content_groups: dict[str, list[str]] = defaultdict(list)
    source_groups: dict[str, list[str]] = defaultdict(list)
    eligible: dict[str, list[str]] = defaultdict(list)
    for record in sorted(records, key=lambda value: value["document_id"]):
        identifier = record["document_id"]
        content_groups[record["content_hash"]].append(identifier)
        source_groups[record["source_hash"]].append(identifier)
        metadata = record["metadata"]
        if metadata.get("status") != "active":
            continue
        scope = {
            key: value
            for key, value in metadata.items()
            if key not in {"document_id", "path", "format", "title"}
        }
        key = stable_json({"content_hash": record["content_hash"], "scope": scope})
        eligible[key].append(identifier)
    exclusions = []
    for identifiers in eligible.values():
        for identifier in identifiers[1:]:
            exclusions.append(
                {
                    "document_id": identifier,
                    "kept_document_id": identifiers[0],
                    "reason": "identical_pre_redaction_content_and_policy_metadata",
                }
            )
    return {
        "duplicate_groups": [
            {"content_hash": key, "document_ids": value}
            for key, value in sorted(content_groups.items())
            if len(value) > 1
        ],
        "source_duplicate_groups": [
            {"source_hash": key, "document_ids": value}
            for key, value in sorted(source_groups.items())
            if len(value) > 1
        ],
        "excluded_documents": sorted(exclusions, key=lambda value: value["document_id"]),
    }
