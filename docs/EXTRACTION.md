# Homework 2, Task 1: extraction and normalization

Run locally, without model calls:

```powershell
python -m pip install -e ".[dev,corpus]"
python -m ai_project extract-corpus --output data/extracted/run-01
python -m pytest -q
```

The installed `ai-project extract-corpus` entry point is equivalent. Optional
`--project-root` and `--manifest` select the project and manifest (manifest paths
are relative to the project root). Output must be a new directory. Existing
outputs and raw documents cannot be overwritten. Each successful manifest entry
produces `<document_id>.json`; `report.json` records aggregate statistics,
warnings by ID, empty documents, and parser errors. Other documents continue
after an individual extraction failure. Exit status is nonzero on setup errors,
extraction errors, or empty documents. Warnings alone do not fail the command.

If Windows restricts pytest's default temporary directory, use a fresh workspace
directory: `python -m pytest -q --basetemp .pytest_tmp_run01`.

The `src/ai_project/extraction` package contains Pydantic v2 models, shared
normalization/heading tracking, separate PDF and DOCX parsers, HTML/Markdown
parsing, and manifest-driven persistence. Dependencies are PyMuPDF, python-docx,
BeautifulSoup4, and markdown-it-py; ReportLab and pypdf remain corpus-generation
and test dependencies. No model provider, credential, or network access is used.

Each document includes its manifest ID, path, title, declared format, complete
manifest metadata, schema version, ordered blocks, and warnings. Blocks retain
type, text, a hierarchical `section_path` (including the current heading), and
locations where available. Heading levels and list ordering/nesting/explicit
markers are separate fields. In schema version 1.1, list `text` never includes
its leading marker: `{"text": "Open profile", "marker": "3.", "ordered": true,
"list_level": 0}`. Literal PDF/DOCX prefixes are split off, native DOCX numbering
uses its numbering definitions and counters, and Markdown retains its authored
bullet or ordered delimiter. To render a plain-text item, prepend `marker` once;
when using a renderer that generates list markers, pass only `text`.
Tables contain ordered `rows` with cells indexed
by column; their text view uses tabs and newlines. Character statistics count
block text once, including retained furniture, excluding metadata and the
duplicated table rows representation. Per-format counts describe successful
documents; `manifest_documents` includes all attempted entries. The report also
counts `semantic_blocks` and `semantic_characters` separately.

Every block serializes `is_semantic`, derived from its type during validation.
Headers, footers, and page breaks are false; body blocks are true. The Python
`document.semantic_blocks` property returns body content in source order. Future
chunking, embedding, and retrieval consumers must use that property (or filter
JSON blocks by `is_semantic`) instead of concatenating all trace blocks. Those
stages are not implemented here. Non-semantic blocks have empty `section_path`
and never change heading tracking. `blocks` retains all trace content and source
locations; the semantic view neither reorders nor duplicates body content.

HTML uses DOM traversal; Markdown uses markdown-it tokens (GFM tables enabled)
and their line maps before the shared HTML traversal. DOCX walks paragraph and
table XML in body order, with style/numbering-aware list recognition. DOCX
headers/footers are retained once per section, before the body, with separate
part locations; they are not assigned invented page positions. Body elements
retain their original order. Rendered DOCX page boundaries are unavailable.

PDF uses PyMuPDF text spans, bounding boxes, font-size heading inference, and
table detection. Horizontal-rule tables infer column boundaries from separate
header text runs. Pages remain separate, with explicit `page_break` blocks.
Wrapped paragraph lines join with spaces; table cells preserve internal breaks.
PDF header/footer classification requires a margin position, smaller typography
than the body, and either recurrence on separate pages in the same margin band
or a separate page-number line. Proximity or repetition alone is insufficient;
ambiguous margin content remains semantic. All classified furniture is retained.
HTML document-level header/footer landmarks are likewise retained as trace
blocks; article/section headers remain meaningful body structure. Markdown does
not infer page furniture from repeated text. Reading order
is geometric top-to-bottom/left-to-right, appropriate for this single-column
corpus; arbitrary multicolumn, irregular tables, and font-only headings require
review. Scanned pages produce warnings; OCR is not implemented.

Normalization collapses horizontal whitespace and excess blank lines, removes
soft hyphens, and preserves Unicode, explicit hard breaks, list boundaries,
and cell relationships. It does not paraphrase, sanitize, deduplicate, or infer
business facts. Parser-inherent tolerance applies to incomplete HTML and
Markdown, while corrupt/encrypted binary documents produce extraction errors.

Corpus validation checks all 32 documents, raw-file SHA-256 preservation,
manifest metadata, list invariants, table counts, and semantic exclusion. When
the previous JSON corpus at `data/extracted/` is present, a separate regression
test compares every block's text, source order, table cells, locations, and body
section paths, allowing only the intended marker normalization. This optional
comparison no longer depends on corpus-generation scripts. Separate tests
exercise all four formats, Unicode, section paths, nested lists, tables, PDF
pages/repeated margin and body text, empty/malformed inputs, schema validation,
CLI error continuation, and input/output protection.

Quality finding: `S02.md` omits the GFM table delimiter row. A constrained
fallback extracts a whole paragraph of consistently sized pipe rows and reports
a warning with its source line. No raw source was changed. Every PDF reports
the geometry/heading-inference advisory. No authored business content or table
cells were lost in the corpus regression checks.

This extraction stage does not sanitize or deduplicate. The separate Task 2
workflow is documented in [SANITIZATION.md](SANITIZATION.md). Chunking, embeddings,
storage/retrieval, generation and RAG evaluation remain unimplemented.

Validated run: `data/extracted-v1.1/report.json` contains 32 successful
documents, 494 blocks, 75,509 extracted characters, and five tables, with no
empty documents or extraction errors. Format counts are 11 HTML, 10 PDF,
4 DOCX, and 7 Markdown. Ten PDF advisories and the S02 warning are recorded.
The semantic stream has 476 blocks and 75,200 characters. The 17 header/footer
blocks and one page boundary are retained for traceability and excluded from
the semantic stream. The previous JSON corpus is unchanged.

Verification: all 27 extraction tests pass, and Ruff passes for the extraction
package and tests. The complete offline suite reports 263 passed, 21 subtests
passed, and one existing failure in
`tests/test_ollama.py::test_defaults_do_not_load_secrets`: the unchanged Ollama
settings implementation calls `load_dotenv`, contrary to that test's expectation.
The call is mocked by the tests; no secret files or live APIs were accessed.
