# PeopleFlow local indexing and vector search

Task 6 adds opt-in `search --mode hybrid` while retaining the vector default.
See [hybrid retrieval and evaluation](RETRIEVAL_EVALUATION.md) for BM25/RRF details,
the two-mode comparison and exact commands. The Task 4 smoke results below are
the historical vector-only run.

Task 4 reads the ingestion pipeline's canonical `chunks.jsonl` directly. It does
not re-extract, re-sanitize, re-chunk, or discard historical versions. Defaults are
`data/chunked/task3-run02/chunks.jsonl`, index directory `data/index/peopleflow`,
Ollama origin `http://localhost:11434`, embedding model `bge-m3`, batch size 16,
and search top-k 5. Paths are relative to the current working directory.

## Exact PowerShell commands

Run from the repository root, using Python 3.11+:

```powershell
python -m pip install -e ".[dev]"
# If Ollama is not already running, run this in another terminal:
ollama serve
# Download once if the embedding model is not installed:
ollama pull bge-m3

python -m ai_project index-corpus --input data/chunked/task3-run02/chunks.jsonl --index data/index/peopleflow --embedding-model bge-m3 --batch-size 16

$question = 'До якого числа треба використати перенесену відпустку за контрактом A?'
python -m ai_project search $question --index data/index/peopleflow
python -m ai_project search $question --index data/index/peopleflow --hr-access
```

The Task 3 canonical file is a generated, git-ignored artifact. If it is absent on
a fresh checkout, generate it first (ingestion requires a new output directory):

```powershell
python -m ai_project ingest-corpus --output data/chunked/task3-run02 --target-tokens 400 --max-tokens 600
```

All options above have the documented defaults, so `python -m ai_project
index-corpus` builds the same index. To use another ingestion run, supply its
explicit `--input` path. To change models, rebuild with `--embedding-model`;
search always uses the model recorded in the active index. Both commands accept
`--ollama-url http://127.0.0.1:11434`. Only HTTP loopback origins are accepted,
proxy settings are bypassed, and neither command loads `.env` or needs an API key.

For machine-checked counts and smoke-test output:

```powershell
$buildJson = python -m ai_project index-corpus --input data/chunked/task3-run02/chunks.jsonl --index data/index/peopleflow
if ($LASTEXITCODE -ne 0) { throw 'Index build failed' }
$build = ($buildJson -join "`n") | ConvertFrom-Json
$lineCount = (Get-Content -Encoding utf8 data/chunked/task3-run02/chunks.jsonl | Measure-Object -Line).Lines
if ($build.chunk_count -ne $lineCount) { throw 'JSONL/index count mismatch' }

$question = 'До якого числа треба використати перенесену відпустку за контрактом A?'
$publicJson = python -m ai_project search $question --index data/index/peopleflow
if ($LASTEXITCODE -ne 0) { throw 'Public query failed' }
$public = @(($publicJson -join "`n") | ConvertFrom-Json)
if (@($public | Where-Object access_group -eq 'hr_confidential').Count -ne 0) { throw 'HR data leaked' }
$public | Select-Object rank, score, document_id, section_path, access_group

$hrJson = python -m ai_project search $question --index data/index/peopleflow --hr-access
if ($LASTEXITCODE -ne 0) { throw 'HR query failed' }
$hr = @(($hrJson -join "`n") | ConvertFrom-Json)
$hr | Select-Object rank, score, document_id, section_path, access_group
$hr | Where-Object { $_.document_id -eq 'C01' -and $_.section_path -contains '4 Leave and sickness' } | Select-Object rank, score, chunk_id
```

## Validation, persistence and access

Before opening Qdrant or embedding anything, the entire JSONL file is validated
against the existing chunk schema with strict field types and no extra fields.
Blank/malformed records, duplicate IDs, IDs outside the canonical
`document_id-<64 lowercase hex characters>` format, empty text/title/source,
empty section labels and missing/unknown access groups fail the build. Validation
errors identify the line without echoing document content. IDs are checked for
format and uniqueness; their ingestion-time digest is not recomputed because the
JSONL alone does not contain all chunking configuration inputs.

Each embedding input is exactly the document title, a newline, the section path
joined with ` > `, two newlines, and the original chunk text. Requests use
Ollama's batched `/api/embed` with `truncate: false`, so oversized input fails
rather than silently losing content. Responses must contain one finite, nonzero
vector per input, with a consistent dimension across batches. See the
[Ollama endpoint specification](https://docs.ollama.com/api/embed).

Qdrant uses `QdrantClient(path=...)` local persistent mode and cosine similarity;
no Qdrant server or embedding integration is needed. See the
[Qdrant local-mode documentation](https://github.com/qdrant/qdrant-client#local-mode).
Point IDs are deterministic UUIDv5 values derived from chunk IDs. Payloads retain
all canonical fields, including original text, chunk ID, source reference, document
title, section path, version, effective date, metadata, locations, and pages.
`access_group` is also copied to a top-level field for Qdrant filtering.

A rebuild stages a new collection, checks its exact persisted count, writes its
metadata sidecar, then switches the `peopleflow` alias. Only after publication is
the previous collection deleted, including stale chunks. Repeated builds have
exactly one active point per input chunk. Ordinary failures before publication
delete staging data and preserve the previous active index. A process crash can
leave an inactive collection, but search only reads the active alias. Local
Qdrant locks the database directory; run build and search sequentially.

The active collection's JSON sidecar records embedding model, vector dimension,
input path, SHA-256 of the exact input file bytes, chunk count, embedding format
version and distance. Query vectors are checked against the recorded dimension.
Changing a local model under the same tag requires rebuilding the index.

Default access is **only `all_employees`**. Qdrant receives an allowlist payload
filter in `query_points`, before ranking and top-k selection. `--hr-access` adds
`hr_confidential` for the requested local smoke test. Other local group simulations
can use repeatable `--access-group managers_hr` or `--access-group hr_payroll`.
These flags simulate caller permissions locally; a future application must derive
groups from authenticated identity. Search returns JSON with rank, cosine score,
chunk ID, text, document title, section path and source reference, plus the
retained payload metadata. BM25, reranking, generation and retrieval evals remain
outside this task.

## Observed corpus smoke test (2026-11-19)

Built the current canonical corpus using installed `bge-m3:latest` through the
`bge-m3` tag and qdrant-client 1.20.0. The persisted index was closed and reopened
for the queries and independent count check:

- JSONL records: **184**; exact persisted Qdrant points: **184**; collections: **1**.
- Vector dimension: **1024**, cosine similarity.
- Input SHA-256: `429649032efba26439e267c7da639daf1ef1dd29491d84224a8e0c1e9bdb15f7`.
- HR query: **C01 → 4 Leave and sickness ranked 2**, score **0.616075**.
- Default query: **zero `hr_confidential` results**, all five are `all_employees`.

Both queries used exactly
`До якого числа треба використати перенесену відпустку за контрактом A?`
with the default top-k of 5.

| Rank | Default access: document / section | With HR access: document / section |
| ---: | --- | --- |
| 1 | F01 / Which annual leave balance applies? | F01 / Which annual leave balance applies? |
| 2 | C04 / Carry-over and scheduling | C01 / 4 Leave and sickness |
| 3 | C04 / Entitlement and scope | C02 / Taking leave and reporting sickness |
| 4 | M03 / Choose the correct balance | C04 / Carry-over and scheduling |
| 5 | C07 / Downstream controls | C04 / Entitlement and scope |

Scores, chunk IDs, source paths and access groups for both result lists are saved
in [results/retrieval_smoke.json](../results/retrieval_smoke.json). Full local CLI
payloads are in the git-ignored index directory as `public-smoke.json` and
`hr-smoke.json`. This is a smoke test, not a retrieval evaluation.

## Offline verification

```powershell
python -m pytest -q tests/test_retrieval.py --basetemp=.pytest_tmp_task4_verify
python -m pytest -q --basetemp=.pytest_tmp_task4_all
```

The tests mock embeddings and HTTP; they make no live API calls. Real persistent
Qdrant tests check reopen, repeat builds, stale removal, failed rebuild recovery,
and pre-ranking access filtering where the denied hit has the highest similarity.

Observed: **31 retrieval tests passed** and Ruff passed for the new module/tests.
The full suite run passed 334 tests and 21 subtests, with one existing failure in
`tests/test_ollama.py::test_defaults_do_not_load_secrets`: the existing
`Settings.ollama_from_env()` calls `load_dotenv`, while its test requires no call.
That settings method is outside this task; the new retrieval commands do not call
it.
