# AI HR Support Assistant

## Goal

Parse unstructured HR support tickets into validated JSON and eventually provide
preliminary troubleshooting. The current AI Engineering homework focuses on
structured outputs, model evaluation, and prompt engineering.

## Current dataset

- 100 synthetic HR support messages: 70 English, 20 Ukrainian, 10 Russian.
- 40 reference labels: 15 development examples and 25 holdout examples.
- Existing 30 tickets and 10 labels are preserved; all original labels are in development.
- See data/README.md for split usage and review status.

## Agreed output schema

All fields must be present, including nullable fields. No extra fields are allowed.

| Field | Type / values |
| --- | --- |
| summary | string |
| category | authentication, absence, attendance, shifts, payroll, employee_profile, technical, other |
| priority | low, medium, high, unknown |
| application | string or null |
| language | en, uk, ru |
| requires_support | boolean |
| details | object with required error_code and error_message fields, each string or null |
| suggested_actions | list of strings, zero to three items |

The models live in src/ai_project/models.py. JSON parsing uses
HRSupportTicket.model_validate_json; JSON Schema is available through
HRSupportTicket.model_json_schema().

## Planned comparison and evaluation

Compare a hosted LLM provider with a local model served through Ollama.
OpenRouter is the hosted service currently used during experimentation;
the comparison models are not finalized.

Metrics:

- Field accuracy against the golden set.
- Schema validity.
- Latency p50 and p95.
- Estimated cost per 1,000 documents.

Metric implementation and detailed scoring rules are deferred.

## Current implementation scope

Phase 1 adds single-ticket OpenRouter parsing through the OpenAI Python SDK,
strict JSON Schema requests, Pydantic response validation, bounded transient
retries, and offline mocked tests. The inherited mock CLI remains available.
The existing schema is packaged at src/ai_project/models.py; the preexisting
models/models.py copy is retained unchanged. The current v1 prompt is stored at
docs/prompts/v1.txt, with prompts/v1.txt supported as the primary location.
The original provider implementation phase excluded dataset changes. The separately
authorized dataset extension now contains 100 tickets and 40 reference labels;
prompts, provider implementations, and prediction results remain unchanged. Sequential batch
processing is now supported through parse-all, reusing single-ticket parsing and
saving atomic incremental results. No automatic resume is implemented.
Live API requests require explicit approval; automated tests use mocks only.

Local Ollama is supported through the existing OpenAI SDK at a loopback /v1 endpoint.
Both parse-ticket and parse-all accept --provider openrouter|ollama (default openrouter).
The default local model is qwen3:8b. Requests disable thinking through
reasoning_effort=none and validate only final message content using the unchanged
AIService. Schema validation failures are not repaired. Ollama settings come from
the process environment without reading .env or requiring a hosted API key.

## Future extensions

Homework 2 Task 1 now provides offline document extraction and normalization in
`src/ai_project/extraction`, using a separate Pydantic document/block schema.
It preserves the complete PeopleFlow manifest metadata and ordered content,
including sections, lists, table cells, and PDF page locations. Run
`python -m ai_project extract-corpus --output data/extracted/run-01` with a new
output directory. See `docs/EXTRACTION.md` for details and corpus validation.
Homework 2 Task 2 adds local deterministic sanitization and SHA-256 exact
deduplication through `ingest-corpus` and `sanitize-corpus`. Sanitized output is
separate from raw/extracted artifacts; access/lifecycle metadata is preserved.
See `docs/SANITIZATION.md` for detection limits and hash/duplicate policy.
Homework 2 Task 3 adds deterministic section-aware chunking after deduplication,
with a configurable 400-token target and 600-token maximum using a documented
local lexical counter. It writes chunks.jsonl, chunking_manifest.json and a
three-document fixed-size comparison. Historical versions, access metadata,
source/content hashes and page references are preserved. See README.md and
docs/CHUNKING.md for observed corpus counts, examples and token-count limitations.
Homework 2 Task 4 adds `index-corpus` and `search`, consuming canonical chunks.jsonl.
Local Ollama /api/embed batches default to bge-m3; persistent Qdrant local mode
uses cosine similarity and an access-group allowlist before ranking. Rebuilds
publish a replacement collection, remove stale points, and record the model,
vector dimension and input SHA-256. Default search allows only all_employees;
--hr-access explicitly adds hr_confidential for local smoke testing. See
docs/RETRIEVAL.md for PowerShell commands and validation results.
Homework 2 Task 5 adds `eval-retrieval` with 12 draft corpus-grounded relevance
cases and a separate employee-only Contract A access-control check. It validates
labels against the active indexed corpus, calls the existing vector search at
k=5, and reports mean Recall@5 and MRR@5. The saved vector baseline is provisional
until the user reviews questions and expected chunks. See
docs/RETRIEVAL_EVALUATION.md and evals/retrieval_cases.json.
The Homework 1 ticket schema and providers are unchanged. BM25, reranking,
generation, and answer evaluation remain outside the implemented scope.

- Versioned prompts stored separately from application code.
- RAG-based troubleshooting using relevant HR support knowledge.
- Agentic troubleshooting workflows.
