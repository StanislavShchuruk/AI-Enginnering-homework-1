"""HTML traversal shared with markdown-it's parsed Markdown rendering."""

import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag
from markdown_it import MarkdownIt
from markdown_it.token import Token

from .common import normalize, table_block
from .models import ContentBlock, SourceLocation


def extract_html(text: str) -> list[ContentBlock]:
    soup = BeautifulSoup(text, "html.parser")
    for tag in soup(["script", "style", "head", "template"]):
        tag.decompose()
    blocks: list[ContentBlock] = []
    index = 0

    def walk(node: Tag, depth: int = 0, ordered: bool = False) -> None:
        nonlocal index
        index += 1
        loc = SourceLocation(element=index, line=node.get("data-source-line"))
        name = node.name or ""
        if name == "br":
            return
        if name in {"header", "footer"}:
            # Only document-level landmarks are furniture. An article/section header
            # can contain a legitimate title and must stay in the semantic stream.
            if not node.find_parent(["article", "section", "main"]):
                if value := normalize(node.get_text("\n")):
                    blocks.append(ContentBlock(type=name, text=value, location=loc))
                return
        if name == "table":
            # Expanded grid makes row/column spans explicit, retaining blank cells.
            grid: list[list[str]] = []
            spans: dict[int, tuple[int, str]] = {}
            for tr in node.find_all("tr"):
                row: list[str] = []
                col = 0
                pending: dict[int, tuple[int, str]] = {}

                def consume_spans(
                    row: list[str] = row,
                    pending: dict[int, tuple[int, str]] = pending,
                ) -> None:
                    nonlocal col
                    while col in spans:
                        remaining, value = spans[col]
                        row.append(value)
                        del spans[col]
                        if remaining > 1:
                            pending[col] = (remaining - 1, value)
                        col += 1

                for cell in tr.find_all(["td", "th"], recursive=False):
                    consume_spans()
                    value = normalize(cell.get_text())
                    for _ in range(max(1, int(cell.get("colspan", 1)))):
                        row.append(value)
                        if int(cell.get("rowspan", 1)) > 1:
                            pending[col] = (int(cell["rowspan"]) - 1, value)
                        col += 1
                consume_spans()
                spans.update(pending)
                grid.append(row)
            if grid and any(any(row) for row in grid):
                blocks.append(table_block(grid, location=loc))
            return
        if name in {"ol", "ul"}:
            number = int(node.get("start", 1))
            for child in node.children:
                if isinstance(child, Tag):
                    if child.name == "li" and name == "ol":
                        number = int(child.get("value", number))
                        if not child.has_attr("data-marker"):
                            child["data-marker"] = str(number) + "."
                        number += 1
                    walk(child, depth + 1, name == "ol")
            return
        if name == "li":
            # Flush text before descending into nested lists to retain source order.
            pieces: list[str] = []

            def flush() -> None:
                value = normalize("".join(pieces))
                pieces.clear()
                if value:
                    blocks.append(
                        ContentBlock(
                            type="list_item",
                            text=value,
                            ordered=ordered,
                            list_level=max(0, depth - 1),
                            marker=node.get("data-marker", "•"),
                            location=loc,
                        )
                    )

            for child in node.children:
                if isinstance(child, Tag) and child.name in {"ol", "ul", "table"}:
                    flush()
                    walk(child, depth, ordered)
                else:
                    pieces.append(child.get_text() if isinstance(child, Tag) else str(child))
            flush()
            return
        if name in {"p", "pre", "blockquote"} or name in {f"h{i}" for i in range(1, 7)}:
            value = normalize(node.get_text())
            if value:
                heading = name.startswith("h")
                blocks.append(
                    ContentBlock(
                        type="heading" if heading else "paragraph",
                        text=value,
                        heading_level=int(name[1]) if heading else None,
                        location=loc,
                    )
                )
            return
        for child in node.children:
            if isinstance(child, Tag):
                walk(child, depth, ordered)
            elif isinstance(child, NavigableString) and normalize(str(child)):
                blocks.append(
                    ContentBlock(type="paragraph", text=normalize(str(child)), location=loc)
                )

    # Preserve explicit hard breaks without introducing spaces around inline markup.
    for br in soup.find_all("br"):
        br.replace_with("\n")
    walk(soup.body or soup)
    return blocks


def extract_web(
    path: Path, markdown: bool = False, warnings: list[str] | None = None
) -> list[ContentBlock]:
    text = path.read_text(encoding="utf-8-sig")
    if markdown:
        parser = MarkdownIt("commonmark").enable("table")
        tokens = parser.parse(text)
        # Some client Markdown has pipe rows without the GFM delimiter row.
        # Recognize only an entire pipe-delimited paragraph with consistent widths.
        for index in range(len(tokens) - 2):
            opening, inline, closing = tokens[index : index + 3]
            if opening.type != "paragraph_open" or inline.type != "inline":
                continue
            lines = inline.content.splitlines()
            if len(lines) < 2 or not all(
                line.startswith("|") and line.endswith("|") for line in lines
            ):
                continue
            rows = [re.split(r"(?<!\\)\|", line[1:-1]) for line in lines]
            if len({len(row) for row in rows}) != 1:
                continue
            token = Token("html_block", "", 0)
            line_number = opening.map[0] + 1 if opening.map else 1
            token.content = (
                f'<table data-source-line="{line_number}">'
                + "".join(
                    "<tr>"
                    + "".join("<td>" + parser.renderInline(cell.strip()) + "</td>" for cell in row)
                    + "</tr>"
                    for row in rows
                )
                + "</table>"
            )
            tokens[index] = token
            inline.content, inline.children = "", []
            closing.type, closing.tag, closing.nesting = "html_block", "", 0
            if warnings is not None:
                warnings.append(
                    f"Markdown pipe table at line {line_number} lacks a delimiter row; "
                    "extracted using consistent pipe columns."
                )
        for token in tokens:
            if token.type == "list_item_open":
                # markdown-it retains the authored bullet or ordered delimiter.
                token.attrSet("data-marker", (token.info + token.markup).strip())
            if token.map and token.nesting == 1:
                token.attrSet("data-source-line", str(token.map[0] + 1))
        text = parser.renderer.render(tokens, parser.options, {})
    return extract_html(text)
