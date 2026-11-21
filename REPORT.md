# PeopleFlow RAG final report

The [README](README.md) provides setup and the
one-command live pipeline, offline replay and optional hosted judge commands.

## Corpus, ingestion and chunking

The [manifest](data/manifest.json) and [corpus validation](data/corpus_validation.json)
describe 32 fictional English HR documents: 12 manuals, eight contracts/policies,
six support documents and six FAQs/versioned guides/release notes. Formats are
11 HTML, ten PDF, four DOCX and seven Markdown. There are 29 active and three
superseded documents (M06, F03, F05); historical versions remain searchable.
Questions include English and Ukrainian and carry explicit access allowlists.

The offline replay rebuilds ingestion from the tracked raw files using the existing
extractors, sanitization, exact deduplication and section chunker. It reproduces
the saved canonical SHA-256
`429649032efba26439e267c7da639daf1ef1dd29491d84224a8e0c1e9bdb15f7`.
The existing `data/chunked/task3-run02/report.json` records 32 sanitized/included
documents, zero duplicates, zero withheld documents, no errors and 42 redactions:
17 person names, six employee IDs, four emails, four medical spans, three each
addresses/bank accounts/phones and two routing identifiers. These detector counts
are not a general privacy guarantee. Extraction preserves ordered sections, lists,
tables, PDF page references, versions and access metadata. Details:
[extraction](docs/EXTRACTION.md), [sanitization](docs/SANITIZATION.md).

The regenerated corpus has **184 chunks**, 13,599 semantic lexical tokens, chunk
sizes 2–188 and 59 chunks with page numbers. The 400-token target/600 maximum
counts Unicode words and punctuation, not model tokens. Section boundaries keep
procedures and policy qualifications attributable to their source topic; intact
lists/tables stay together, oversized tables repeat headers, and no generic overlap
is added. Tiny parent-heading chunks are a fragmentation cost.

The saved three-document comparison is retained by ingestion and documented in
[chunking details](docs/CHUNKING.md) and the README:

| Document | Semantic tokens | Section-aware chunks | Fixed 400-token chunks |
| --- | ---: | ---: | ---: |
| M11 Manager Approval Dashboard | 484 | 6 | 2 |
| C02 Part-Time Employment Contract B | 621 | 7 | 2 |
| S03 Authentication Troubleshooting | 423 | 5 | 2 |

Fixed windows split M11's escalation sentence, C02's leave/sickness wording and
S03's recovery/escalation text. Section chunking preserves those sentences and
the associated procedures/tables. Across all documents it yields 184 chunks
versus 52 fixed windows. This motivates attribution and structure preservation;
there is no retrieval A/B experiment proving this chunk size optimal. Generated
ingestion trees and local indexes remain ignored and are reproducible from raw
sources; the saved comparison and counts can be regenerated with `ingest-corpus`.

## Retrieval quality and latency

The three [saved retrieval reports](results/retrieval_vector_baseline.json) share
the reviewed 12-case labels, canonical source hash, bge-m3 embeddings, 1024 vector
dimensions, 184 chunks and top-k five. Separate reports contain
[hybrid](results/retrieval_hybrid.json) and
[hybrid + reranking](results/retrieval_hybrid_rerank.json).

| Metric | Vector | Hybrid | Hybrid + reranking |
| --- | ---: | ---: | ---: |
| Mean Recall@5 | 0.805556 | 0.847222 | 1.000000 |
| MRR@5 | 0.777778 | 0.756944 | 0.916667 |
| Complete misses | 2/12 | 1/12 | 0/12 |
| Median retrieval latency | 2.096 s | 2.116 s | 8.251 s |
| ACL01 | PASS | PASS | PASS |
| Confidential final hits | 0/5 | 0/5 | 0/5 |
| Unauthorized candidate-pool chunks | 0 | 0 | 0 |

Recall averages each case's fraction of expected chunks retrieved; MRR averages
the reciprocal rank of its first relevant chunk. ACL01 is excluded from the 12
relevance cases. Timing includes query embedding/search and, where selected,
BM25/fusion/pair scoring; it excludes evaluator setup and reranker initialization
(6.933 s from cache). These are single local CPU runs, not a controlled benchmark.

Hybrid fuses up to 20 vector and 20 Unicode BM25 candidates with equal-weight
RRF, k=60. It recovers R06 but reduces R01 recall and R08 reciprocal rank;
recall improves while MRR declines. The BAAI/bge-reranker-v2-m3 CrossEncoder scores
the full authorized union before top-five selection. Every labeled expected chunk
was already in that pool; reranking resolves ranking failures, at about **3.9×**
hybrid's median latency. Perfect recall on 12 reviewed questions does not establish
general retrieval quality. Both branches filter access before candidate selection;
the reranker checks access again. See [retrieval evaluation](docs/RETRIEVAL_EVALUATION.md)
for per-case rankings, model revision, timing boundaries and ACL evidence.

## Generation, deterministic scores and human calibration

The [20-case baseline](results/rag_baseline.json) uses local Ollama qwen3:8b,
temperature 0/top-p 1, `rag-v1`, hybrid + reranking/top five and whole-chunk
context budget 3200. Labels remain **draft**; ten saved answers have separate
[human completeness/faithfulness reviews](evals/rag_human_labels.csv).
The live evaluator retains raw responses and exact generator excerpts.

The offline replay recomputes these signals with current scorers and current labels:

| Deterministic signal | Result | Interpretation |
| --- | --- | --- |
| Valid structured responses | 19/20 | R09 fails response schema validation |
| Expected status matches | 16/20 | R06, R09, P02, N03 fail; invalid R09 stays in denominator |
| Citation membership | 19/19 schema-valid answers | All cited IDs exist in supplied contexts |
| Lexical key-fact matches | 12/17 regex facts | Paraphrases/negation/qualifications need review |
| Expected sources on matched lexical facts | 11/12 | P02 cites a historical source for its duration claim |
| Semantic-only facts | 13 unscored | No deterministic semantic pass is claimed |

The older baseline Markdown shows 16/19 among valid responses; the CI gate uses
the required **16/20** denominator. Citation membership establishes reference
integrity, not entailment, correct version or completeness. No-claim unavailable
answers have zero citation obligations. R09 is an error, not an unavailable answer.

The saved [hosted judge run](results/rag_judge.json) uses
`google/gemini-3.1-flash-lite`, `rag-judge-v1` and exact saved generator contexts.
It judges 19 answers with zero judge errors and excludes R09 from semantic scoring.
Its semantic verdicts are completeness **18 pass / one fail**, and faithfulness
**16 pass / one fail / two n/a**. These are model assessments, not human agreement.

On the ten human-reviewed answers, exact completeness agreement is **7/10 (70%)**;
faithfulness agreement is **8/9 (88.9%)**, excluding N01's human n/a. Completeness
disagreements are R06, R07 and P02; faithfulness disagreement is P02. Human scores
and reasons were excluded from judge requests and joined afterward. Input hashes,
requests, raw verdicts, per-claim reasons and usage are saved. Ten reviewed examples
are too few for strong calibration claims. See [judge documentation](docs/RAG_JUDGE.md)
and [disagreement report](results/rag_judge.md).

## Concrete cases: expectations, observations and causes

| Case | Expected behavior | Observed behavior | Cause supported by saved evidence |
| --- | --- | --- | --- |
| R04: historical attendance correction | Explain v1.8 manager adjustment and employee check after the five-minute cycle | Vector and hybrid miss; reranking retrieves M06 at rank 2. Generation gives both steps, cites S2; human and judge pass | M06 was candidate rank 6 before reranking: candidate generation succeeded, top-five ranking failed |
| R05: v2.0 correction qualifications | State the 14-calendar-day submission window, relevant boundary/conditions and unlocked-period requirement; route locked periods to Payroll | Reranking improves retrieval recall from 2/3 to 3/3. Answer states 14 days and ATT-LOCK routing, but does not explicitly explain all qualifications. Two regex facts are unmatched; human and judge nevertheless pass | Evidence is available; generation compresses conditions. Lexical matching and reviewer judgments capture different requirements; missing lexical matches alone cannot establish semantic failure |
| N03: unavailable v3.0 procedure | Return unavailable because the corpus covers v1.8/v2.0, not v3.0 | Answer says partial and asserts a v3.0 14-day rule from S1, while also saying v3.0 data is absent. Citation membership passes; human and judge fail both dimensions | A valid citation points to the wrong version: generation transfers a v2.0 rule into unsupported v3.0 wording |
| P02: lockout plus absent vendor phone | Return partial, explain 30-minute lockout using current evidence, identify unavailable phone | Returns answered, cites historical S1 for duration although current S5 is present; human fails both dimensions, judge passes both | Generation mishandles partial status and source/version choice. Judge rationale refers to S5's support even though duration claim cites only S1, showing incomplete enforcement of claim-specific citation grounding |

R06 additionally returns partial despite itself listing the supposedly missing
balance-verification step; R07 omits a replacement-request step. The judge passes
both on completeness, explaining two more disagreements. These examples motivate
manual review and stricter semantic calibration beyond structural gates.

## Cost: hosted judge versus local RAG

The 19 recorded judge requests used **84,130 input tokens and 3,614 output tokens**
(87,744 total). [config/pricing.json](config/pricing.json) records $0.25 per million
input and $1.50 per million output tokens for this judge, matching Google's
[published Gemini 3.1 Flash-Lite rates](https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-1-flash-lite/)
(checked 2026-11-21). The token-rate estimate is:

`(84,130 × 0.25 + 3,614 × 1.50) / 1,000,000 = $0.0264535` for the saved run,
or **$1.3923 per 1,000 actually judged answers** at the same average token volume.
R09 has no judge call and is excluded from this normalization. This is an estimate,
not a provider invoice: routing fees, discounts, retries not retained in per-case
usage and billing adjustments are unavailable in the saved artifacts.

Local RAG uses local embedding, reranking and Ollama generation, with no hosted
inference charge. It still consumes hardware time and electricity. Although the
pricing configuration contains 500 W and $0.09557/kWh assumptions, measured power,
complete ingestion/indexing/retrieval/generation wall time, amortization and hardware
cost are unavailable for a defensible end-to-end cost per 1,000 local evaluations.
The hosted judge estimate must not be presented as local RAG cost.

## CI coverage, reproduction and publication

`.github/workflows/quality.yml` runs the full offline tests and `python -m ai_project
ci-rag` for PRs and pushes to `main` (current default branch). It installs the dev
extra without Sentence Transformers, requires no OpenRouter credentials or Ollama,
and disables Hugging Face/Transformers downloads. Replay rebuilds canonical chunks
from raw sources and validates test-set/corpus/prompt hashes, unique case membership,
exact saved request/source equality, canonical source metadata/text and ACLs. It
parses raw outputs and reuses `score_answer`/`summary`, ignoring saved scores.

The gates require at least **19/20** valid structures, **16/20** expected statuses
(invalid outputs are failures), and citation membership on every schema-valid
response. Output identifies counts, thresholds and failing cases. Missing/stale
artifacts fail with setup diagnostics and regeneration instructions. Offline
retrieval/access tests, including ACL01 and unauthorized reranker-pool rejection,
run in the full suite. Regression tests prove nonzero exits for schema/status/
citation regressions; they also cover stale artifacts and ignored cached scores.
These gates cannot detect changes in live embedding, retrieval or generation
quality; use `reproduce-rag` for fresh measurements and approved judging/manual
review for semantics.

Publication review: the tracked corpus is explicitly synthetic; reserved contacts,
masked banking examples and invented HR identities are documented in
[CORPUS_README](data/CORPUS_README.md). Saved RAG/judge artifacts contain these
synthetic excerpts, not production HR records. Only `.env.example` is tracked as
an environment file; `.env` and `.env.*` are ignored except that example. No real
secret file was read. A filename/content-pattern audit found no credential matches
in tracked publishable files. An unrelated tracked Office lock file was removed.
Generated indexes, model caches and run directories remain ignored. Explicit Git
line-ending rules preserve existing byte hashes on Windows and Linux checkouts.
Pattern scanning and fictional-data provenance are bounded checks, not a general
secret-detection guarantee.

Local verification (Python 3.14; CI is configured for Python 3.11):

- `python -m ai_project ci-rag`: exit 0; 19/20 structures, 16/20 statuses, 19/19 citation membership.
- `python -m pytest -q tests/test_rag_ci.py`: regression fixtures exercise exit 1;
  baseline replay passes. Full final test command below includes these tests.
- `python -m pytest -q -p no:cacheprovider`:
  **482 passed, 21 subtests passed**. Ollama settings already use process environment
  only; the strengthened dotenv test checks this behavior and passes.
- Ruff checks on the new modules/tests pass.

A temporary publishable-tree check reconstructed tracked files with Git's checkout
filters and overlaid the current changes, without ignored local artifacts.
`python -m ai_project ci-rag` passed there; `python -m pytest -q -p no:cacheprovider`
reported **480 passed, two skipped, 21 subtests passed**. The skipped tests require
optional saved local artifacts; offline corpus rebuilding and ACL tests still run.
A separate process running `python -m ai_project ci-rag --baseline
tmp/rag_ci_citation_regression.json` returned **exit 1** for an intentionally
unknown R01 citation (18/19 citation memberships passed); the tracked baseline
was unchanged. `git diff --check` passed.

Changed publishable files:

- Added `.github/workflows/quality.yml`, `.gitattributes`, `REPORT.md`,
  `src/ai_project/rag_ci.py`, `src/ai_project/rag_reproduction.py`,
  `tests/test_rag_ci.py`, and `tests/test_rag_reproduction.py`.
- Updated `.gitignore`, `README.md`, `src/ai_project/cli.py` and
  `tests/test_ollama.py`.
- Removed `data/documents/policies/~$C05.docx`, an Office lock artifact outside
  the manifest. No synthetic source document or saved baseline was changed.

GitHub Actions verified the offline test suite and RAG replay quality gates on `main`.
[Workflow run #3](https://github.com/StanislavShchuruk/AI-Enginnering-homework-1/actions/runs/44902413466) passed for commit `9e2752e` in 50 seconds. Local results
must be kept separate from hosted workflow status.
The live reproduce-rag command completed locally and reproduced the saved baseline metrics. Case R09 again failed response schema validation.

## Next improvements

Review the remaining generation labels/answers and expand version, qualification,
partial-status and access adversarial cases before claiming broader accuracy.
Calibrate the judge on disagreements with strict per-claim cited-source/version
checks; retain independent human labels. Improve generation's explicit conditions,
partial-answer status and abstention on unknown versions with a new versioned
prompt, then rerun live evaluation before replacing the fixture. Benchmark reranking
under repeated warm/cold runs and realistic concurrency, comparing smaller local
rerankers or candidate limits while measuring recall regressions. Explore merging
tiny heading chunks and compare against the fixed-size baseline with unchanged
reviewed labels. Record end-to-end time, energy and billing inputs to improve cost
estimates. Keep CI replay fast and offline, with live evaluations run separately.
