"""Geometry-based PDF extraction. Page furniture is labeled and never discarded."""

from collections import Counter
from pathlib import Path

import pymupdf

from .common import normalize, split_list_prefix, table_block
from .models import ContentBlock, SourceLocation


def furniture_kind(raw: dict, height: float, body_size: float) -> str | None:
    """A margin position is only a candidate, never sufficient evidence by itself."""
    spans = [span for line in raw.get("lines", []) for span in line["spans"]]
    if not spans or max(span["size"] for span in spans) > body_size * 0.85:
        return None
    if raw["bbox"][3] < height * 0.045:
        return "header"
    if raw["bbox"][1] > height * 0.95:
        return "footer"
    return None


def block_text(raw: dict) -> str:
    return normalize(
        " ".join("".join(s["text"] for s in line["spans"]) for line in raw.get("lines", []))
    )


def extract_pdf(path: Path) -> tuple[list[ContentBlock], list[str]]:
    blocks: list[ContentBlock] = []
    warnings = [
        "PDF headings and reading order are inferred from font size and geometry; "
        "only small margin text with recurrence or a page-number cue is labeled "
        "as non-semantic header/footer; ambiguous margin content stays semantic."
    ]
    with pymupdf.open(path) as doc:
        if doc.needs_pass:
            raise ValueError("Encrypted PDF requires a password")
        pages = [page.get_text("dict", sort=True)["blocks"] for page in doc]
        sizes: Counter[float] = Counter()
        body_sizes: Counter[float] = Counter()
        for page, page_blocks in zip(doc, pages, strict=True):
            for block in page_blocks:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        sizes[round(span["size"], 1)] += len(span["text"])
                        if (
                            block["bbox"][1] >= page.rect.height * 0.045
                            and block["bbox"][3] <= page.rect.height * 0.95
                        ):
                            body_sizes[round(span["size"], 1)] += len(span["text"])
        body_size = (body_sizes or sizes).most_common(1)[0][0] if sizes else 11
        heading_sizes = sorted((size for size in sizes if size > body_size + 0.8), reverse=True)
        occurrences: Counter[tuple[str, str, int]] = Counter()
        for page, raw_blocks in zip(doc, pages, strict=True):
            # Count pages, not duplicate text occurrences on one page. Matching
            # margin position and smaller typography provide additional evidence.
            occurrences.update(
                {
                    (kind, block_text(raw), round(raw["bbox"][1] / page.rect.height * 100))
                    for raw in raw_blocks
                    if (kind := furniture_kind(raw, page.rect.height, body_size))
                }
            )
        for page_index, page in enumerate(doc):
            page_number = page_index + 1
            if page_index:
                blocks.append(
                    ContentBlock(
                        type="page_break", text="", location=SourceLocation(page=page_number)
                    )
                )
            # Horizontal-rule tables (including this corpus) need inferred vertical edges.
            drawings = page.get_drawings()
            horizontal = [
                item
                for drawing in drawings
                for item in drawing["items"]
                if item[0] == "l" and abs(item[1].y - item[2].y) < 1
            ]
            tables = page.find_tables().tables
            if not tables and len(horizontal) >= 2:
                # Infer column boundaries from the header's separate text runs, rather
                # than every body word (which can split business facts across cells).
                first_rule = min(item[1].y for item in horizontal)
                left = min(min(item[1].x, item[2].x) for item in horizontal)
                right = max(max(item[1].x, item[2].x) for item in horizontal)
                lines = [
                    line
                    for raw in pages[page_index]
                    for line in raw.get("lines", [])
                    if first_rule - 35 < line["bbox"][1] < first_rule
                    and line["bbox"][3] <= first_rule + 1
                ]
                if len(lines) >= 2:
                    top_y = max(line["bbox"][1] for line in lines)
                    header = sorted(
                        (line for line in lines if abs(line["bbox"][1] - top_y) < 2),
                        key=lambda line: line["bbox"][0],
                    )
                    padding = header[0]["bbox"][0] - left
                    edges = [left, *[line["bbox"][0] - padding for line in header[1:]], right]
                    if len(edges) >= 3:
                        tables = page.find_tables(
                            vertical_strategy="explicit",
                            vertical_lines=edges,
                            horizontal_lines=[top_y - 5],
                        ).tables
            items: list[tuple[float, float, ContentBlock]] = []
            for table in tables:
                rows = table.extract()
                if rows and any(any(row) for row in rows):
                    items.append(
                        (
                            table.bbox[1],
                            table.bbox[0],
                            table_block(
                                rows, location=SourceLocation(page=page_number, bbox=table.bbox)
                            ),
                        )
                    )
            for raw in pages[page_index]:
                if "lines" not in raw:
                    continue
                bbox = raw["bbox"]
                # Exclude only text actually contained in an extracted table rectangle.
                remaining = []
                for line in raw["lines"]:
                    x0, y0, x1, y1 = line["bbox"]
                    if not any(
                        t.bbox[0] - 1 <= x0
                        and t.bbox[2] + 1 >= x1
                        and t.bbox[1] - 1 <= y0
                        and t.bbox[3] + 1 >= y1
                        for t in tables
                    ):
                        remaining.append(line)
                if not remaining:
                    continue
                text = normalize(
                    " ".join("".join(s["text"] for s in line["spans"]) for line in remaining)
                )
                if not text:
                    continue
                size = max(s["size"] for line in remaining for s in line["spans"])
                loc = SourceLocation(page=page_number, bbox=bbox)
                item_text, marker = split_list_prefix(text)
                kind = furniture_kind(raw, page.rect.height, body_size)
                key = (kind, text, round(bbox[1] / page.rect.height * 100))
                # The corpus uses a label and a separate page numeral in one block.
                has_page_number = any(
                    normalize("".join(s["text"] for s in line["spans"])) == str(page_number)
                    for line in remaining
                )
                if kind and (occurrences[key] >= 2 or has_page_number):
                    block = ContentBlock(type=kind, text=text, location=loc)
                elif size > body_size + 0.8:
                    level = (
                        min(range(len(heading_sizes)), key=lambda i: abs(heading_sizes[i] - size))
                        + 1
                    )
                    block = ContentBlock(
                        type="heading", text=text, heading_level=level, location=loc
                    )
                elif marker:
                    block = ContentBlock(
                        type="list_item",
                        text=item_text,
                        ordered=marker[0].isdigit(),
                        marker=marker,
                        list_level=0,
                        location=loc,
                    )
                else:
                    block = ContentBlock(type="paragraph", text=text, location=loc)
                items.append((bbox[1], bbox[0], block))
            page_blocks = [block for _, _, block in sorted(items, key=lambda item: item[:2])]
            blocks.extend(page_blocks)
            if not page_blocks:
                warnings.append(
                    f"Page {page_number} has no extractable text (OCR is not performed)."
                )
    return blocks, warnings
