"""Extraction -> sanitization -> exact deduplication -> local chunking."""

import json
import re
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from ai_project.chunking import ChunkingConfig, write_chunks
from ai_project.deduplication import content_hash, deduplicate, source_hash, stable_json
from ai_project.extraction import extract_document
from ai_project.extraction.corpus import ManifestSource
from ai_project.extraction.models import ExtractedDocument
from ai_project.sanitization import LIMITATIONS, SanitizationConfig, sanitize_document


def load_config(path: Path | None) -> SanitizationConfig:
    if path is None:
        return SanitizationConfig()
    path = path.resolve()
    if path.suffix.lower() != ".json" or path.name.startswith(".env"):
        raise ValueError("Configuration must be a JSON file")
    return SanitizationConfig.model_validate_json(path.read_text(encoding="utf-8"))


def process_corpus(
    root: Path,
    manifest: Path,
    output: Path,
    *,
    extracted: Path | None = None,
    config: SanitizationConfig | None = None,
    chunking: ChunkingConfig | None = None,
) -> dict[str, Any]:
    """Write only sanitized documents. Existing raw/extracted artifacts are never written.

    If extracted is absent, extraction occurs in memory. When present, load the
    manifest's document IDs from that directory and verify metadata consistency.
    A document that fails processing is withheld; safe error codes go to the report.
    """
    root, manifest, output = root.resolve(), manifest.resolve(), output.resolve()
    extracted = extracted.resolve() if extracted else None
    config = config or SanitizationConfig()
    if manifest.suffix.lower() != ".json" or manifest.name.startswith(".env"):
        raise ValueError("Manifest must be a JSON file")
    entries = TypeAdapter(list[ManifestSource]).validate_json(manifest.read_text(encoding="utf-8"))
    entries.sort(key=lambda entry: entry.document_id)
    ids = [entry.document_id for entry in entries]
    if len({identifier.casefold() for identifier in ids}) != len(ids) or any(
        not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", identifier) for identifier in ids
    ):
        raise ValueError("Document IDs must be unique safe identifiers")
    for entry in entries:
        source = (root / entry.path).resolve()
        suffix = ".md" if entry.format == "markdown" else "." + entry.format
        if not source.is_relative_to(root / "data/documents") or source.suffix.lower() != suffix:
            raise ValueError("Sources must match declared formats under data/documents")
        metadata = entry.model_dump()
        if any(
            not isinstance(metadata.get(key), str) or not metadata[key].strip()
            for key in ("access_group", "status", "version", "effective_date")
        ):
            raise ValueError("Manifest requires explicit access and lifecycle metadata")
    if output.is_relative_to(root / "data/documents") or (
        extracted and (output.is_relative_to(extracted) or extracted.is_relative_to(output))
    ):
        raise ValueError("Sanitized output must be separate from raw and extracted inputs")
    if extracted and not extracted.is_dir():
        raise ValueError("Extracted input directory does not exist")
    output.mkdir(parents=True, exist_ok=False)
    documents: dict[str, dict[str, Any]] = {}
    records = []
    counts: Counter[str] = Counter()
    warnings: dict[str, list[str]] = {}
    errors = []
    for entry in entries:
        stage = "source_read"
        try:
            source = (root / entry.path).resolve()
            original_bytes = source.read_bytes()
            stage = "extracted_load" if extracted else "extraction"
            if extracted:
                input_path = (extracted / f"{entry.document_id}.json").resolve()
                if not input_path.is_relative_to(extracted) or input_path.suffix != ".json":
                    raise ValueError("Invalid extracted input path")
                payload = json.loads(input_path.read_text(encoding="utf-8"))
                if any(
                    key in payload
                    for key in (
                        "sanitization_version",
                        "redaction_counts",
                        "source_hash",
                        "content_hash",
                    )
                ):
                    raise ValueError("Expected original, unsanitized extraction")
                document = ExtractedDocument.model_validate(payload)
                if (
                    document.document_id,
                    document.title,
                    document.format,
                    document.source_path,
                    document.metadata,
                ) != (entry.document_id, entry.title, entry.format, entry.path, entry.model_dump()):
                    raise ValueError("Extracted metadata disagrees with manifest")
            else:
                # Third-party parser diagnostics must not leak source content.
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    document = extract_document(source, entry.model_dump())
            if not document.semantic_blocks:
                raise ValueError("Empty semantic content")
            stage = "hashing"
            hashes = {
                "source_hash": source_hash(original_bytes),
                "content_hash": content_hash(document),
            }
            stage = "sanitization"
            sanitized = sanitize_document(document, config)
            payload = sanitized.model_dump()
            payload.update(hashes)
            documents[entry.document_id] = payload
            records.append(
                {"document_id": entry.document_id, "metadata": document.metadata, **hashes}
            )
            counts.update(sanitized.redaction_counts)
            warnings[entry.document_id] = sanitized.warnings
        except Exception:
            # Exception text, source paths and validation inputs may contain PII.
            # Never include them in logs, report errors, or CLI output.
            errors.append(
                {
                    "document_id": entry.document_id,
                    "stage": stage,
                    "code": "document_withheld_processing_failed",
                }
            )
    duplicates = deduplicate(records)
    excluded = {
        item["document_id"]: item["kept_document_id"] for item in duplicates["excluded_documents"]
    }
    (output / "documents").mkdir()
    for identifier, payload in sorted(documents.items()):
        payload["excluded_as_duplicate_of"] = excluded.get(identifier)
        directory = output / ("duplicates" if identifier in excluded else "documents")
        directory.mkdir(exist_ok=True)
        (directory / f"{identifier}.json").write_text(stable_json(payload), encoding="utf-8")
    chunk_manifest = write_chunks(list(documents.values()), output, chunking or ChunkingConfig())
    report = {
        "processing_version": "1.0",
        "manifest_documents": len(entries),
        "sanitized_documents": len(documents),
        "included_documents": len(documents) - len(excluded),
        "excluded_duplicate_documents": len(excluded),
        "withheld_documents": len(errors),
        "redaction_counts": dict(sorted(counts.items())),
        "warnings": warnings,
        "limitations": LIMITATIONS,
        "errors": errors,
        "chunking": chunk_manifest,
        **duplicates,
    }
    (output / "report.json").write_text(stable_json(report), encoding="utf-8")
    return report
