# PeopleFlow RAG answer baseline (Task 9A)

The [20-case suite](../evals/rag_cases.json) is **draft**. Its facts, qualifications
and acceptable source excerpts were derived from the canonical corpus before
Task 9A generation. The run is provisional until those labels are reviewed.
The existing reviewed retrieval suite is unchanged. The two Task 8 smoke answers
were already observed during Task 8; neither saved answer was read to construct
Task 9A labels. No question, label, matcher or generation prompt was tuned after
looking at Task 9A answers.

The [compact label review sheet](../results/rag_case_review.md) contains each
question, access groups, expected status, required facts/qualifications and
verbatim source excerpts, with alternatives deduplicated within each case.
It is generated from labels only, without retrieval or inference. Review the
negative cases against the whole corpus, not only retrieved passages.

## Cases and labeling

- R01–R12 reuse suitable reviewed retrieval questions. R05 uses the exact Task 8
  question without the answer-bearing deadline hint.
- N01 is the exact Task 8 home-solar reimbursement question; N02 asks in Ukrainian
  about nursery reimbursement. N03 asks about the undocumented v3.0 correction
  window. These have no supported answer in the corpus.
- P01 combines the documented correction window with an absent solar benefit.
  P02 combines the documented lockout duration with an absent authenticator
  vendor support phone. Both require a supported answer and an explicit gap.
- T01 distinguishes Contract B's already part-time leave entitlement from
  Contracts A/C; T02 asks for historical v1.8 attendance rules; T03 asks for the
  current v2.0 cancellation flow rather than the superseded support-mediated flow.

The distribution is 15 answered, two partial and three unavailable cases, with
English and Ukrainian questions. Facts have per-fact acceptable chunk IDs and
verbatim evidence with title, section and version. Equivalent FAQ, policy, guide
or release-note sources are included when they support the labeled fact and the
question permits them. Historical evidence is acceptable for historical questions.
Missing facts do not receive fabricated positive source labels.

R05's three independently labeled facts are:

1. Self-service is available within **14 calendar days from the affected workday**.
2. Self-service requires an **unlocked payroll period**.
3. **ATT-LOCK routes to HR Payroll even within the 14-day window**; historical
   direct manager edits cannot bypass v2.0 controls.

The corpus SHA-256, label-file SHA-256 and prompt SHA-256 are stored in the run.
Before inference, label validation checks corpus/index identity, source existence,
case access groups, metadata, verbatim excerpts, duplicate IDs and pattern syntax.
The independent factual correctness/completeness of the labels still needs review.

## Command and persisted artifacts

Run from the repository root with the existing Task 7 virtual environment,
cached `BAAI/bge-reranker-v2-m3`, indexed canonical corpus and local Ollama serving
`bge-m3` and `qwen3:8b`. No hosted service is used. The exact PowerShell baseline
command was:

```powershell
$env:PYTHONUTF8 = '1'
$env:OMP_NUM_THREADS = '8'
$env:MKL_NUM_THREADS = '8'
$env:OLLAMA_TIMEOUT_SECONDS = '300'
./.venv-rerank/Scripts/python.exe -m ai_project eval-rag --cases evals/rag_cases.json --index data/index/peopleflow --context-token-budget 3200 --output results/rag_baseline.json
```

`eval-rag` fixes generation to local Ollama `qwen3:8b`, prompt `rag-v1` and
`hybrid-rerank` at top five, reusing the same `search`, access/context assembly,
`generate_answer` and Ollama provider used by `ask`. The cached reranker runs on
CPU with the existing default batch size 8 and no model downloads. Generation
temperature/top-p use existing settings (defaults 0/1). The context budget uses
the exact Task 8 lexical counting and whole-chunk inclusion rules documented in
[RAG.md](RAG.md). The prompt is unchanged from Task 8.

The run saves [structured JSON](../results/rag_baseline.json) and a
[compact results report](../results/rag_baseline.md). JSON is atomically updated
after each attempted case. A later case error does not erase earlier results;
there is no automatic retry/repair or resume. Both output paths must be new;
use `results/rag_baseline_reproduced.json` in a checkout with saved outputs.
The command exits nonzero if any retrieval, provider or response-validation
error occurred, while retaining the completed report. Status/fact mismatches are
evaluation observations and do not by themselves fail command execution.

Each row retains question/access/status labels, exact included `sources`, context
count, retrieved IDs, structured answer and rendered answer when valid, raw model
content, model/usage, generation duration, scoring details, and observed failures.
`generation_request` preserves the exact user message sent to generation; its
excerpts equal `sources`, including short-ID to original chunk-ID mappings and
canonical metadata. The report saves the exact system prompt and hash, generation
settings, retrieval mode/top-k/reranker, active collection and index metadata.
This supports inspection of context truncation, version mix-ups and source choice.

The same label-only review sheet can be reproduced offline:

```powershell
python -m ai_project eval-rag --cases evals/rag_cases.json --index data/index/peopleflow --review-sheet results/rag_case_review_reproduced.md
```

## Separate scoring signals

**Schema and status.** Pydantic enforces the Task 8 response schema, including
citations on every claim, no extra fields, and status/claims/gap consistency.
Status matching compares a schema-valid response status with the case label.
A schema-valid `unavailable` answer is a valid response, distinct from
`retrieval_error`, `provider_error` and `response_validation_error` outcomes.
Failed requests are not converted to unavailable answers or included as correct
status matches. Schema-invalid responses are retained for inspection and are
excluded from status/content denominators.

**Citation membership.** Every claim's short source IDs must exist in the exact
included context, not merely in retrieval results or the corpus. Unknown IDs
fail independently of status and key-fact checks. Invalid raw responses are saved
for review but never displayed by `ask` as validated answers. A valid unavailable
response has no claims and hence zero citation obligations; its membership check
passes vacuously. Membership says nothing about whether a passage supports a claim.

**Key facts.** Small, predeclared English/Ukrainian regex checks detect reliable
lexical signals such as numbers, units, named routes and times. All patterns for
a fact must match within one claim. Neither the question, context text nor
`missing_information` can satisfy them. A fact is `matched`,
`missing_or_paraphrased`, or semantic-only `not_scored`. Qualifications are always
retained for human review. These are lexical coverage indicators, not correctness
judgments: synonyms can be missed, negations can match, and a matching numeral
does not prove a complete rule. Fact patterns were frozen before the baseline.

**Expected sources for cited facts.** For a lexically matched fact, at least one
matching claim must cite one of that fact's acceptable original chunks. A correct
chunk cited only on another claim does not satisfy the check. Extra chunks on a
matched claim are exposed separately for review. For semantic-only facts, the
report lists claims citing acceptable chunks as review candidates; it does not
automatically count them as fact coverage or supported answers. A numerically
correct assertion citing the wrong document/version can therefore pass the
lexical check while failing expected-source alignment.

Summary denominators are explicit: status and membership use schema-valid
responses; key-fact totals use regex facts from those responses; expected-source
totals use lexically matched facts only. Error counts and semantic-only unscored
fact counts are reported separately. No combined answer-accuracy score is produced.
An error case with a schema-valid response but invalid source IDs remains an
error outcome while contributing a failed membership check.

## Semantic review

Every valid response still needs human assessment for entailment, negation,
contradictions, omissions, qualifications, language, named-version applicability,
unsupported additional claims, completeness, and accurate partial/unavailable
gap wording. Also inspect cases lacking acceptable evidence in context to separate
retrieval/context omissions from generation omissions. A correct expected status
does not prove a correct answer. No LLM judge or paid calls are used in this task.

Review labels first, then answers. Keep label corrections distinct from future
prompt/retrieval improvements. The baseline remains provisional; lexical results
and citation membership must not be presented as semantic accuracy.

## Observed baseline (2026-11-20)

All 20 cases were attempted. There were 19 schema-valid responses and one
response-validation error, with no retrieval or provider errors. The CLI exited
1 as designed because of that validation error; the completed JSON and Markdown
reports were retained.

| Signal | Result | Scope |
| --- | ---: | --- |
| Expected status | 16/19 | Schema-valid responses |
| Citation membership | 19/19 | Includes claim-free unavailable responses |
| Lexical key facts | 12/17 | 13 additional facts are semantic-only and unscored |
| Expected source for matched lexical facts | 11/12 | Source membership, not entailment |

Important review findings:

- **R05:** the answer gives 14 calendar days and the HR Payroll route but omits
  the starting point (affected workday), the unlocked-period prerequisite, and
  explicit wording that ATT-LOCK overrides the window even within 14 days.
  The first two facts fail lexical checks; the route matches lexically while its
  within-window qualification still needs semantic review. Citation membership
  passing does not make this a complete answer.
- **R06:** returns `partial` while claiming the employee checks Cancelled and the
  released balance, then says balance confirmation is missing. Review this
  internal inconsistency and the unnecessary gap; expected status is `answered`.
- **R09:** returns `answered` with `missing_information=""` rather than `null`.
  The Task 8 consistency validator rejects this response. Raw output and exact
  context are preserved; it is not counted as an unavailable answer.
- **P01:** identifies the absent solar benefit but omits the workday origin of
  the correction window. **P02** incorrectly marks the mixed question `answered`
  and puts the missing vendor phone into a cited claim instead of a partial gap.
  Its lockout claim cites a v1.8 release-note chunk outside the labeled current
  source alternatives. Review version applicability and whether that historical
  equivalent should be accepted; do not assume the flag alone proves false content.
- **T01:** a lexical false negative: “annual leave days per calendar year are
  15” does not match the frozen `15 ... days` word order. The source review should
  assess the fact rather than treat this matcher miss as a wrong numerical answer.
  **T02** omits the unlocked-period qualification from its window claim.
- **N03:** invents a v3.0 14-day rule using a v2.0 excerpt while also admitting
  that v3.0 evidence is absent. Membership passes, but the status mismatches and
  this spot check shows why named-version entailment needs semantic review.

These observations are targeted review notes, not a completed semantic scoring
of all answers. Labels, patterns and rag-v1 were left unchanged after the run.
The saved case and prompt hashes were checked against the files after completion.

## Offline checks

```powershell
python -m pytest -q tests/test_rag_evaluation.py tests/test_rag.py -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
python -m ruff check src/ai_project/rag_evaluation.py src/ai_project/rag.py tests/test_rag_evaluation.py
```

Focused tests use mocked answers/providers and cover independent score signals,
equivalent sources, known-but-wrong and unknown citations, claim-local alignment,
excluded text, semantic-only facts, negation limitations, unavailable responses,
error denominators, exact context persistence, invalid response preservation,
pre-inference label validation, and offline review-sheet generation. All **438
tests and 21 subtests pass**; Ruff passes for the listed modules and tests.
