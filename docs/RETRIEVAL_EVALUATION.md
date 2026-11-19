# PeopleFlow vector retrieval baseline (Task 5)

The evaluation calls the existing vector `search` function at **k=5**, with each
case's exact allowed groups. It does not change retrieval, add BM25 or reranking,
or generate answers. Results are **provisional until the user reviews the draft
questions and expected chunks**.

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

## Exact PowerShell command

Run from the repository root with the existing local Ollama service and Task 4
index available:

```powershell
python -m ai_project eval-retrieval --cases evals/retrieval_cases.json --index data/index/peopleflow --output results/retrieval_vector_baseline.json
```

All three paths shown are defaults, so `python -m ai_project eval-retrieval` runs
the same evaluation. `--ollama-url http://127.0.0.1:11434` can select another local
Ollama origin. The evaluation uses the index's recorded embedding model, with no
model override or rebuild. It performs 13 sequential local query embeddings,
makes no hosted calls, and does not load `.env`. See
[Task 4 setup](RETRIEVAL.md) if the index needs to be built first.

The report replaces the selected output atomically only after the complete run
succeeds. It records the embedding model, vector dimension, exact canonical source
SHA-256, cases-file SHA-256, UTC run time, per-case rankings and metrics. An API or
validation failure leaves a previous report intact. An access-control failure is
saved as a failed check and returns exit code 1. Relevance misses alone return 0
because this draft baseline has no quality gate.

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
case is excluded from the relevance denominator. Scores remain provisional:
12 manually drafted cases are a small, unreviewed baseline, not a comprehensive
retrieval evaluation or proof that other relevant chunks do not exist.

## Observed provisional baseline

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

## Offline tests

```powershell
python -m pytest -q tests/test_retrieval_evaluation.py -p no:cacheprovider --basetemp=.pytest_tmp_task5_verify
python -m pytest -q -p no:cacheprovider --basetemp=.pytest_tmp_task5_all
```

Tests use fake embeddings and real temporary local Qdrant indexes, with mocked
search where exact ranks or a deliberate access violation are needed. They cover
partial recall, misses, the rank-five cutoff, label/evidence/access validation
before calls, corpus/index mismatches, CLI report persistence, and separation of
access checks from relevance metrics. No test makes real API calls.

Observed validation: **28 new evaluation tests pass**; Ruff passes for the new
module and tests. The full suite has **362 passed and 21 subtests passed**, with
the same pre-existing failure in
`tests/test_ollama.py::test_defaults_do_not_load_secrets`: the existing Ollama
settings loader calls `load_dotenv`, contrary to that test's expectation. This
task does not change the settings loader; evaluation uses the existing retrieval
path directly.
