"""Offline structure fixtures and regression checks against all authored source content."""

import hashlib
import json
import re
from pathlib import Path
from zipfile import BadZipFile

import pymupdf
import pytest
from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from pydantic import ValidationError

from ai_project.cli import main
from ai_project.extraction import extract_document
from ai_project.extraction.corpus import extract_corpus
from ai_project.extraction.models import ContentBlock, ExtractedDocument

ROOT = Path(__file__).resolve().parents[1]


def metadata(path: Path, fmt: str) -> dict:
    return {"document_id": "T01", "title": "HR guide", "path": str(path), "format": fmt}


@pytest.mark.parametrize("fmt", ["html", "markdown", "docx", "pdf"])
def test_formats_structure_order_unicode(tmp_path: Path, fmt: str) -> None:
    path = tmp_path / ("test.md" if fmt == "markdown" else f"test.{fmt}")
    if fmt == "html":
        path.write_text(
            "<h1>HR guide</h1><h2>Terms</h2><p>Café — Україна<br>Next line</p>"
            '<ol start="3"><li>First</li></ol><ul><li>Second</li></ul>'
            "<table><tr><th>Key</th><th>Value</th></tr>"
            "<tr><td>Leave</td><td>25 days</td></tr></table>"
            "<h2>End</h2><p>Last</p>",
            encoding="utf-8",
        )
    elif fmt == "markdown":
        path.write_text(
            "# HR guide\n\n## Terms\n\nCafé — Україна  \nNext line\n\n"
            "3. First\n\n- Second\n\n| Key | Value |\n| --- | --- |\n"
            "| Leave | 25 days |\n\n## End\n\nLast\n",
            encoding="utf-8",
        )
    elif fmt == "docx":
        doc = Document()
        doc.add_paragraph("HR guide", "Title")
        doc.add_heading("Terms", level=1)
        doc.add_paragraph("Café — Україна\nNext line")
        doc.add_paragraph("First", "List Number")
        doc.add_paragraph("Second", "List Bullet")
        table = doc.add_table(rows=2, cols=2)
        for row, values in zip(table.rows, [["Key", "Value"], ["Leave", "25 days"]], strict=True):
            for cell, value in zip(row.cells, values, strict=True):
                cell.text = value
        doc.add_heading("End", level=1)
        doc.add_paragraph("Last")
        doc.save(path)
    else:
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Table

        styles = getSampleStyleSheet()
        SimpleDocTemplate(str(path)).build(
            [
                Paragraph("HR guide", styles["Title"]),
                Paragraph("Terms", styles["Heading2"]),
                Paragraph("Café", styles["BodyText"]),
                Paragraph("1. First", styles["BodyText"]),
                Paragraph("- Second", styles["BodyText"]),
                Table(
                    [["Key", "Value"], ["Leave", "25 days"]],
                    style=[("GRID", (0, 0), (-1, -1), 1, "black")],
                ),
                Paragraph("End", styles["Heading2"]),
                Paragraph("Last", styles["BodyText"]),
            ]
        )
    document = extract_document(path, metadata(path, fmt))
    blocks = document.blocks
    assert [b.type for b in blocks] == [
        "heading",
        "heading",
        "paragraph",
        "list_item",
        "list_item",
        "table",
        "heading",
        "paragraph",
    ]
    assert "Café" in blocks[2].text
    if fmt != "pdf":
        assert "Україна" in blocks[2].text
        assert "\nNext line" in blocks[2].text
    assert blocks[3].ordered is True
    assert blocks[4].ordered is False
    assert blocks[3].text == "First"
    assert blocks[4].text == "Second"
    assert blocks[3].marker == ("3." if fmt in {"html", "markdown"} else "1.")
    assert blocks[4].marker in {"•", "-"}
    assert blocks[3].list_level == blocks[4].list_level == 0
    assert f"{blocks[3].marker} {blocks[3].text}".count(blocks[3].marker) == 1
    assert blocks[5].rows == [["Key", "Value"], ["Leave", "25 days"]]
    assert blocks[3].section_path == ["HR guide", "Terms"]
    assert blocks[-1].section_path == ["HR guide", "End"]
    if fmt == "markdown":
        assert blocks[1].location.line == 3


def test_pdf_pages_and_repeated_legitimate_content(tmp_path: Path) -> None:
    path = tmp_path / "pages.pdf"
    with pymupdf.open() as doc:
        for _ in range(2):
            page = doc.new_page()
            page.insert_text((50, 20), "Repeated header", fontsize=8)
            page.insert_text((50, 100), "Repeated header")
            page.insert_text((50, 825), "Footer", fontsize=8)
        doc.save(path)
    blocks = extract_document(path, metadata(path, "pdf")).blocks
    assert sum(b.text == "Repeated header" for b in blocks) == 4
    assert [b.location.page for b in blocks if b.type == "page_break"] == [2]
    assert sum(b.type == "paragraph" for b in blocks) == 2
    assert all(b.location.bbox for b in blocks if b.type != "page_break")
    assert all(
        not b.is_semantic and not b.section_path
        for b in blocks
        if b.type in {"header", "footer", "page_break"}
    )


def test_pdf_legitimate_margin_content_stays_semantic(tmp_path: Path) -> None:
    path = tmp_path / "margins.pdf"
    with pymupdf.open() as doc:
        for page_index in range(2):
            page = doc.new_page()
            # Repeated body-sized text at the edge is not sufficient furniture evidence.
            page.insert_text((50, 20), "Leave entitlement", fontsize=16)
            page.insert_text((50, 100), "Employees receive 25 days of annual leave.")
            page.insert_text((50, 803), "Annual leave cannot be exchanged for cash.")
            # Even small, one-off margin text could be a meaningful footnote.
            page.insert_text(
                (50, 825), f"Entitlement applies to contract {chr(65 + page_index)}.", fontsize=8
            )
        doc.save(path)
    document = extract_document(path, metadata(path, "pdf"))
    assert len(document.semantic_blocks) == 8
    assert not any(b.type in {"header", "footer"} for b in document.blocks)
    assert all("Leave entitlement" in b.section_path for b in document.semantic_blocks)


@pytest.mark.parametrize("fmt", ["html", "markdown", "docx"])
def test_furniture_excluded_from_semantic_stream(tmp_path: Path, fmt: str) -> None:
    path = tmp_path / ("furniture.md" if fmt == "markdown" else f"furniture.{fmt}")
    if fmt == "docx":
        doc = Document()
        doc.sections[0].header.paragraphs[0].text = "Company name"
        doc.sections[0].footer.paragraphs[0].text = "Confidential footer"
        doc.add_paragraph("HR guide", "Title")
        doc.add_heading("Terms", level=1)
        doc.add_paragraph("First paragraph")
        doc.add_paragraph("Last paragraph")
        doc.save(path)
    else:
        path.write_text(
            "<header><h1>Company name</h1></header>\n\n"
            "<h1>HR guide</h1><h2>Terms</h2><p>First paragraph</p>"
            "<footer>Confidential footer</footer><p>Last paragraph</p>",
            encoding="utf-8",
        )
    document = extract_document(path, metadata(path, fmt))
    assert [b.text for b in document.semantic_blocks] == [
        "HR guide",
        "Terms",
        "First paragraph",
        "Last paragraph",
    ]
    assert document.semantic_blocks[-1].section_path == ["HR guide", "Terms"]
    furniture = [b for b in document.blocks if b.type in {"header", "footer"}]
    assert {b.text for b in furniture} == {"Company name", "Confidential footer"}
    assert all(not b.is_semantic and b.section_path == [] for b in furniture)
    assert ExtractedDocument.model_validate_json(document.model_dump_json()) == document


def test_article_header_is_meaningful_content(tmp_path: Path) -> None:
    path = tmp_path / "article.html"
    path.write_text(
        "<article><header><h1>HR guide</h1></header><p>Body</p></article>", encoding="utf-8"
    )
    document = extract_document(path, metadata(path, "html"))
    assert [b.type for b in document.semantic_blocks] == ["heading", "paragraph"]
    assert document.semantic_blocks[-1].section_path == ["HR guide"]


def test_docx_literal_and_native_markers(tmp_path: Path) -> None:
    path = tmp_path / "lists.docx"
    doc = Document()
    doc.add_paragraph("3) Literal number")
    doc.add_paragraph("• Literal bullet")
    doc.add_paragraph("Native first", "List Number")
    doc.add_paragraph("Native second", "List Number")
    doc.add_paragraph("Native bullet", "List Bullet")
    doc.save(path)
    items = extract_document(path, metadata(path, "docx")).semantic_blocks
    assert [b.text for b in items] == [
        "Literal number",
        "Literal bullet",
        "Native first",
        "Native second",
        "Native bullet",
    ]
    assert [b.marker for b in items] == ["3)", "•", "1.", "2.", "•"]
    assert [b.ordered for b in items] == [True, False, True, True, False]


def test_markdown_nested_markers_and_numbering(tmp_path: Path) -> None:
    path = tmp_path / "lists.md"
    path.write_text("3) Parent\n   + Child\n   + Other\n4) Next\n", encoding="utf-8")
    items = extract_document(path, metadata(path, "markdown")).semantic_blocks
    assert [b.text for b in items] == ["Parent", "Child", "Other", "Next"]
    assert [b.marker for b in items] == ["3)", "+", "+", "4)"]
    assert [b.list_level for b in items] == [0, 1, 1, 0]


def test_docx_nested_numbering_and_restart(tmp_path: Path) -> None:
    path = tmp_path / "numbering.docx"
    doc = Document()
    definitions = doc.part.numbering_part.element
    abstract = OxmlElement("w:abstractNum")
    abstract.set(qn("w:abstractNumId"), "90")
    for depth, template in [(0, "%1."), (1, "%1.%2)")]:
        level = OxmlElement("w:lvl")
        level.set(qn("w:ilvl"), str(depth))
        for tag, value in [("start", "1"), ("numFmt", "decimal"), ("lvlText", template)]:
            child = OxmlElement("w:" + tag)
            child.set(qn("w:val"), value)
            level.append(child)
        abstract.append(level)
    definitions.append(abstract)
    for num_id in (90, 91):
        num = OxmlElement("w:num")
        num.set(qn("w:numId"), str(num_id))
        ref = OxmlElement("w:abstractNumId")
        ref.set(qn("w:val"), "90")
        num.append(ref)
        override = OxmlElement("w:lvlOverride")
        override.set(qn("w:ilvl"), "0")
        start = OxmlElement("w:startOverride")
        start.set(qn("w:val"), "3")
        override.append(start)
        num.append(override)
        definitions.append(num)
    for text, num_id, depth in [
        ("Parent", 90, 0),
        ("Child", 90, 1),
        ("Next", 90, 0),
        ("Reset child", 90, 1),
        ("Restart", 91, 0),
    ]:
        paragraph = doc.add_paragraph(text)
        num = paragraph._p.get_or_add_pPr().get_or_add_numPr()
        num.get_or_add_numId().val = num_id
        num.get_or_add_ilvl().val = depth
    doc.save(path)
    items = extract_document(path, metadata(path, "docx")).semantic_blocks
    assert [b.marker for b in items] == ["3.", "3.1)", "4.", "4.1)", "3."]
    assert [b.list_level for b in items] == [0, 1, 0, 1, 0]
    assert all(b.ordered for b in items)


def test_semantic_flag_is_derived_from_type() -> None:
    footer = ContentBlock(type="footer", text="Trace", is_semantic=True, section_path=["Terms"])
    assert not footer.is_semantic and footer.section_path == []
    assert ContentBlock(type="paragraph", text="Body", is_semantic=False).is_semantic


@pytest.mark.parametrize("fmt", ["html", "markdown", "docx", "pdf"])
def test_empty_documents(tmp_path: Path, fmt: str) -> None:
    path = tmp_path / f"empty.{fmt}"
    if fmt == "docx":
        Document().save(path)
    elif fmt == "pdf":
        with pymupdf.open() as doc:
            doc.new_page()
            doc.save(path)
    else:
        path.write_text("", encoding="utf-8")
    assert any(
        "no extractable body" in w for w in extract_document(path, metadata(path, fmt)).warnings
    )


@pytest.mark.parametrize("fmt", ["pdf", "docx"])
def test_malformed_binary(tmp_path: Path, fmt: str) -> None:
    path = tmp_path / f"broken.{fmt}"
    path.write_bytes(b"not a document")
    with pytest.raises((pymupdf.FileDataError, PackageNotFoundError, BadZipFile)):
        extract_document(path, metadata(path, fmt))


def test_pdf_unicode(tmp_path: Path) -> None:
    path = tmp_path / "unicode.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_htmlbox((50, 100, 500, 200), "<p>Україна — Café</p>")
        doc.save(path)
    result = extract_document(path, metadata(path, "pdf"))
    assert "Україна — Café" in " ".join(b.text for b in result.blocks)


def test_html_table_spans(tmp_path: Path) -> None:
    path = tmp_path / "spans.html"
    path.write_text(
        '<table><tr><td rowspan="2">A</td><td colspan="2">B</td></tr>'
        "<tr><td>C</td><td>D</td></tr></table>",
        encoding="utf-8",
    )
    result = extract_document(path, metadata(path, "html"))
    assert result.blocks[0].rows == [["A", "B", "B"], ["A", "C", "D"]]


def test_tolerant_html_and_nested_lists(tmp_path: Path) -> None:
    path = tmp_path / "t.html"
    path.write_text(
        "<h1>Title</h1><ul><li>Outer<ul><li>Inner</li></ul>After</li></ul><p>Unclosed <b>bold",
        encoding="utf-8",
    )
    blocks = extract_document(path, metadata(path, "html")).blocks
    assert [b.text for b in blocks] == ["Title", "Outer", "Inner", "After", "Unclosed bold"]
    assert blocks[2].list_level == 1


def test_block_validation() -> None:
    for values in [
        {"type": "heading", "text": "Title"},
        {"type": "table", "text": "x"},
        {"type": "list_item", "text": "x"},
        {"type": "paragraph", "text": " "},
    ]:
        with pytest.raises(ValidationError):
            ContentBlock(**values)


def test_actual_corpus_all_content_and_raw_unchanged(tmp_path: Path) -> None:
    manifest = json.loads((ROOT / "data/manifest.json").read_text(encoding="utf-8"))
    before = {
        e["path"]: hashlib.sha256((ROOT / e["path"]).read_bytes()).hexdigest() for e in manifest
    }
    report = extract_corpus(ROOT, ROOT / "data/manifest.json", tmp_path / "extracted")
    assert report["documents"] == 32
    assert report["per_format"] == {"html": 11, "pdf": 10, "docx": 4, "markdown": 7}
    assert not report["errors"] and not report["empty_documents"]
    assert report["block_types"]["table"] == 5
    assert report["block_types"]["list_item"] == 94
    assert report["semantic_blocks"] < report["blocks"]
    assert report["semantic_characters"] < report["extracted_characters"]
    for entry in manifest:
        result = ExtractedDocument.model_validate_json(
            (tmp_path / "extracted" / f"{entry['document_id']}.json").read_text(encoding="utf-8")
        )
        assert result.metadata == entry
        assert result.title in " ".join(b.text for b in result.semantic_blocks)
        for block in result.blocks:
            if block.type == "list_item":
                assert block.marker and block.list_level is not None
                assert not re.match(r"^(\d+[.)]|[-•*+])\s+", block.text)
            if block.type in {"header", "footer", "page_break"}:
                assert not block.is_semantic and block.section_path == []
        assert (
            hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest() == before[entry["path"]]
        )


def test_existing_extracted_corpus_regression() -> None:
    baseline = ROOT / "data/extracted"
    manifest = json.loads((ROOT / "data/manifest.json").read_text(encoding="utf-8"))
    if not all((baseline / (e["document_id"] + ".json")).exists() for e in manifest):
        pytest.skip("Existing extracted corpus is not available in this checkout")
    for entry in manifest:
        previous = ExtractedDocument.model_validate_json(
            (baseline / (entry["document_id"] + ".json")).read_text(encoding="utf-8")
        )
        current = extract_document(ROOT / entry["path"], entry)
        assert len(previous.blocks) == len(current.blocks), entry["document_id"]
        for old, new in zip(previous.blocks, current.blocks, strict=True):
            expected = old.text
            if old.type == "list_item":
                expected = re.sub(r"^(\d+[.)]|[-•*+])\s+", "", expected)
                assert new.ordered == old.ordered and new.list_level == old.list_level
                if old.marker:
                    assert new.marker == old.marker or entry["format"] == "markdown"
            assert new.text == expected, (entry["document_id"], old.text)
            assert new.type == old.type
            assert new.rows == old.rows and new.location == old.location
            if new.is_semantic:
                assert new.section_path == old.section_path


def test_cli_and_errors(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    root = tmp_path / "project"
    (root / "data/documents").mkdir(parents=True)
    manifest = [
        dict(document_id="Bad", title="Broken", path="data/documents/bad.pdf", format="pdf"),
        dict(document_id="Good", title="Good", path="data/documents/good.md", format="markdown"),
    ]
    (root / "data/manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "data/documents/good.md").write_text("# Good\n\nText", encoding="utf-8")
    output = tmp_path / "out"
    assert main(["extract-corpus", "--project-root", str(root), "--output", str(output)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["documents"] == 1 and report["errors"][0]["document_id"] == "Bad"
    assert (output / "Good.json").exists()
    with pytest.raises(FileExistsError):
        extract_corpus(root, root / "data/manifest.json", output)
    manifest[0]["path"] = "../outside.pdf"
    (root / "data/manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="under data/documents"):
        extract_corpus(root, root / "data/manifest.json", tmp_path / "unsafe")
