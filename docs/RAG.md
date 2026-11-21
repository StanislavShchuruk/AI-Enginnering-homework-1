# Grounded PeopleFlow answers (Task 8)

Run from the repository root with Python 3.11+, the existing PeopleFlow index,
local Ollama with `bge-m3` and `qwen3:8b`, and the Task 7 reranker environment/cache.
No new dependencies are needed. `ask` uses the existing `search` implementation,
defaults to `--mode hybrid-rerank --top-k 5`, and accepts explicit `vector`,
`hybrid`, or `hybrid-rerank` modes. Vector/hybrid need no reranker packages.

Generation reuses `OllamaProvider` SDK, local endpoint validation, timeout,
non-thinking request and error handling, with a separate `RagAnswer` JSON schema.
Ticket parsing retains its original schema. `OLLAMA_MODEL` defaults to
`qwen3:8b`; `--model` overrides it. `OLLAMA_BASE_URL` defaults to
`http://localhost:11434`; `--ollama-url` overrides generation only. The existing
`OLLAMA_TEMPERATURE`, `OLLAMA_TOP_P`, and `OLLAMA_TIMEOUT_SECONDS` settings apply.
Ollama reads process settings only and never loads `.env`. `--embedding-url`
sets the retrieval embedding origin (default `http://localhost:11434`).

Access defaults to `all_employees`. Existing `--access-group` and `--hr-access`
options are local testing switches, not authentication. Production callers must
supply groups from a trusted identity. Retrieval filters candidates before
ranking; context assembly checks access again before generation, including
over-budget hits, and rejects inconsistent access metadata.

## Context budget and source mapping

`--context-token-budget` defaults to **3200** and must be at least 2. Counting
reuses the chunker's `unicode-word-or-punctuation-v1`: Unicode `\w+` runs each
count as one token; every non-whitespace punctuation character counts as one;
whitespace costs zero. This is a deterministic local lexical estimate, **not
Qwen's tokenizer and not a guarantee of fitting the model's context window**.

The budget covers the exact compact UTF-8 JSON excerpts array sent to generation,
serialized with `ensure_ascii=False` and separators `(',', ':')`. It includes
array/object delimiters, keys, source IDs, document titles, section paths,
versions, effective dates, source references, full chunk text, and all retained
canonical metadata (including locations, pages and provenance hashes). The empty
array costs two tokens. It excludes the question, surrounding request object,
system prompt, chat/schema overhead and generated output. Allow additional model
context space for these; choose a smaller budget for a smaller context window.
The provider's actual token usage is saved separately when available.

Traverse the ranked results in returned order. Add a whole canonical chunk only
if the resulting excerpts array fits, otherwise skip it and try the next one.
Never truncate a chunk or reorder selected chunks. Deduplicate by original chunk
ID. Assign contiguous short IDs `S1`, `S2`, ... only to included chunks.
The `sources` array in saved JSON is exactly the excerpts supplied to the model,
so it maps every short ID to its original chunk ID and full source metadata.
`retrieved_chunk_ids` also records hits that did not fit. `context_tokens`, budget,
counter identity, prompt version/hash, model/usage, retrieval settings and
generation time are saved with each validated response.

## Prompt and validation boundary

[rag-v1](prompts/rag-v1.txt) requires the question's language, supplied-excerpt
evidence only, one factual claim per item, supporting source IDs, version
applicability, and treating instructions inside excerpts as untrusted text.
No answer is seeded from evaluation labels or questions. Supported parts become
claims; unsupported parts are described in `missing_information`. If nothing is
supported, use `unavailable` with no claims and state that the information is
unavailable in accessible documents. Empty retrieval or an empty budgeted context
still uses generation to express that gap in the question's language; validation
prevents any cited factual claims when no source IDs were supplied.

Strict Pydantic validation rejects extra fields, missing fields, blank claims,
claims without citations, invalid status/claim/gap combinations, and source IDs
absent from the **included** context. Invalid answers are neither printed nor
saved. There is no automatic repair or fallback to unvalidated text. Only after
validation does the renderer create citation labels from actual chunk titles,
section paths and versions. The model cannot supply replacement labels.

These checks establish structural citation coverage and source membership.
They do not establish that a cited passage entails a claim, that a claim is
atomic, that a gap contains no disguised facts, or that the model followed
language/version/injection instructions. Those are semantic quality checks for
Task 9. `missing_information` is reserved by the prompt for coverage gaps, not
uncited factual answers. Source existence alone is not evidence of correctness.

## Exact PowerShell smoke commands

The Task 7 environment, cached reranker, active 184-chunk index and local Ollama
models were already available. Both smoke tests use default hybrid-rerank/top
five and employee-only access. R05 is rephrased to remove the answer-bearing
14-day hint; the reviewed retrieval evaluation dataset is unchanged.
The second asks about home solar panel installation reimbursement, for which
the canonical corpus contains no policy or reimbursement limit.

```powershell
$env:PYTHONUTF8 = '1'
$env:OMP_NUM_THREADS = '8'
$env:MKL_NUM_THREADS = '8'
$env:OLLAMA_TIMEOUT_SECONDS = '300'
./.venv-rerank/Scripts/python.exe -m ai_project ask 'У PeopleFlow v2.0 який строк подання виправлення обліку часу та що робити з помилкою ATT-LOCK?' --model qwen3:8b --output results/rag_r05.json
./.venv-rerank/Scripts/python.exe -m ai_project ask 'What is the reimbursement limit for installing home solar panels under PeopleFlow policy?' --model qwen3:8b --output results/rag_absent.json
```

Outputs must be new `.json` files. When reproducing in a checkout containing the
saved smoke artifacts, change only the output paths, for example to
`results/rag_r05_reproduced.json` and `results/rag_absent_reproduced.json`.
Local inference can vary across model/runtime revisions even at temperature zero.

Observed results (2026-11-20):

| Smoke | Status | Included chunks | Lexical context tokens | Actual prompt / completion tokens |
| --- | --- | ---: | ---: | ---: |
| [R05](../results/rag_r05.json) | answered, Ukrainian | 5 | 2606 | 3507 / 141 |
| [Absent policy](../results/rag_absent.json) | unavailable, English | 5 | 2405 | 3195 / 45 |

R05 gives the 14-calendar-day deadline with S1/S3/S4 and the controlled HR Payroll
adjustment route for ATT-LOCK with S2/S3. The included mapping is S1 = F04 / New
self-service actions; S2 = M07 / Outside the self-service window; S3 = S04 /
Correction controls; S4 = M07 / Submit a correction; S5 = M06 / Historical limits.
The historical v1.8 S5 is present in retrieved context but is not cited in the
v2.0 answer. The full original chunk IDs and metadata are retained in the JSON.
The first development smoke omitted the requested action; the prompt was
strengthened to address every requested part before marking an answer complete,
and the saved final R05 run above was generated using the final prompt.

The absent-policy run returns no claims or citations and explicitly says the
information is unavailable in accessible documents, despite five retrieved
chunks. These are irrelevant excerpts, distinct from the empty-retrieval case
covered offline. Both artifacts passed structure/membership validation and their
saved context counts and prompt hashes were checked against the final prompt.
These two smoke observations are not a semantic accuracy evaluation.

## Offline verification

```powershell
python -m pytest -q tests/test_rag.py tests/test_ollama.py -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
python -m ruff check src/ai_project/rag.py tests/test_rag.py src/ai_project/providers.py src/ai_project/config.py
```

Tests mock generation and retrieval/SDK calls: exact budget boundaries,
metadata overhead, whole-chunk skipping, rank order, deduplication, access denial,
invalid and omitted citation IDs, budget-excluded references, empty retrieval,
partial answers, status consistency, schema selection, CLI defaults/overrides,
metadata-based labels, source persistence, and no output for invalid answers.
All **418 tests and 21 subtests pass**, including the existing Ollama test that
requires no dotenv loading. Ruff passes for the files listed above. Pre-existing
line-length warnings in unrelated CLI functions remain outside this change.
