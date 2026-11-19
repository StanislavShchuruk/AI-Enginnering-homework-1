# PeopleFlow chunking

Task 3 extends the existing offline ingestion function, `process_corpus`, after
sanitization and exact deduplication. The existing pending Task 2 implementation
and its duplicate/lifecycle/access policy are reused. No API, tokenizer download,
embedding, retrieval, or generation is involved.

## Inputs and boundaries

Only sanitized documents without `excluded_as_duplicate_of` are passed into
chunking. Semantic blocks keep extraction order and the existing `section_path`,
which extraction derives from the heading-level stack. Chunking never crosses a
change in that path, including repeated headings with intervening sections.
Headers, footers, page breaks, and blocks explicitly marked `is_semantic: false`
are excluded. The chunker also rejects unsanitized input. It does not filter
`status`, so historical versions retained by deduplication remain available.

The section packer keeps adding atomic units while doing so moves its count
closer to the configured target and remains under the maximum. A list's adjacent
items form one unit when they fit under the maximum; a table is likewise one unit.
An indivisible fitting unit may exceed the target, but never the maximum. Final
section remainders and heading-only sections can be much smaller than the target.
No ancestor heading text is injected into the body: the full hierarchy remains in
metadata. This keeps the baseline and structured inputs equivalent.

Oversized paragraphs and headings split near the target, preferring line/paragraph
breaks and then sentence endings in the latter half of the token window. Without
those boundaries, a hard lexical token boundary guarantees progress. An oversized
list splits between complete items near the target; original markers and nesting
indentation are preserved. A single oversized item splits its prose with its
original marker repeated on each continuation. No new numbering is invented.

Oversized tables split by rows near the target; each fragment repeats row zero.
The extraction schema has no explicit header-row flag, so **row zero is assumed
to contain column headers**. A single row larger than the available budget is
continued at prose/token boundaries under the same repeated header. Such fragments
are text continuations rather than independently reconstructable table grids;
their original table block index and location remain available. If a header alone
uses the maximum budget, preserving the full header and a row is impossible: the
run raises `ValueError` rather than emitting an over-limit chunk. The same rule
applies to a list marker leaving no room for content. Increase the maximum for
these pathological inputs. No current corpus document reaches these edge cases.

The README documents the precise shared lexical counter, observed comparison,
hash semantics and ID inputs. It deliberately does not equate these counts with
any provider's model tokenizer. Repeated table headers and continued list markers
count toward each output chunk's size. There is no generic overlap.

## Artifacts and checks

Full run: `data/chunked/task3-run02/`; independent repeat: `task3-run03/`.
Each directory contains:

- `documents/`: canonical sanitized JSON documents.
- `duplicates/`: sanitized excluded copies, if any, for existing audit behavior.
- `chunks.jsonl`: one typed chunk record per line, in document/section order.
- `chunking_manifest.json`: settings, counter version, hash definitions, document
  hashes and per-document counts, plus total document/chunk counts.
- `chunking_comparison.json`: M11, C02 and S03 counts, concrete 400-token boundary
  excerpts, corresponding structured boundaries and intact table/list references.
- `report.json`: existing ingestion report, extended with the chunking manifest.

Observed: 32 input/canonical documents, 184 chunks, zero excluded copies and zero
withheld documents. The corpus has 13,599 semantic lexical tokens; chunks range
from 2 to 188 tokens. Fifty-nine chunks carry page numbers. All files in the two
full-run output trees compared byte-for-byte equal. IDs are stable for identical
inputs/settings; changing content, metadata or chunking settings may change IDs.

Run focused offline checks:

```powershell
python -m pytest -q tests/test_chunking.py tests/test_ingestion.py
```

Tests validate real-corpus section containment and full semantic token preservation,
metadata/hash propagation, historical inclusion, long-block split bounds, repeated
headers, original numbering, and deterministic canonical selection. A synthetic
integration corpus supplies two active identical copies and one historical copy;
only the first active copy and the historical document emit chunks. Reversing the
input manifest yields byte-identical chunk and report artifacts. This fixture
proves exclusion behavior that the duplicate-free real corpus cannot exercise.
