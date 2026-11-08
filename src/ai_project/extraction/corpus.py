"""Manifest-driven corpus extraction and inspection report."""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, TypeAdapter

from . import extract_document
from .models import DocumentFormat


class ManifestSource(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    document_id: str
    title: str
    path: str
    format: DocumentFormat


def extract_corpus(root: Path, manifest: Path, output: Path) -> dict[str, Any]:
    root, manifest, output = root.resolve(), manifest.resolve(), output.resolve()
    if manifest.suffix.lower() != ".json" or manifest.name.startswith(".env"):
        raise ValueError("Manifest must be a JSON file")
    entries = TypeAdapter(list[ManifestSource]).validate_json(manifest.read_text(encoding="utf-8"))
    ids = [entry.document_id for entry in entries]
    if len({x.casefold() for x in ids}) != len(ids) or any(
        not re.fullmatch(r"[\w-]+", x) or x.casefold() == "report" for x in ids
    ):
        raise ValueError("Document IDs must be unique safe filenames")
    sources = [(root / entry.path).resolve() for entry in entries]
    if len(set(sources)) != len(sources):
        raise ValueError("Manifest contains duplicate source paths")
    for source, entry in zip(sources, entries, strict=True):
        suffix = ".md" if entry.format == "markdown" else "." + entry.format
        if not source.is_relative_to(root / "data/documents") or source.suffix.lower() != suffix:
            raise ValueError("Sources must have the declared extension and be under data/documents")
    # Only create a fresh output directory. Prevent replacing raw or prior artifacts.
    if output == manifest or output.is_relative_to(root / "data/documents"):
        raise ValueError("Output cannot be inside the raw corpus")
    output.mkdir(parents=True, exist_ok=False)
    report: dict[str, Any] = {
        "manifest_documents": len(entries),
        "documents": 0,
        "blocks": 0,
        "extracted_characters": 0,
        "semantic_blocks": 0,
        "semantic_characters": 0,
        "per_format": {},
        "block_types": {},
        "empty_documents": [],
        "warnings": {},
        "errors": [],
    }
    formats: Counter[str] = Counter()
    types: Counter[str] = Counter()
    for entry, source in zip(entries, sources, strict=True):
        try:
            document = extract_document(source, entry.model_dump())
            (output / f"{entry.document_id}.json").write_text(
                document.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
        except Exception as exc:
            # Isolate parser failures so every manifest entry is attempted and reported.
            report["errors"].append(
                {"document_id": entry.document_id, "error": f"{type(exc).__name__}: {exc}"}
            )
            continue
        report["documents"] += 1
        report["blocks"] += len(document.blocks)
        report["extracted_characters"] += sum(len(block.text) for block in document.blocks)
        report["semantic_blocks"] += len(document.semantic_blocks)
        report["semantic_characters"] += sum(len(block.text) for block in document.semantic_blocks)
        formats[document.format] += 1
        types.update(block.type for block in document.blocks)
        if not document.semantic_blocks:
            report["empty_documents"].append(entry.document_id)
        if document.warnings:
            report["warnings"][entry.document_id] = document.warnings
    report["per_format"] = dict(formats)
    report["block_types"] = dict(types)
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report
