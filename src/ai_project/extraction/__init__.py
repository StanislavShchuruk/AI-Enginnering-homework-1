"""Offline document extraction entry point."""

from pathlib import Path
from typing import Any

from .common import assign_sections
from .models import ExtractedDocument
from .office import extract_docx
from .pdf import extract_pdf
from .web import extract_web


def extract_document(path: Path, metadata: dict[str, Any]) -> ExtractedDocument:
    fmt = metadata["format"]
    warnings: list[str] = []
    if fmt == "pdf":
        blocks, warnings = extract_pdf(path)
    elif fmt == "docx":
        blocks = extract_docx(path)
    elif fmt in {"html", "markdown"}:
        blocks = extract_web(path, markdown=fmt == "markdown", warnings=warnings)
    else:
        raise ValueError(f"Unsupported format: {fmt}")
    assign_sections(blocks)
    if not any(b.is_semantic for b in blocks):
        warnings.append("Document has no extractable body content.")
    if any("\ufffd" in block.text for block in blocks):
        warnings.append("Replacement Unicode character found; inspect source encoding/font.")
    return ExtractedDocument(
        document_id=metadata["document_id"],
        source_path=metadata["path"],
        title=metadata["title"],
        format=fmt,
        metadata=metadata,
        blocks=blocks,
        warnings=warnings,
    )
