"""Shared conservative normalization and section tracking."""

import re

from .models import ContentBlock

LIST_PREFIX = re.compile(r"^(\d+[.)]|[-•*+])\s+")


def split_list_prefix(text: str) -> tuple[str, str | None]:
    """Split only an explicit leading list marker, leaving business text intact."""
    match = LIST_PREFIX.match(text)
    return (text[match.end() :], match[1]) if match else (text, None)


def normalize(text: str) -> str:
    """Keep explicit line breaks and Unicode; collapse horizontal whitespace only."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00ad", "")
    lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def assign_sections(blocks: list[ContentBlock]) -> None:
    headings: list[tuple[int, str]] = []
    for block in blocks:
        if not block.is_semantic:
            block.section_path = []
            continue
        if block.type == "heading":
            level = block.heading_level or 1
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, block.text))
        block.section_path = [text for _, text in headings]


def table_block(rows: list[list[str]], **kwargs: object) -> ContentBlock:
    cleaned = [[normalize(cell or "") for cell in row] for row in rows]
    return ContentBlock(
        type="table", text="\n".join("\t".join(row) for row in cleaned), rows=cleaned, **kwargs
    )
