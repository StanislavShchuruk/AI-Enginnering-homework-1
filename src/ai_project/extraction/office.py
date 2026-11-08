"""DOCX extraction in XML body order, including interleaved tables."""

import re
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from .common import normalize, split_list_prefix, table_block
from .models import ContentBlock, SourceLocation


def format_number(number: int, fmt: str) -> str:
    if fmt in {"lowerLetter", "upperLetter"} and number > 0:
        letters = ""
        while number:
            number, digit = divmod(number - 1, 26)
            letters = chr(65 + digit) + letters
        return letters.lower() if fmt == "lowerLetter" else letters
    if fmt in {"lowerRoman", "upperRoman"} and 0 < number < 4000:
        roman = ""
        for value, symbol in [
            (1000, "M"),
            (900, "CM"),
            (500, "D"),
            (400, "CD"),
            (100, "C"),
            (90, "XC"),
            (50, "L"),
            (40, "XL"),
            (10, "X"),
            (9, "IX"),
            (5, "V"),
            (4, "IV"),
            (1, "I"),
        ]:
            count, number = divmod(number, value)
            roman += symbol * count
        return roman.lower() if fmt == "lowerRoman" else roman
    return str(number)


def extract_docx(path: Path) -> list[ContentBlock]:
    doc = Document(path)
    blocks: list[ContentBlock] = []
    counters: dict[tuple[int, int], int] = {}
    # Header/footer parts are retained once per section, not guessed into page order.
    for section_index, section in enumerate(doc.sections):
        for part_name in ("header", "footer"):
            part = getattr(section, part_name)
            for index, paragraph in enumerate(part.paragraphs):
                if text := normalize(paragraph.text):
                    blocks.append(
                        ContentBlock(
                            type=part_name,
                            text=text,
                            location=SourceLocation(
                                element=index, part=f"section{section_index}/{part_name}"
                            ),
                        )
                    )
    for index, element in enumerate(doc.element.body):
        loc = SourceLocation(element=index, part="body")
        if element.tag == qn("w:tbl"):
            rows = [[cell.text for cell in row.cells] for row in Table(element, doc).rows]
            if rows and any(any(row) for row in rows):
                blocks.append(table_block(rows, location=loc))
        elif element.tag == qn("w:p"):
            p = Paragraph(element, doc)
            text = normalize(p.text)
            if not text:
                continue
            style = p.style.name if p.style else ""
            heading = re.fullmatch(r"Heading (\d+)", style)
            if style == "Title" or heading:
                blocks.append(
                    ContentBlock(
                        type="heading",
                        text=text,
                        heading_level=1 if style == "Title" else int(heading[1]) + 1,
                        location=loc,
                    )
                )
                continue
            num = p._p.pPr.numPr if p._p.pPr is not None else None
            if num is None and p.style is not None and p.style.element.pPr is not None:
                num = p.style.element.pPr.numPr
            ordered = "Number" in style
            level = 0
            marker = None
            if num is not None and num.numId is not None:
                level = int(num.ilvl.val) if num.ilvl is not None else 0
                definitions = doc.part.numbering_part.element
                nums = definitions.xpath(f'./w:num[@w:numId="{num.numId.val}"]')
                if nums:
                    abstract_id = nums[0].abstractNumId.val
                    levels = definitions.xpath(
                        f'./w:abstractNum[@w:abstractNumId="{abstract_id}"]'
                        f'/w:lvl[@w:ilvl="{level}"]'
                    )
                    overrides = nums[0].xpath(f'./w:lvlOverride[@w:ilvl="{level}"]')
                    if overrides and overrides[0].find(qn("w:lvl")) is not None:
                        levels = [overrides[0].find(qn("w:lvl"))]
                    if levels:
                        definition = levels[0]
                        fmt_node = definition.find(qn("w:numFmt"))
                        fmt = fmt_node.get(qn("w:val")) if fmt_node is not None else "decimal"
                        ordered = fmt != "bullet"
                        start_node = definition.find(qn("w:start"))
                        start = int(start_node.get(qn("w:val"))) if start_node is not None else 1
                        if overrides:
                            start_override = overrides[0].find(qn("w:startOverride"))
                            if start_override is not None:
                                start = int(start_override.get(qn("w:val")))
                        key = (int(num.numId.val), level)
                        counters[key] = counters.get(key, start - 1) + 1
                        for deeper in list(counters):
                            if deeper[0] == key[0] and deeper[1] > level:
                                del counters[deeper]
                        template = definition.find(qn("w:lvlText"))
                        marker = template.get(qn("w:val")) if template is not None else "%1."
                        if ordered:
                            for depth in range(level + 1):
                                parent = definitions.xpath(
                                    f'./w:abstractNum[@w:abstractNumId="{abstract_id}"]'
                                    f'/w:lvl[@w:ilvl="{depth}"]/w:numFmt'
                                )
                                parent_fmt = (
                                    fmt
                                    if depth == level or not parent
                                    else parent[0].get(qn("w:val"))
                                )
                                value = counters.get((key[0], depth), 1)
                                marker = marker.replace(
                                    f"%{depth + 1}", format_number(value, parent_fmt)
                                )
                        elif not marker or any(0xE000 <= ord(c) <= 0xF8FF for c in marker):
                            marker = "•"  # Word Symbol-font bullets use private-use glyphs.
            item_text, literal_marker = split_list_prefix(text)
            if num is not None or style.startswith("List") or literal_marker:
                if literal_marker:
                    marker = literal_marker
                    ordered = literal_marker[0].isdigit()
                elif marker is None:
                    marker = "•" if not ordered else "1."
                blocks.append(
                    ContentBlock(
                        type="list_item",
                        text=item_text,
                        ordered=ordered,
                        marker=marker,
                        list_level=level,
                        location=loc,
                    )
                )
            else:
                blocks.append(ContentBlock(type="paragraph", text=text, location=loc))
    return blocks
