# Homework 2, Task 2: local sanitization and exact deduplication

Run extraction in memory, then sanitize, hash and deduplicate before writing:

```powershell
python -m ai_project ingest-corpus --output data/sanitized
```

Or sanitize existing extraction JSON without changing it:

```powershell
python -m ai_project sanitize-corpus --input data/extracted --output data/sanitized-from-extracted
```

Both commands accept `--project-root`, `--manifest`, and `--config`. Manifest
paths are relative to the project root; input, output and config paths are
relative to the working directory. The output must be a new directory, separate
from raw and extracted inputs. Existing sanitized files are also rejected as
extraction inputs: their redacted text cannot supply pre-redaction hashes.
No dependencies or services were added. Processing is local and deterministic.

`sanitization.py` provides `sanitize_document(extracted, config)`, returning a
deep `SanitizedDocument` copy. Regex rules cover email addresses, common phone
forms (including E.164), EMP-prefixed or labeled employee IDs, contextual bank
account/routing values and masked suffixes. Typed placeholders include `[PERSON]`,
`[EMAIL]`, `[PHONE]`, `[EMPLOYEE_ID]`, `[ADDRESS]`, `[BANK_ACCOUNT]`,
`[BANK_ROUTING]` and `[MEDICAL_INFO]`.

Personal names are discovered from explicit person labels, employee agreement
contexts and name/contact combinations, then replaced throughout that document.
Street addresses use configurable patterns. Production rules contain no list
of PeopleFlow names or exact addresses. Document-local discovery avoids sharing
identities between files. English medical terms plus an identified individual
activate clinical case-note rules; diagnosis, illness dates, clinician notes
and case evidence are replaced. General policy discussions remain unchanged.
Clinical spans stop before payroll fact labels or currency amounts. This is
not general clinical entity recognition.

Sanitizer version 1.1 also recognizes subsequent first/last-name references to
an already identified full name in the same document. A name part must have a
unique owner and person-specific context (a supported subject/action phrase,
personal possessive field, honorific or explicit person label). Common-word name
parts, shared names and insufficient context remain unchanged and produce
counted warnings without matched values. `ambiguous_name_parts` configures the
common-word guard; supplying it replaces the default list. No aliases are shared
across documents, and shorter names are not inferred before a full-name mention.
The existing protected-field policy still preserves headings and metadata.

Use `config/sanitization.example.json` as a starting point for local detection
configuration. `person_values` and `address_values` supplement detection;
`person_patterns` and `address_patterns` replace the default pattern lists when
provided. A pattern can select a named `(?P<pii>...)` group; otherwise its whole
match is the value. Discovered names/addresses are replaced in all non-heading
blocks, including table cells. `medical_terms` replaces the clinical context
lexicon. For example, a pattern `Staff member = (?P<pii>[^;]+)` supports a new
label. Keep configurations containing actual personal values private; they are
not copied to generated reports. Configuration patterns are trusted local code.

Sanitization preserves block types, order, list markers/nesting, source
locations, section paths, titles/headings and all manifest metadata. Tables are
sanitized cell by cell; their text view is rebuilt without counting each
replacement twice. Headers/footers are sanitized for traceability but remain
non-semantic. Future semantic consumers must use `document.semantic_blocks` or
filter `is_semantic`; no chunking, embedding or retrieval stage is implemented.

If a detected identifier occurs in protected headings, paths, list markers,
source-location parts or metadata, the document is withheld rather than leaking
the identifier or silently modifying protected structure. This is a detectable
conflict, not a request for approval. Unrecognized PII is still possible.
Original exception messages and extraction warnings are never copied into
processing reports. Per-document failures use safe stage/error codes. Parser
stdout/stderr is suppressed during extraction in this workflow. The CLI prints
counts only. Failure of any document returns a nonzero status; the report
identifies withheld IDs, and successful documents may still be inspected.

`deduplication.py` computes two SHA-256 hashes:

- `source_hash`: original source-file bytes, before extraction/redaction.
- `content_hash`: canonical semantic content **before redaction**. Canonical
  serialization includes title, ordered block types/text, heading paths, list
  metadata and table cells. Whitespace collapses within strings. Source
  locations, page furniture, page boundaries and generated warnings are omitted.
  Table text is derived from cells and is not hashed twice.

Different block/row/column structures and meaningful text remain distinct.
Sanitized hashes are never used for duplicate selection: different personal
records can become identical after redaction. Matching source hashes and matching
semantic hashes are reported separately. Only active documents with the same
pre-redaction content hash and the same non-identity manifest metadata can be
excluded. Access groups, versions, effective dates, supersession relationships,
language, category and other policy metadata must agree. Historical/non-active
documents are always retained, even when text matches. Within an eligible group,
the lexicographically smallest document ID is retained regardless of input order.
No original file is deleted.

`ingestion.py` validates manifest entries and, when loading extraction JSON,
requires an exact metadata match. Original bytes remain necessary for source
hashing. It sanitizes in memory before any generated document is written.
Outputs have deterministic paths and sorted JSON keys, with no timestamps:

```text
data/sanitized/
  documents/<ID>.json     # Sanitized, included documents
  duplicates/<ID>.json    # Sanitized duplicate trace copies, if any
  report.json
```

Documents record both hashes, redaction counts and `excluded_as_duplicate_of`.
The report records counts, detected content/source duplicate groups, explicit
exclusions, replacements by category, limitations and per-document warnings.
Use only `documents/` for future ingestion; `duplicates/` is trace output.
Counts describe replaced occurrences, not distinct individuals; table cells are
counted once. Non-semantic trace blocks can contribute redaction counts, but
never enter semantic hashing or processing.

All access and lifecycle metadata is retained. Redaction neither changes a
confidential document to `all_employees` nor implements authorization. Sanitized
files, duplicate reports and hashes still require appropriate storage/access
controls; salary facts, business context and indirect identifiers can enable
reidentification. They are not certified anonymous/public artifacts.

Known limitations: contextual English/Latin-capitalized name rules cannot cover
every name, language or unlabeled signature. Default address patterns target
numbered North American street addresses. Unusual phone/employee/account
formats, spaced IBANs, unlabeled bank values and arbitrary medical prose can
escape detection. Bank institution names, ticket/signature references, business
dates, salaries and policy facts are retained. Configure detection and review
new source styles locally. The report explicitly states these limitations;
passing fixed-corpus checks is not a claim of complete PII coverage.

Run offline tests:

```powershell
python -m pytest -q --basetemp .pytest_tmp_task2
```

The tests cover identifiers, configurable detection, clinical cases, business
fact/structure preservation, unchanged original artifacts, semantic exclusions,
hash stability, whitespace normalization, redaction collisions, policy/version
boundaries, ordering-independent duplicate selection, safe errors, both CLI
paths and regression checks across the real 32-document corpus.

Validated corpus run: `data/sanitized-name-references/report.json` records 32 sanitized/included
documents, zero withheld documents, zero content/source duplicate groups, and
zero duplicate exclusions. The version 1.1 regression scan finds no remaining
standalone first/last-name tokens for the identified corpus people, and no
ambiguous short-reference warnings. Raw documents and original extraction JSON
hashes are unchanged. Previous generated runs remain separate.

| Category | Replacements |
| --- | ---: |
| PERSON | 17 |
| EMAIL | 4 |
| PHONE | 3 |
| EMPLOYEE_ID | 6 |
| ADDRESS | 3 |
| BANK_ACCOUNT | 3 |
| BANK_ROUTING | 2 |
| MEDICAL_INFO | 4 |
| Total | 42 |

All 28 Task 2 tests and 27 extraction tests pass. The complete offline suite
reports 291 passed, 21 subtests passed and one existing failure in
`tests/test_ollama.py::test_defaults_do_not_load_secrets`. The unchanged Ollama
configuration calls the mocked `load_dotenv`, contrary to that test's expectation.
No live APIs or secret-file reads were used. Ruff passes for the new modules and
tests; whitespace checks pass.
