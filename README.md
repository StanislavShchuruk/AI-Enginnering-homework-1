# AI HR Support Assistant

## PeopleFlow document corpus

The [32-document PeopleFlow corpus](data/CORPUS_README.md) is fictional.
PeopleFlow, its employer, all identities, contact details, medical examples,
salary amounts, payment identifiers, procedures and contractual benefits are
invented for this project. No document represents real employment, legal,
taxation or privacy guidance. Reserved email and phone examples and masked
bank details must remain nonfunctional when revising the materials.

The files under `data/documents/` are presented as raw client-provided documents.
Technical IDs, access groups, PII flags and version relationships belong in
`data/manifest.json`; the source documents carry only ordinary business metadata.
Offline structured extraction is available; see [extraction documentation](docs/EXTRACTION.md).
RAG retrieval and generation are not implemented.

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Configure provider settings locally before live inference.
python -m ai_project reproduce
# Or regenerate reports from existing predictions without calling providers:
python -m ai_project reproduce --eval-only
```

See [all commands and safe reruns](docs/commands.md) for setup, parsing, evaluation,
and reproduction. The [manual evaluation report](docs/evaluation_report.md) remains
separate from generated reports in `results/reproduction/`.


A Python 3.11+ AI Engineering homework project for converting messy HR support
messages into validated JSON with Pydantic v2. Supports single-ticket and sequential
batch processing through OpenRouter or local Ollama, with offline mocked tests.
See [project context](docs/PROJECT_CONTEXT.md) for dataset requirements,
planned evaluation, and future RAG and agent work.

The inherited mock command still echoes prompts offline. The parse-ticket command
calls the selected provider only when you explicitly run it. Saved batch results can be
evaluated entirely offline.

## Quick start

Open a terminal in this directory. On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
ai-project "Hello, AI!"
```

On macOS/Linux, activate with `source .venv/bin/activate` instead.
You can also run `python -m ai_project "Hello, AI!"` after installation.

Expected output: `[mock] You said: Hello, AI!`

## Configuration

Settings read process environment variables. Defaults are `AI_PROVIDER=mock`
and `AI_MODEL=demo`. The model setting is reserved for a future real provider;
the mock provider does not use it. `.env.example` documents these variables;
copying it to `.env` does not load them automatically.

PowerShell example:

```powershell
$env:AI_PROVIDER = "mock"
```

Keep API keys in environment variables and out of source control.

## Project structure

```text
src/ai_project/
  models.py       Pydantic ticket models and enums
  config.py       Environment settings
  providers.py    Provider interface and offline mock
  service.py      Application logic and input validation
  cli.py          Command-line interface
tests/            Unit tests
docs/             Persistent project context
data/             Local datasets (ignored by Git)
models/           Local model artifacts (ignored by Git)
```

## Development

```powershell
python -m unittest discover -s tests -v
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

To run without installing the package, set `$env:PYTHONPATH = "src"` in
PowerShell, then run `python -m ai_project "Hello"` or the unit test command.
On macOS/Linux, use `PYTHONPATH=src python -m unittest discover -s tests -v`.

## Phase 1: parse one ticket with OpenRouter

Install from the project root in your virtual environment:

```powershell
python -m pip install -e ".[dev]"
```

Set OPENROUTER_API_KEY and OPENROUTER_MODEL in your process environment.
The current config also loads .env from the working directory at application runtime.
Tests mock that loader and never read the file. .env.example documents names and
defaults only; it must not contain real secrets. To enter the key without putting
it in shell history (PowerShell 7):

```powershell
$env:OPENROUTER_API_KEY = Read-Host "OpenRouter API key" -MaskInput
$env:OPENROUTER_MODEL = "openai/gpt-4o-mini"
```

Choose a model/endpoint that supports Structured Outputs and all supplied parameters.
The example model is a starting choice, not a guarantee of endpoint availability.
Run the first manual request yourself:

```powershell
ai-project parse-ticket --ticket-id 1 --prompt-version v1
```

Equivalent: python -m ai_project parse-ticket --ticket-id 1 --prompt-version v1.
Run from the project root, or supply --project-root with its absolute path.
This sends one selected ticket to OpenRouter and can incur API charges.

The command reads data/tickets.json by integer ID. It loads prompts/v1.txt when
present; this checkout currently stores the unchanged prompt at docs/prompts/v1.txt,
which is the supported alternate location. Only v1 is accepted. Prompts are external
project files, not embedded in the installed wheel.

The provider sends HRSupportTicket.model_json_schema() with json_schema and
strict=true, plus provider.require_parameters=true to require compatible routing.
Unsupported requests fail explicitly: no json_object/text fallback and no repair.
The service validates the returned content with HRSupportTicket.model_validate_json().
Output is a JSON envelope containing ticket, elapsed_seconds (request, retries,
and validation), returned model, and usage (null when unavailable).

Optional environment settings:

| Name | Default | Allowed values |
| --- | --- | --- |
| OPENROUTER_TEMPERATURE | 0 | 0 through 2 |
| OPENROUTER_TOP_P | 1 | greater than 0, at most 1 |
| OPENROUTER_TIMEOUT_SECONDS | 30 | positive finite seconds per SDK request |
| OPENROUTER_MAX_RETRIES | 2 | integer 0 through 5, additional attempts |

Retries apply only to 429, 5xx, connection failures, and network timeouts. The SDK's
built-in retries are disabled; exponential delays are capped at 8 seconds. Timeout
is not a total wall-clock deadline. Authentication, unsupported schema/parameters,
refusals, truncated responses, and invalid JSON are not retried. Errors preserve
HTTP status and attempt count without printing provider response bodies or keys;
original SDK exceptions remain available as chained causes to callers.

```powershell
python -m pytest -q
```

All API tests mock the SDK and use dummy keys; no live API call is needed for tests.

## Sequential batch processing

From the project root, after configuring OpenRouter as above, run:

```powershell
python -m ai_project parse-all --prompt-version v1 --output results/openrouter_v1.json
```

This makes sequential requests for every input ticket using the same service,
Pydantic validation, and provider retries as parse-ticket. It can incur API costs.
--output is required. Existing output is refused unless you deliberately add
--overwrite; use a fresh filename to retain previous runs. Relative output paths
are relative to the working directory. --project-root selects the input project.
Datasets and prompt files cannot be used as output destinations.

The output format is:

```json
{
  "metadata": {
    "provider": "openrouter",
    "configured_model": "openai/gpt-4o-mini",
    "prompt_version": "v1",
    "temperature": 0.0,
    "top_p": 1.0,
    "timestamp": "2026-10-18T12:00:00+00:00"
  },
  "total_tickets": 30,
  "completed": false,
  "results": []
}
```

Each results entry contains ticket_id, status (success or error), output (the full
validated HRSupportTicket on success, otherwise null), elapsed_seconds, model,
usage, and error (null on success). Successful model/usage values come from the
provider response. Failed entries use the configured model and null usage because
the service did not return a successful TicketResult. Error messages use safe
fixed descriptions, optionally preserving an HTTP status; raw exception bodies,
response text, and credentials are never written to error messages or metadata.

An initial snapshot is published before processing. Each completed result is saved
in input order by flushing a temporary file in the output directory and atomically
replacing the destination. Filesystem write errors stop the run while preserving
the previous snapshot. Individual ticket errors are saved and processing continues.
Ctrl+C leaves the last saved results with completed=false; the interrupted ticket
may already have incurred API costs. completed=true means all tickets were attempted,
including failures. Exit code is 1 if any tickets failed, otherwise 0. There is no
automatic resume: rerunning requires a new path or --overwrite and processes all
tickets again. Do not run concurrent writers against the same output file.

## Local Ollama

Install Ollama from https://ollama.com/download, then prepare the local server/model:

```powershell
ollama pull qwen3:8b
ollama serve
```

If the Ollama desktop application is already serving localhost:11434, skip
ollama serve. Run the parser in a separate terminal from the project root:

```powershell
python -m ai_project parse-ticket --provider ollama --ticket-id 1 --prompt-version v1
python -m ai_project parse-all --provider ollama --prompt-version v1 --output results/ollama_v1.json
```

The batch command processes all 30 tickets in the current dataset. Existing output
is protected; choose a new path or explicitly supply --overwrite for another run.
Keep --provider openrouter for hosted processing; omitting --provider preserves the
previous OpenRouter default. Both providers use the same AIService, HRSupportTicket
validation, v1 prompt loading, and atomic batch progress saving.

Ollama reads only these process environment variables (not .env); no API key is needed:

| Name | Default |
| --- | --- |
| OLLAMA_BASE_URL | http://localhost:11434 |
| OLLAMA_MODEL | qwen3:8b |
| OLLAMA_TEMPERATURE | 0 |
| OLLAMA_TOP_P | 1 |
| OLLAMA_TIMEOUT_SECONDS | 120 |

For example, use $env:OLLAMA_MODEL = "qwen3:8b" in PowerShell. Sampling/timeout
validation is shared with OpenRouter. OLLAMA_BASE_URL accepts loopback HTTP(S)
addresses, with optional /v1; /v1 is appended exactly once. Remote endpoints,
embedded credentials, query parameters, and custom API paths are rejected. Local
requests ignore environment proxies and do not follow redirects, preventing provider
mix-ups. OpenRouter always uses its fixed hosted URL. The local SDK uses the
non-secret placeholder key "ollama" and has automatic retries disabled; Ollama
defaults to one attempt with the configured timeout. OpenRouter retry settings
continue to apply only to OpenRouter.

Use a recent Ollama version supporting JSON Schema response_format and
reasoning_effort="none". For Qwen3 this requests thinking disabled; any separate
reasoning_content is ignored. Only message.content reaches Pydantic. If thinking
text is mixed into content, validation fails without stripping or repairing it.
Unsupported schema/thinking options fail explicitly rather than silently changing
formats. See [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility).

Successful batch records now also contain provider, temperature, and top_p alongside
the returned model, elapsed_seconds, and usage. Missing token counts are null; usage
itself is null if absent. Run metadata retains configured_model. Failed records use
the configured model and a provider-specific sanitized error; raw reasoning and
provider error bodies are never persisted. The existing result fields remain intact.

Offline unit tests without reading the real datasets:

```powershell
python -m pytest -q tests/test_app.py tests/test_models.py tests/test_openrouter.py tests/test_batch.py tests/test_ollama.py
```

Both `parse-ticket` and `parse-all` accept `--prompt-version v1|v2` (default `v1`).
Each version loads `prompts/<version>.txt` first, falling back to
`docs/prompts/<version>.txt`. Prompt contents are used unchanged; missing or empty
files still fail rather than falling back to another version.

## Offline evaluation

Evaluate the existing OpenRouter and Ollama baselines without contacting either provider:

```powershell
python -m ai_project eval --predictions results/openrouter_v1.json --golden data/golden_set.json --output results/openrouter_v1_eval.md
python -m ai_project eval --predictions results/ollama_qwen3_8b_v1.json --golden data/golden_set.json --output results/ollama_qwen3_8b_v1_eval.md
```

Omit `--output` for a console summary only. Use a new `.json` output path for a
machine-readable report, or `.md` for a human-readable Markdown report. Both print
the same concise console summary. Add `--overwrite` to replace an existing report.
Predictions and golden data cannot be used as output destinations, even with `--overwrite`.
JSON reports preserve available run and per-record provider/model/prompt/sampling metadata.
The eval command does not load provider settings, read `.env`, or make API calls.

To score only the development examples:

```powershell
python -m ai_project eval --predictions results/openrouter_v1.json --golden data/golden_set.json --ids-file data/development_ids.json
```

`--ids-file` must contain a nonempty JSON array of unique integers; booleans,
strings, fractional values, duplicates, and IDs absent from the golden set are
rejected. Field accuracy, mismatches, and missing-golden diagnostics use only the
selected golden IDs. **Valid-output rate and latency still cover the entire
prediction batch.** Filtered JSON, Markdown, and console reports state this scope
and list the selected IDs. The full golden file is still schema-validated.
The IDs file is also protected from being overwritten by report output.
Omitting `--ids-file` preserves evaluation against all golden examples. Reserve
holdout examples for final evaluation, not prompt optimization.

Records match by integer `ticket_id` to golden `id`, independently of list order.
Each of the seven scored fields uses **all golden records** (or the selected
records with `--ids-file`) as its denominator:
category, priority, application, language, requires_support, details.error_code,
and details.error_message. Missing, failed, schema-invalid, and duplicate-ID
predictions count as incorrect in every field. Duplicate golden IDs and malformed
golden outputs are rejected; duplicate prediction IDs are reported and never
arbitrarily resolved. Extra prediction IDs do not enter field accuracy.

Enums and booleans compare exactly. Nullable text (application and both details
fields) uses Python `strip().casefold()` to ignore surrounding whitespace and case,
including Unicode case folding. Null remains distinct from an empty string.
Punctuation, quotes, and internal whitespace are preserved. Detailed mismatches
retain the original values. Markdown escapes table delimiters, HTML characters,
backticks, and backslashes; JSON quotes distinguish empty strings from null, and
missing/unusable predictions have an explicit marker.

Valid-output rate covers the entire batch, including non-golden tickets: successful
outputs must validate against `HRSupportTicket` and have an integer ticket ID.
The denominator is `max(total_tickets, len(results))`, so declared but absent
entries count as invalid and extra entries cannot disappear from the denominator.
Duplicate entries remain individual input predictions for schema validity, but are
unusable for golden matching. Failed, missing, and invalid outputs are invalid.
Count inconsistencies, malformed entries, missing IDs, incomplete batches, and
invalid timings appear in report issues. Malformed top-level structures/counts
are rejected. An empty validity denominator yields null/N/A.

Latency uses all success-status predictions with finite, nonnegative numeric
`elapsed_seconds`, even if schema validation fails. Booleans and numeric strings
are excluded. Percentiles use linear interpolation (type 7): sort the n samples,
locate `(n - 1) * p`, then interpolate between neighboring samples for p=0.50/0.95.
One sample returns itself; no samples yields null. Failures are excluded from latency.

`summary` and `suggested_actions` are excluded from automated exact-match accuracy:
equivalent summaries can use different wording, and several action selections,
orders, and phrasings can be appropriate. They still participate in schema validation.
No LLM judge is used. Run all offline tests with `python -m pytest`.

## Offline multi-run comparison and cost estimates

Compare saved runs using the same golden set, without reading `.env` or contacting
OpenRouter or Ollama:

```powershell
python -m ai_project compare --predictions results/openrouter_v1.json results/ollama_qwen3_8b_v1.json --golden data/golden_set.json --output results/comparison.md
```

The output must be a new `.md` file. Existing files are protected; choose a new
filename for another comparison. Predictions, tickets, golden labels, and prompts
are never updated. The table includes run metadata, golden document count, input
record count, aggregate and field-level accuracy, valid-output rate, and latency
p50/p95. Accuracy and latency reuse the offline evaluator described above.

Hosted token costs require an explicit model-keyed `--pricing` JSON file. Each key
must match `metadata.configured_model`. For example, a **hypothetical illustration,
not current provider prices**, saved as `pricing.example.json`:

```json
{
  "your-configured-model-id": {
    "input_usd_per_million": 2.0,
    "output_usd_per_million": 4.0
  }
}
```

Supply rates you have chosen for the recorded model and run; no prices are fetched
or assumed. Both prices must be finite nonnegative numbers. Explicit zero is
allowed. The report prints the configured rates for review.

```powershell
python -m ai_project compare --predictions results/openrouter_v1.json results/ollama_qwen3_8b_v1.json --golden data/golden_set.json --pricing pricing.example.json --power-watts 200 --electricity-usd-per-kwh 0.25 --output results/comparison_with_costs.md
```

The power and electricity values above are also illustrative. Local options apply
to every Ollama run in that comparison; compare separately if machines or tariffs
differ. The report shows Ollama API fee as $0, independently of whether electricity
can be estimated. Local inference still has energy, hardware, and operating costs.

Hosted USD per 1,000 attempted documents is:
`(sum(prompt_tokens) * input_price + sum(completion_tokens) * output_price) / 1_000_000 * 1_000 / record_count`.
Usage comes from each saved record's `usage.prompt_tokens` and
`usage.completion_tokens`, including failed records. Missing prices, missing or
invalid usage (even for one failure), or an incomplete/empty/count-inconsistent
batch yield N/A, never an assumed zero. Prices apply to the configured model;
recorded response model names are listed to expose aliases or routing differences.
These are **estimated token-based costs, not actual billed charges**. Unrecorded
retries, caching, discounts, routing fees, taxes, and billing adjustments are not
accounted for. Failed requests can incur charges not present in saved usage.

Local estimated electricity USD per 1,000 attempted documents is:
`power_watts / 1_000 * sum(elapsed_seconds) / 3_600 * electricity_usd_per_kwh * 1_000 / record_count`.
It uses all measured record times, including failures. Missing power, tariff, or
any timing yields N/A; incomplete/empty/count-inconsistent batches also yield N/A.
Power and tariff must be finite nonnegative numbers. Summing record times assumes
sequential processing and approximates active processing energy; it is not a
measurement of electricity use. It excludes idle time outside the records,
hardware amortization, and other operating costs. Latency retains the evaluator's
success-only sampling, whereas costs include all recorded attempts. Different
hardware, system load, model routing, and missing metadata limit comparisons.

## Evaluation Results

See the [Evaluation Report](docs/evaluation_report.md) for the
comparison of Prompt v1 and v2 across Gemini and Qwen3 8B.

## Homework 2: document extraction

Extract the raw HR corpus locally with
`python -m ai_project extract-corpus --output data/extracted/run-01`.
The output directory must be new. See [extraction documentation](docs/EXTRACTION.md)
for the schema, dependencies, validation, and known format limitations.

Task 2 adds local sanitization and exact deduplication:
`python -m ai_project ingest-corpus --output data/sanitized`.
For existing extraction JSON, use
`python -m ai_project sanitize-corpus --input data/extracted --output data/sanitized-from-extracted`.
See [sanitization documentation](docs/SANITIZATION.md) for configuration, access
boundaries, duplicate policy and detection limitations.

## Homework 2 Task 3: section-aware chunking

`ingest-corpus` now runs extraction → sanitization → exact deduplication → chunking.
It chunks only canonical sanitized semantic blocks, retaining historical versions
and existing access metadata. Run locally, with a **new** output directory:

```powershell
python -m ai_project ingest-corpus --output data/chunked/task3-run04 --target-tokens 400 --max-tokens 600
```

The same chunking options work with `sanitize-corpus --input data/extracted`.
Outputs include `chunks.jsonl`, `chunking_manifest.json`, `chunking_comparison.json`,
and the existing `report.json` with an embedded chunking manifest. Source documents
and sanitized duplicate audit files retain their existing formats.

Chunks stay within the extraction's heading hierarchy. Whole paragraphs, consecutive
list items (including numbered procedures), and tables are packed toward 400 tokens
without exceeding 600. A fitting list or table stays whole even if it passes the
target. Oversized lists split between items; oversized tables split between rows
and repeat the first row as column headers. Oversized prose prefers line/paragraph,
then sentence boundaries, falling back to token boundaries. There is no overlap
between chunks apart from repeated table headers and markers on continued items.

The shared, dependency-free counter is `unicode-word-or-punctuation-v1`: Python
Unicode regex `\w+|[^\w\s]` counts each word/number run and each punctuation character;
whitespace costs zero. Counts include rendered list markers, headings and table
cells. These are reproducible lexical token counts, **not model tokenizer counts**;
400/600 therefore do not guarantee an embedding model's token limit. The baseline
uses hard 400-token windows of exactly the same rendered sanitized semantic stream,
without section awareness, overlap or injected context.

Observed comparison from `data/chunked/task3-run02/chunking_comparison.json`:

| Document | Semantic tokens | Section-aware chunks | Fixed 400 chunks | Concrete first baseline boundary |
| --- | ---: | ---: | ---: | --- |
| M11 — Manager Approval Dashboard | 484 | 6 | 2 | `routes the matter` / `to HR Payroll.` |
| C02 — Part-Time Employment Contract B | 621 | 7 | 2 | `Sick Pay & Absence` / `Policy apply to requests` |
| S03 — Authentication Troubleshooting | 423 | 5 | 2 | `or recovery` / `secret. Support Escalation` |

Section-aware chunking keeps each quoted sentence within its section: respectively
95 tokens for “Concurrency and confidentiality”, 100 for “Taking leave and reporting
sickness”, and 102 for “Escalation and disabled accounts”. M11's five-step procedure
stays together (78 tokens); C02's ten-row table stays together (66 tokens). S03's
four diagnostic steps and five-row error table also each stay whole. The JSON report
records the actual boundary excerpts, section paths, block indices and protected
structure chunk IDs for inspection.

We choose section boundaries to keep policy rules and procedures attributable to
their own topics. The 400-token target with 600-token slack permits larger intact
procedures without forcing unrelated sections together. These documents have short
sections: the observed maximum is only 188 tokens, and standalone parent headings
can yield tiny chunks (minimum 2). The full corpus produces **184 chunks from 32
documents**, versus 52 fixed-size chunks; this is an intentional fragmentation
tradeoff, not evidence of better retrieval accuracy. Retrieval/embedding evaluation
is deferred; the present corpus does not empirically establish an optimal size.

Both full runs (`data/chunked/task3-run02` and `task3-run03`) produced byte-identical
artifacts and IDs. No documents were withheld and no exact duplicates were found
in this corpus. Historical documents M06, F03 and F05 remain in the chunks. All
semantic content is preserved; non-semantic furniture is excluded. Tests exercise
actual duplicate exclusion separately, explicit non-semantic flags, long lists and
tables, oversized individual blocks, token limits, page metadata and stable IDs.

Each chunk carries the source path, title, section path, version, effective date,
complete original metadata, zero-based extraction block indices, locations and
available page numbers. `source_hash` is SHA-256 of original bytes; `content_hash`
is SHA-256 of normalized semantic content **before redaction**. Neither is a hash
of the sanitized chunk. Chunk IDs use document ID plus SHA-256 of algorithm/counter
versions, size settings, both document hashes, metadata, section, ordinal, block
indices and chunk text. Output paths and run times do not enter IDs.

See [chunking details](docs/CHUNKING.md) for splitting edge cases and verification.

## Homework 2 Task 4: local indexing and search

Build the canonical chunks with local Ollama embeddings and persistent Qdrant:

```powershell
python -m ai_project index-corpus --input data/chunked/task3-run02/chunks.jsonl --index data/index/peopleflow --embedding-model bge-m3
$question = 'До якого числа треба використати перенесену відпустку за контрактом A?'
python -m ai_project search $question
python -m ai_project search $question --hr-access
```

The input path above is the documented default. Embeddings include title, section
path and text; search uses the saved model and cosine similarity, returning five
results by default. Access filtering happens before ranking. Default access allows
only `all_employees`; `--hr-access` explicitly includes `hr_confidential` for local
testing. Successful rebuilds replace the old collection and remove stale chunks.
See [retrieval commands and verification](docs/RETRIEVAL.md) for setup, validation,
metadata, access options and the observed corpus smoke test.

## Homework 2 Task 5: provisional retrieval evaluation

Review the 12 English/Ukrainian draft questions, expected chunk IDs and source
excerpts in [evals/retrieval_cases.json](evals/retrieval_cases.json), then run:

```powershell
python -m ai_project eval-retrieval --cases evals/retrieval_cases.json --index data/index/peopleflow --output results/retrieval_vector_baseline.json
```

This evaluates the existing vector search at k=5, validates expected chunks
against the current indexed corpus and case access groups, and reports mean
Recall@5 and MRR@5. The employee-only Contract A access check is reported
separately. The saved baseline is provisional until the draft labels are reviewed.
See [retrieval evaluation](docs/RETRIEVAL_EVALUATION.md) for exact metric definitions,
source/version distinctions, results and offline tests.

## Homework 2 Task 6: hybrid retrieval

Vector search remains the default. Hybrid combines up to 20 access-filtered
vector candidates and 20 BM25 candidates with equal-weight RRF (`k=60`):

```powershell
python -m ai_project search "ATT-LOCK v2.0" --mode hybrid
python -m ai_project eval-retrieval --mode vector --output results/retrieval_vector_baseline.json
python -m ai_project eval-retrieval --mode hybrid --output results/retrieval_hybrid.json
```

BM25 uses the active index's canonical chunks and indexes title, section and text.
Unicode tokenization preserves English/Ukrainian words, `ATT-LOCK` and `v1.8`.
Both modes run the same relevance cases and separate ACL01 check. See
[retrieval comparison](docs/RETRIEVAL_EVALUATION.md) for exact commands, scores,
per-case improvements/regressions and limitations. Task 7 adds reranking below.

## Homework 2 Task 7: optional local reranking

`--mode hybrid-rerank` scores the complete access-filtered RRF candidate union
using a local Sentence Transformers CrossEncoder before selecting the top five.
The default is `BAAI/bge-reranker-v2-m3`; ties retain RRF order. Install only when
needed, prepare the model once, then run the evaluation:

```powershell
python -m venv .venv-rerank --system-site-packages
.venv-rerank/Scripts/python -m pip install -e ".[rerank]"
.venv-rerank/Scripts/python -c "from ai_project.reranking import CrossEncoderReranker; CrossEncoderReranker(local_files_only=False)"
.venv-rerank/Scripts/python -m ai_project eval-retrieval --mode hybrid-rerank --output results/retrieval_hybrid_rerank.json
```

Vector and hybrid need no reranker dependencies. The reviewed suite is shared by
all three modes; reports include median query time and expected-chunk candidate
coverage. See [setup and three-way comparison](docs/RETRIEVAL_EVALUATION.md).

## Homework 2 Task 8: grounded answers with citations

```powershell
python -m ai_project ask "How do I correct attendance in PeopleFlow v2.0?"
python -m ai_project ask "How do I correct attendance in PeopleFlow v2.0?" --mode hybrid --context-token-budget 3200 --output results/my_answer.json
```

`ask` defaults to hybrid-rerank, top five, and local Ollama `qwen3:8b`.
The default mode needs the Task 7 reranker environment and cached model above.
Use `--mode vector|hybrid|hybrid-rerank` to override retrieval. Only whole
authorized chunks enter the budgeted context. Structured answers require citations
on every claim, and citation labels use actual source metadata. See
[RAG behavior, budgeting and exact local smoke commands](docs/RAG.md).

## Homework 2 Task 9A: provisional RAG answer baseline

The [draft 20-case suite](evals/rag_cases.json) labels required facts,
qualifications, acceptable source chunks and answer statuses before generation.
It covers English/Ukrainian questions, partial and unavailable answers, similar
contracts and historical-version traps. Review the
[question/fact/source sheet](results/rag_case_review.md), then inspect the
[baseline report](results/rag_baseline.md).

```powershell
.venv-rerank/Scripts/python.exe -m ai_project eval-rag --output results/rag_baseline_reproduced.json
```

The local run uses `rag-v1`, `qwen3:8b`, hybrid-rerank/top five and the existing
`ask` components. Status, citation membership, lexical fact signals and expected
sources are reported separately; errors remain distinct from unavailable answers.
Labels and results remain provisional pending review. See
[exact commands, scoring limits and offline tests](docs/RAG_EVALUATION.md).
