# PeopleFlow synthetic HR knowledge base

The corpus-wide fictional-data disclaimer is in the [project README](../README.md).
The 32 English source files are presented as raw internal client materials.

The approved IDs and exact titles are recorded in `manifest.json`. There are
exactly **32 source documents** under `documents/`:

| Specification group | IDs | Count |
| --- | --- | --- |
| HR system user manuals | M01–M12 | 12 |
| Employment contracts and HR policies | C01–C08 | 8 |
| Support and troubleshooting | S01–S06 | 6 |
| FAQs, release notes, versioned guides | F01–F06 | 6 |

Formats: **11 HTML, 10 PDF, 4 DOCX, 7 Markdown**. Category directories are
`manuals`, `contracts`, `policies`, `support`, `faq`, and `release_notes`.
F05 and F06 reside in `manuals` because they are guides, while remaining in
specification group F. Length and structure vary by purpose: agreements contain
employment terms and acceptance blocks, policies set out rules, and guides and
FAQs focus on the employee's task. Sources retain ordinary titles, revision or
release dates, and policy owners where appropriate. Technical IDs, lifecycle
flags, access groups and relationships remain in the manifest. Corpus disclaimers
and generic metadata blocks are excluded from source bodies and footers.

## Fictional application conventions

The current release is v2.0, effective **2026-09-01**. Historical v1.8 guidance
was effective **2026-03-01** through **2026-08-31**. These dates were selected
for this corpus; they do not describe a real product release.

| Historical source | Current replacement | Deliberate difference |
| --- | --- | --- |
| M06 | M07 | Manager direct adjustments become employee correction requests with manager approval |
| F05 | F06 | HR Support cancellation becomes self-service cancellation before leave starts |
| F03 | F04 | Release notes document these changes and manager-initiated swaps becoming employee-initiated swaps |

Historical documents state their original date range and name their replacement.
The manifest records their superseded status. A new action after cutover follows
current procedures even when it concerns an older record; payroll locks still
apply. Versions describe application behavior, not contract entitlement changes.
Contract A provides 25 annual leave days, 10 paid sick days, and 40 hours/week;
B provides 15, 5, and 24 respectively; C provides 28, 12, and 40 respectively.

Workplace timezones govern rosters, leave-start boundaries, and weekly attendance.
Payroll cutoff and support hours explicitly use UTC. A support business day has
eight hours, Monday–Friday 09:00–17:00 UTC, excluding 1 January and 25 December.
Support targets concern first response rather than guaranteed resolution.

## Raw synthetic personal information

Exactly these sources contain synthetic personal or sensitive example data:
**M02, M04, M09, M12, C01, C02, C03, C05, S01, S05**.
The other 22 documents contain procedural or policy material without personal
examples. The current examples use newly composed ordinary names, `EMP-` employee
identifiers, `example.com` email addresses, and North American phone numbers in
the reserved 555-0100–0199 range. The street addresses were composed for the
invented Oregon municipality of Alderhaven, without residential address lookups.
No dates of birth were present, and none have been added.

Bank names are invented. Account and routing fields contain masked suffixes only
(`****4826` and `*****6214`, for example); the corpus contains no complete account
number, routing number, IBAN, payment credential or government identification
number. Medical records, sickness dates, salary amounts and payroll arithmetic
remain unchanged. A realistic name may coincidentally match a real person; no
profile was sourced from or researched about a real person.

The contact conventions follow [IANA's reserved example domains](https://www.iana.org/help/example-domains)
and [NANPA's reserved fictional phone range](https://nanpa.com/numbering/555-line-numbers).

| Changed sources | Personal details revised |
| --- | --- |
| M02 | Name, email, reserved phone, home address |
| M04 | Name and employee ID in the sickness record |
| M09 | Name, employee ID, bank name, masked account and routing suffixes |
| M12 | Signer name, email and signature receipt reference |
| C01 | Employee name throughout, email and home address |
| C02 | Employee name throughout, reserved phone and employee ID |
| C03 | Employee name throughout, home address, bank name and masked suffixes |
| C05 | Name and employee ID in the absence record |
| S01 | Email, reserved phone, employee ID and ticket reference |
| S05 | Name, employee ID, bank name and masked payment destination |

These are intentionally **unsanitized raw sources**. Do not remove these examples
before implementing the separately scoped sanitization experiment. The manifest
PII flag identifies documents containing personal examples, not all documents
that merely discuss sensitive record types. Access groups are corpus metadata,
not an implemented authorization system: `all_employees`, `managers_hr`,
`hr_confidential`, and `hr_payroll` describe the intended audience. Restricted
samples must eventually receive record-level authorization as well.

## Reproduction and validation

The generation scripts are isolated from the Homework 1 package and CLI. Their
authored content lives in `scripts/peopleflow_content.py`; no prompts, providers,
ticket records, predictions, or evaluation logic were changed. The optional
`corpus` dependency group supplies python-docx, ReportLab, and pypdf. With those
dependencies and Pydantic v2 installed, run from the repository root:

```text
python scripts/generate_peopleflow.py
python scripts/validate_peopleflow.py --report data/corpus_validation.json
python -m pytest
```

Generation overwrites only the approved 32 output paths and leaves the manifest
unchanged. Focused editorial updates can select document IDs through the existing
generator function; this PII revision changed only the 10 listed sources, leaving
the remaining 22 files byte-for-byte unchanged. Generation does not delete
unexpected files; validation reports any extra source file.
Validation checks Pydantic metadata, exact approved titles, IDs, paths, formats,
dates, lifecycle status, reciprocal supersession, actual file inventories,
readability, package signatures, contract benefits, workflow and policy facts,
authored personal examples, and the absence of artificial headers, training
disclaimers and ID-based references. Word counts are reported without enforcing
a uniform length. Negative tests exercise corrupt signatures, unexpected files,
metadata tampering, PII leakage, version links, altered rules and editorial regressions.
No generation or validation command makes network or paid API requests.

`corpus_validation.json` records the machine-readable results. PII checks verify
the known authored profiles, cross-document assignment, repeated contract names,
reserved contacts, masked bank fields and absence of old placeholder markers; they are not
a general-purpose PII sanitizer or proof that arbitrary future text is PII-free.
For the PII revision, all four changed PDFs (five rendered pages) were visually
reviewed. The other six PDFs are unchanged from the earlier full PDF review.
All four DOCX files pass package and content parsing. DOCX visual QA additionally
requires a working Word/LibreOffice renderer; the current environment lacks
LibreOffice, and the renderer could not run. This limitation is separate from
source-file readability and is not represented as a successful visual check.

No ingestion, chunking, embeddings, indexing, RAG, or evaluation implementation
is part of this corpus task. The validation report is corpus QA only.
