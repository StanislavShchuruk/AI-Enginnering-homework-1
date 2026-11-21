# PeopleFlow retrieval and local reranking evaluation (Tasks 5–7)

The evaluation calls `search` in vector, hybrid or hybrid-rerank mode at **k=5**,
with each case's exact allowed groups. Task 6 adds BM25 and rank fusion; Task 7
adds a local CrossEncoder over the full fused candidate pool. Answer generation
remains a follow-up task. The suite's existing `status` field now accepts `draft`
or `reviewed`. At the user's explicit Task 7 instruction it was set to `reviewed`
without changing questions, access groups, expected IDs or evidence. Reports from
reviewed suites have `status: evaluated` and `review_required: false`; draft
suites retain the earlier provisional behavior. The small case set still limits
the conclusions that can be drawn from these metrics.

## Draft labels

[evals/retrieval_cases.json](../evals/retrieval_cases.json) contains 12 answerable
relevance cases: six English and six Ukrainian questions across leave, payroll,
attendance, shifts and support. Expected IDs were selected from the current
index's canonical `data/chunked/task3-run02/chunks.jsonl` text before Task 5
search runs. R01 intentionally repeats the previously observed Task 4 Ukrainian
Contract A smoke case with HR access. Initial expected IDs were chosen without
using the Task 5 rankings. During user review, R01 was expanded to include the
Employee FAQ chunk after verifying that its carry-over explanation supports the
same 31 March deadline.
R05 was also expanded during user review to include the v2.0 release-notes
summary of the correction window and the route for locked payroll periods.
These label changes precede Task 7; no labels were tuned to reranker results.

Each case includes its ID, question, allowed access groups, topic, labeling note,
expected chunk IDs and one evidence entry per expected chunk. Each evidence entry
contains the exact chunk ID, document title, section path, version and a verbatim
excerpt. Review those entries against the canonical file before treating the
labels as authoritative.

| Case | Language | Topic and source-specific target | Expected chunks |
| --- | --- | --- | ---: |
| R01 | Ukrainian | Contract A / 4 Leave and sickness + Employee FAQ / Which annual leave balance applies?: carry-over deadline | 2 |
| R02 | English | Contract B / Taking leave and reporting sickness: medical evidence threshold | 1 |
| R03 | Ukrainian | Annual Leave Policy / Carry-over and scheduling: consumption order | 1 |
| R04 | English | Attendance Correction Guide v1 / Manager-mediated correction: historical v1.8 | 1 |
| R05 | Ukrainian | Attendance Correction Guide v2 / Submit a correction + Outside the self-service window; Release Notes v2.0 / New self-service actions | 3 |
| R06 | English | Leave Request Guide v1 / Historical cancellation procedure | 1 |
| R07 | Ukrainian | Leave Request Guide v2 / Cancel before leave starts | 1 |
| R08 | English | Shift Schedule & Swap Guide / Propose an employee swap + Eligibility controls | 2 |
| R09 | Ukrainian | Payslip & Payroll Portal Guide / Gross pay and net pay: Submitted and settlement delay | 1 |
| R10 | English | Payroll Troubleshooting / Missing allowance procedure: cutoff handling | 1 |
| R11 | Ukrainian | Support Priority & SLA Policy / Clock examples: Friday Medium-ticket deadline | 1 |
| R12 | English | Authentication Troubleshooting / MFA and lockout: failed-attempt thresholds | 1 |

These are **exact chunk labels**, not document-level relevance labels. An adjacent
section from the correct document does not count. R01 accepts the contract and
the FAQ as relevant sources for its deadline; R02 requires the named Contract B.
Historical and current guide cases deliberately distinguish v1.8 and v2.0.
R05 includes the two detailed guide chunks and the relevant release-notes summary;
only the guide explicitly names ATT-LOCK. All three count toward its recall
denominator. R08 requires two chunks to support all parts of its question.
R01's two expected chunks each support the same answer; under Recall@5 both count
as relevant chunks, so retrieving just one gives recall 0.5.

The separate ACL01 case uses exactly R01's Contract A question with only
`all_employees` access. It checks that none of its top five results belongs to
`hr_confidential`; it has no expected relevance label and does not enter either
relevance metric. Missing/unauthorized access-group values also fail this check.

## Exact PowerShell commands

Task 7 requires an optional setup step; vector and hybrid continue to work with
the base installation and never import Sentence Transformers or PyTorch:

```powershell
python -m venv .venv-rerank --system-site-packages
.venv-rerank/Scripts/python -m pip install -e ".[rerank]"
# One-time public model download; inference itself runs locally.
.venv-rerank/Scripts/python -c "from ai_project.reranking import CrossEncoderReranker; CrossEncoderReranker(local_files_only=False)"
```

The optional extra is `sentence-transformers>=5.1,<6`. Model files are cached in
the git-ignored `data/models/reranker/` directory. Normal search/evaluation loads
only cached model files (`local_files_only=True`), disables remote model code,
and passes `token=False` so no Hugging Face credential is required. The default
model is `BAAI/bge-reranker-v2-m3`, the default device is CPU, and the default
pair batch size is 8. A different model may be selected with `--reranker-model`;
its weights must be prepared in the same cache first.

Run from the repository root with the existing local Ollama service and Task 4
index available:

```powershell
.venv-rerank/Scripts/python -m ai_project eval-retrieval --mode vector --cases evals/retrieval_cases.json --index data/index/peopleflow --output results/retrieval_vector_baseline.json
if ($LASTEXITCODE -ne 0) { throw 'Vector evaluation failed' }
.venv-rerank/Scripts/python -m ai_project eval-retrieval --mode hybrid --cases evals/retrieval_cases.json --index data/index/peopleflow --output results/retrieval_hybrid.json
if ($LASTEXITCODE -ne 0) { throw 'Hybrid evaluation failed' }
.venv-rerank/Scripts/python -m ai_project eval-retrieval --mode hybrid-rerank --cases evals/retrieval_cases.json --index data/index/peopleflow --reranker-model BAAI/bge-reranker-v2-m3 --reranker-batch-size 8 --reranker-device cpu --output results/retrieval_hybrid_rerank.json
if ($LASTEXITCODE -ne 0) { throw 'Reranked evaluation failed' }

$vector = Get-Content -Raw -Encoding utf8 results/retrieval_vector_baseline.json | ConvertFrom-Json
$hybrid = Get-Content -Raw -Encoding utf8 results/retrieval_hybrid.json | ConvertFrom-Json
$reranked = Get-Content -Raw -Encoding utf8 results/retrieval_hybrid_rerank.json | ConvertFrom-Json
foreach ($field in @('source_sha256', 'cases_sha256', 'embedding_model', 'vector_dimension')) {
    if ($vector.$field -ne $hybrid.$field -or $vector.$field -ne $reranked.$field) { throw "Comparison input mismatch: $field" }
}
```

The paths shown are defaults: `python -m ai_project eval-retrieval` runs vector
evaluation, and adding `--mode hybrid` selects hybrid and defaults to the separate
`results/retrieval_hybrid.json` output. `--ollama-url http://127.0.0.1:11434` can select another local
Ollama origin. The evaluation uses the index's recorded embedding model, with no
model override or rebuild. Each mode performs 13 sequential local query embeddings,
makes no hosted calls, and does not load `.env`. See
[Task 4 setup](RETRIEVAL.md) if the index needs to be built first.

The report replaces the selected output atomically only after the complete run
succeeds. It records the embedding model, vector dimension, exact canonical source
SHA-256, cases-file SHA-256, UTC run time, per-case rankings and metrics. An API or
validation failure leaves a previous report intact. An access-control failure is
saved as a failed check and returns exit code 1. Relevance misses alone return 0
because this evaluation has no quality gate.

For `--mode hybrid-rerank`, the default output is the separate
`results/retrieval_hybrid_rerank.json`. The model is loaded once per evaluation;
`reranker_initialization_seconds` records that cost separately. `query_seconds`
includes search, canonical/index validation inside search, embeddings, BM25/RRF
and pair scoring. `median_query_seconds` is the median of the 12 relevance-query
times, excluding model initialization, evaluator setup, and ACL01. ACL01 has its
own query time. These are single local CPU runs, not a controlled latency benchmark.

## Local reranking (Task 7)

`hybrid-rerank` uses the unchanged Task 6 branch limits, BM25 settings and RRF.
It builds the **complete deduplicated union** (at most 40 chunks) in RRF order,
before any final top-five truncation. Each `(question, passage)` pair contains the
original question and `document_title + newline + section_path joined by ' > ' +
two newlines + text`. Sentence Transformers `CrossEncoder.predict` scores the
pairs locally in batches. An identity output activation preserves raw logits;
scores are not probabilities. Higher scores rank first, and exact score ties keep
the original RRF rank. The final top-k is selected only after all pairs are scored.

Both branches apply access filters before selecting candidates. A second check
at the scorer boundary rejects unauthorized or missing-access candidates before
constructing passages or calling the scorer. ACL01 records candidate access
groups and rejects unauthorized candidates as well as unauthorized final hits.
The report includes the reranker model/batch/device, original `candidate_ids` in
RRF order, and `expected_in_candidate_pool`/`expected_candidate_ranks` for each
expected chunk. This distinguishes a candidate-generation miss from a reranking
failure. Search results retain the payload fields, use `score` for the CrossEncoder
score and additionally expose `rrf_rank`/`rrf_score` for the selected hits.

```powershell
$question = 'До якого числа треба використати перенесену відпустку за контрактом A?'
.venv-rerank/Scripts/python -m ai_project search $question --mode hybrid-rerank --hr-access --reranker-batch-size 8 --reranker-device cpu
```

The implementation follows the
[Sentence Transformers CrossEncoder API](https://www.sbert.net/docs/package_reference/cross_encoder/model.html)
and the [BAAI model card](https://huggingface.co/BAAI/bge-reranker-v2-m3).

## Hybrid retrieval implementation

Search keeps vector mode as its default. Use hybrid explicitly:

```powershell
$question = 'До якого числа треба використати перенесену відпустку за контрактом A?'
python -m ai_project search $question --mode hybrid --hr-access --top-k 5
```

`src/ai_project/lexical.py` implements BM25 with standard term-frequency saturation
and document-length normalization, `k1=1.5`, `b=0.75`, and positive IDF
`log(1 + (N - df + 0.5)/(df + 0.5))`. Query terms are unique; repeated question
words do not receive extra weight. See the
[Stanford BM25 material](https://web.stanford.edu/class/cs224u/2021/slides/CS224U-IR-part-2.pdf)
for the scoring components.

BM25 indexes exactly the embedding input fields: title, full section path and
original chunk text. It builds a small in-memory index from the canonical JSONL
recorded by the active Qdrant index, verifying the file hash and persisted chunk
membership/payloads before use. It is rebuilt on demand for this 184-chunk local
corpus; no duplicate disk index, package dependency, or embedding rebuild is
needed. Statistics use the complete canonical corpus, while only allowed chunks
are scored and eligible for candidate selection.

Tokenizer `unicode-compounds-v1` uses NFKC normalization, Unicode case folding,
normalized apostrophes/hyphens, and Unicode letters/digits. Ukrainian words and
internal apostrophes are preserved. `ATT-LOCK` produces `att-lock`, `att`, `lock`;
`v1.8` produces `v1.8`, `v1`, `8`. Both exact compounds and their parts are
searchable. This is lexical matching without stemming, stopword removal,
translation or synonyms. English corpus text therefore needs shared terms,
codes or numbers to match a Ukrainian query lexically; vector retrieval supplies
the semantic branch.

Hybrid obtains **up to 20 candidates from each branch**. Qdrant applies the
existing access-group allowlist inside `query_points`; BM25 applies it before
scoring/selecting candidates. Nonmatching BM25 documents are omitted. BM25 ties
and ties within the returned vector candidate pool use ascending `chunk_id`.
The two lists are merged by `chunk_id` with equal weights:

`RRF(chunk) = sum(1 / (60 + branch_rank))`

Ranks start at 1; an absent chunk contributes zero for that branch. A duplicate
chunk within one branch counts once. Final ties use ascending `chunk_id`, followed
by the requested top-k (default 5). The formula and fixed `k=60` follow the
[original RRF paper](https://cormack.uwaterloo.ca/cormack/cormacksigir09-rrf.pdf).
Result fields are unchanged; `score` is the RRF score in hybrid mode and cosine
similarity in vector mode, so the two scores are not directly comparable.
Hybrid reports record branch limits, weights, fusion constant, BM25 parameters
and tokenizer version for reproducibility. Neither search mode reads eval labels.

## Validation and metric definitions

Before any embeddings, the evaluator resolves the active Qdrant alias and reads
the canonical input path from its metadata. It validates the complete JSONL,
checks its SHA-256 and count against the active index, and verifies that persisted
chunk IDs and payloads match the canonical chunk records. The labels' source hash must
also match. Every expected ID must exist, be indexed, and have an access group in
the case's allowlist. Evidence titles, sections, versions and excerpts must match
their chunks. Duplicate case IDs, duplicate expected IDs, missing evidence and
unknown access groups are rejected. The active index is checked again after the
queries; a run spanning a rebuild is rejected.

For each relevance case the report includes ranked top-five chunk IDs, the
1-based first relevant rank (or `null`), a total-miss flag, all missing expected
IDs, Recall@5 and reciprocal rank:

- **Recall@5** = number of distinct expected chunks found in the top five divided
  by the number of expected chunks. Finding one of two expected chunks gives 0.5.
- **Mean Recall@5** = arithmetic mean of case recalls, giving each case equal
  weight, regardless of its number of expected chunks.
- **MRR@5** = arithmetic mean of reciprocal first relevant ranks. Rank 2 gives
  0.5; no expected chunk in the top five gives 0. A chunk below rank 5 does not count.

`relevance` and `access_control` are separate report objects. The access-control
case is excluded from the relevance denominator. The suite was marked reviewed
for Task 7, but 12 manually selected cases are a small baseline, not a comprehensive
retrieval evaluation or proof that other relevant chunks do not exist.

## Observed provisional baseline

The following Task 5/6 relevance figures are retained for comparison. The current
report files have since been regenerated with reviewed status and Task 7 timing
and candidate diagnostics, without changing the relevance labels.

The saved run below was regenerated after the user-reviewed additions of the FAQ
to R01 and the F04 release-notes chunk to R05. Its cases-file hash matches the
current labels.

Saved [results/retrieval_vector_baseline.json](../results/retrieval_vector_baseline.json)
using the current `bge-m3` index (1024 dimensions, 184 chunks) and source SHA-256
`429649032efba26439e267c7da639daf1ef1dd29491d84224a8e0c1e9bdb15f7`.

- **Mean Recall@5: 0.805556**.
- **MRR@5: 0.777778**.
- Complete misses: **2 of 12**; one additional case has partial recall.
- Separate ACL01 check: **PASS**, five returned results, **zero `hr_confidential` chunks**.

| Case | First relevant rank | Recall@5 | Missing expected chunks |
| --- | ---: | ---: | ---: |
| R01 | 1 | 1.0 | 0 |
| R02 | 1 | 1.0 | 0 |
| R03 | 1 | 1.0 | 0 |
| R04 | Miss | 0.0 | 1 |
| R05 | 1 | 0.666667 | 1 |
| R06 | Miss | 0.0 | 1 |
| R07 | 1 | 1.0 | 0 |
| R08 | 1 | 1.0 | 0 |
| R09 | 3 | 1.0 | 0 |
| R10 | 1 | 1.0 | 0 |
| R11 | 1 | 1.0 | 0 |
| R12 | 1 | 1.0 | 0 |

R04 misses the historical attendance correction procedure; R06 misses the
historical leave cancellation procedure. R05 finds the F04 release-notes summary
and locked-period guidance but misses the separate submission-window procedure.
These results are retained for
review. In R01 the accepted FAQ chunk ranks 1 and the Contract A chunk ranks 2;
both expected chunks are retrieved. Relevance figures remain provisional until the draft
questions and source labels have been reviewed.

## Task 6 comparison on the current reviewed labels

Both modes were rerun against the same 184-chunk `bge-m3` index and the unchanged
case file containing the user-reviewed R01/R05 additions. Source hash, cases-file
hash, model and vector dimension were verified equal across the reports. At the
time of Task 6 the suite still had draft status; Task 7 explicitly changes the
status to reviewed and regenerates all reports without changing labels.

| Metric | Vector | Hybrid | Hybrid − vector |
| --- | ---: | ---: | ---: |
| Mean Recall@5 | 0.805556 | 0.847222 | +0.041667 |
| MRR@5 | 0.777778 | 0.756944 | −0.020833 |
| Complete misses | 2/12 | 1/12 | −1 |
| ACL01 confidential chunks / 5 results | 0 | 0 | Both PASS |

The vector report is
[retrieval_vector_baseline.json](../results/retrieval_vector_baseline.json);
the separate hybrid report is
[retrieval_hybrid.json](../results/retrieval_hybrid.json).

| Case | Vector first rank | Hybrid first rank | Vector Recall@5 | Hybrid Recall@5 |
| --- | ---: | ---: | ---: | ---: |
| R01 | 1 | 4 | 1.0 | 0.5 |
| R02 | 1 | 1 | 1.0 | 1.0 |
| R03 | 1 | 1 | 1.0 | 1.0 |
| R04 | Miss | Miss | 0.0 | 0.0 |
| R05 | 1 | 1 | 0.666667 | 0.666667 |
| R06 | Miss | 3 | 0.0 | 1.0 |
| R07 | 1 | 1 | 1.0 | 1.0 |
| R08 | 1 | 2 | 1.0 | 1.0 |
| R09 | 3 | 1 | 1.0 | 1.0 |
| R10 | 1 | 1 | 1.0 | 1.0 |
| R11 | 1 | 1 | 1.0 | 1.0 |
| R12 | 1 | 1 | 1.0 | 1.0 |

Specific source/version checks:

- **R04:** both modes miss M06 / Manager-mediated correction in the top five.
  Hybrid does not solve this historical v1.8 case.
- **R05:** both modes retrieve two of the three expected chunks. M07 / Outside
  the self-service window moves from rank 2 to 1; F04 / New self-service actions
  moves from 1 to 4. M07 / Submit a correction remains missing. The first relevant
  rank and recall are unchanged despite different supporting-source ranks.
- **R06:** F05 / Historical cancellation procedure improves from a miss to rank
  3, recovering the historical leave-cancellation case.

Other improvements and regressions:

- **R09 improves:** its expected payroll settlement chunk moves from rank 3 to 1.
- **R01 regresses:** the FAQ moves from rank 1 to 4, and the Contract A chunk
  falls out of the top five (previously rank 2). Recall drops from 1.0 to 0.5.
- **R08 has mixed ranks:** the proposal chunk moves from 1 to 2, lowering reciprocal
  rank; the eligibility chunk improves from 5 to 4. Recall stays 1.0.
- The other cases keep their first relevant rank and Recall@5.

For R01, the only query token shared with the corpus's lexical vocabulary is
`a` (the Latin contract letter). This is weak lexical evidence because it is also
an English article; the vector branch supplies the Ukrainian semantic match.
The tokenizer provides Unicode support, not cross-language translation.

Hybrid improves recall overall but does not dominate vector retrieval: the R01
and R08 regressions outweigh the reciprocal-rank gains in mean MRR. The configured
fusion, candidate limits and labels were left unchanged after observing these
results. Both ACL01 runs return five `all_employees` results, with zero
`hr_confidential` chunks. Reranking is evaluated separately in Task 7 below.

## Task 7 three-way comparison

All three reports were regenerated from the same **reviewed 12-case suite**,
including the R01/F01 and R05/F04 additions. The questions, expected IDs, evidence
and access groups were verified unchanged from the pre-Task-7 suite. All reports
share the source/cases hashes, `bge-m3` embedding model, 1024-vector dimension and
184 indexed chunks. Hybrid and hybrid-rerank have identical per-case candidate
IDs in identical RRF order and identical fusion settings.

The new report is
[retrieval_hybrid_rerank.json](../results/retrieval_hybrid_rerank.json).

| Metric | Vector | Hybrid | Hybrid-rerank |
| --- | ---: | ---: | ---: |
| Mean Recall@5 | 0.805556 | 0.847222 | **1.000000** |
| MRR@5 | 0.777778 | 0.756944 | **0.916667** |
| Complete misses | 2/12 | 1/12 | **0/12** |
| Median query time | 2.096 s | 2.116 s | **8.251 s** |
| ACL01 | PASS | PASS | PASS |
| ACL01 confidential final chunks | 0/5 | 0/5 | 0/5 |
| ACL01 unauthorized pool chunks | 0 | 0 | 0 |

The run used `BAAI/bge-reranker-v2-m3` on CPU with eight PyTorch threads and pair
batch size 8, Sentence Transformers 5.7.0, PyTorch 2.15.0+cpu and Transformers
5.23.0. Cached model revision:
`953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`. Reranker initialization from cache took
6.933 s and is excluded from the median. Download/setup time is also excluded.
No hosted reranking API was used. Vector and hybrid retain their original
relevance scores, while reranking costs about 3.9 times hybrid's median query time
on this machine.

| Case | First rank: vector / hybrid / rerank | Recall@5: vector / hybrid / rerank |
| --- | --- | --- |
| R01 | 1 / 4 / **1** | 1.0 / 0.5 / **1.0** |
| R02 | 1 / 1 / 1 | 1.0 / 1.0 / 1.0 |
| R03 | 1 / 1 / 1 | 1.0 / 1.0 / 1.0 |
| R04 | Miss / Miss / **2** | 0.0 / 0.0 / **1.0** |
| R05 | 1 / 1 / 1 | 0.666667 / 0.666667 / **1.0** |
| R06 | Miss / 3 / **1** | 0.0 / 1.0 / 1.0 |
| R07 | 1 / 1 / 1 | 1.0 / 1.0 / 1.0 |
| R08 | 1 / 2 / 2 | 1.0 / 1.0 / 1.0 |
| R09 | 3 / 1 / 1 | 1.0 / 1.0 / 1.0 |
| R10 | 1 / 1 / 1 | 1.0 / 1.0 / 1.0 |
| R11 | 1 / 1 / 1 | 1.0 / 1.0 / 1.0 |
| R12 | 1 / 1 / 1 | 1.0 / 1.0 / 1.0 |

Candidate-pool inspection, with **pre-rerank RRF rank → final reranked rank**:

- **R01:** C01 / 4 Leave and sickness **6 → 2**; F01 / Which annual leave balance
  applies? **4 → 1**. Both were available before reranking. The contract chunk
  would have been lost by trimming to the initial five, so full-pool scoring
  restores recall from 0.5 to 1.0.
- **R04:** M06 / Manager-mediated correction **6 → 2**, recovering the historical
  v1.8 procedure missed by both earlier modes. This was a ranking failure, not a
  missing candidate.
- **R05:** M07 / Submit a correction **9 → 4**; M07 / Outside the self-service
  window **1 → 1**; F04 / New self-service actions **4 → 2**. All three expected
  chunks were in the pool; promoting the rank-nine chunk yields full coverage.
- **R06:** F05 / Historical cancellation procedure **3 → 1**. Recall remains 1.0
  relative to hybrid, with improved reciprocal rank.
- **R09:** M09 / Gross pay and net pay **1 → 1**; full recall is retained.

Every expected chunk in all 12 cases was present in the hybrid candidate pool;
the reranked report records this per ID. Pool sizes ranged from 23 to 37. The
same **33 authorized candidates** were available for ACL01 in hybrid and rerank;
all had `all_employees` access and none had `hr_confidential` access.

There are no Recall@5 or first-relevant-rank regressions relative to hybrid on
this set. One supporting-source rank worsens in **R08**: its eligibility chunk
moves from RRF rank 4 to reranked rank 5, while its proposal chunk remains rank 2.
Relative to vector, R08 still has a worse first-relevant rank (2 versus 1).
Perfect recall on these 12 reviewed cases is not evidence of general retrieval
accuracy; no labels, branch limits, fusion weights or model settings were tuned
after inspecting the reranked results.

## Offline tests

```powershell
python -m pytest -q tests/test_reranking.py tests/test_hybrid_retrieval.py tests/test_retrieval.py tests/test_retrieval_evaluation.py -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
```

Tests use fake embeddings and real temporary local Qdrant indexes, with mocked
search where exact ranks or a deliberate access violation are needed. They cover
partial recall, misses, the rank-five cutoff, label/evidence/access validation
before calls, corpus/index mismatches, CLI report persistence, and separation of
access checks from relevance metrics. No test makes real API calls.

Task 6 tests additionally check Unicode compounds and Ukrainian apostrophes,
BM25 scores and title/section/text coverage, equal-weight fusion, duplicate
handling, deterministic ties, and pre-selection access filtering in both branches
with more than 20 denied and allowed documents. Evaluation tests cover both modes
and verify that hybrid's default report cannot overwrite the vector baseline.

Task 7 uses a fake reranker to prove that the entire deduplicated pool is scored,
a candidate initially ranked 8 can become final rank 1, exact score ties retain
RRF order, and ACL01 restricted text never reaches the scorer. Additional checks
cover score validation, pair formatting/batching, candidate-coverage diagnostics,
reviewed status, and base modes working with reranker packages unavailable.

Observed validation: Ruff passes for the changed modules and tests. The full
suite has **386 passed and 21 subtests passed**, with
the same pre-existing failure in
`tests/test_ollama.py::test_defaults_do_not_load_secrets`: the existing Ollama
settings loader calls `load_dotenv`, contrary to that test's expectation. This
task does not change the settings loader; evaluation uses the existing retrieval
path directly.
