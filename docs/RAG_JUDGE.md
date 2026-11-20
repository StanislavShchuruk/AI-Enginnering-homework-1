# PeopleFlow RAG judge and human calibration (Task 9B)

`eval-rag-judge` evaluates the existing saved answers, without retrieval or new
answer generation. It verifies the baseline's `cases_sha256` against the exact
bytes of `evals/rag_cases.json`, checks unique matching case IDs and questions,
validates saved answer schemas and citation membership, and checks that saved
excerpts equal the original generator request. Every one of the 10 human-labeled
IDs must refer to a valid saved answer. Input artifacts are never changed.

CSV headers and field values are trimmed. The supplied CSV contains unquoted
commas in the final Reason column; trailing fields are rejoined with commas only
when Reason is the last header. Quoted CSV reasons also work. Blank human reasons
remain blank and are identified as absent in disagreement reporting.

The versioned `docs/prompts/rag-judge-v1.txt` rubric assesses completeness against
expected status, required facts and qualifications, unsupported parts and gap
wording. Faithfulness requires each claim's actual wording to follow from its own
cited passages, including numerical, conditional and version constraints. Every
claim receives an ordered, 1-based support verdict and short explanation. Overall
faithfulness must agree with those verdicts; n/a is allowed exactly for no claims.
Invalid structure, missing/duplicate claim assessments and provider failures are
judge errors, never semantic failures. No repair or semantic override is applied.

Requests include the exact structured answer and every excerpt originally supplied
to generation (including source metadata), plus the question and expected facts.
They exclude human scores/reasons, baseline scoring signals, regex matchers and
alternative label evidence. Expected facts inform completeness; only the claim's
cited generator excerpts inform faithfulness. The prompt treats candidate answers
and excerpts as untrusted data, including any embedded instructions.

## PowerShell commands

Validate everything offline first:

```powershell
python -m ai_project eval-rag-judge --validate-only
```

After explicit approval for hosted inference, use the settings in the project
`.env` or process environment, documented in `.env.example`: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`,
`OPENROUTER_TIMEOUT_SECONDS`, and `OPENROUTER_MAX_RETRIES`. The command loads `.env`
from the current working directory; existing process values take precedence, and
`--model` overrides the model from either source. Configure credentials outside
chat; do not print them. Set a model that
supports strict JSON Schema, or override the configured model:

```powershell
python -m ai_project eval-rag-judge --baseline results/rag_baseline.json --cases evals/rag_cases.json --human-labels evals/rag_human_labels.csv --output results/rag_judge.json
```

Run that command once. For an optional model override, add `--model` followed by
your actual OpenRouter model ID. `provider/model-id` is a placeholder, not a
usable model. Use a new output name for a subsequent run; existing JSON or sibling
Markdown files are preserved and cause an output-validation error.

If setup fails, the CLI reports the failing stage and a safe diagnostic. An
OpenRouter configuration failure usually means neither `.env` nor the process
environment supplies the required key or model. Run from the project root so
the command can locate `.env`. Input validation (`--validate-only`) does not load
`.env` or check provider credentials
and makes no API calls.

The judge reuses OpenRouter's existing SDK integration, strict schema requests,
safe provider errors and bounded transient retries. Temperature is 0 and top-p 1.
The model is configurable; no model ID or price is assumed. The full run attempts
19 valid saved answers, with 10 calibration and nine judge-only answers. R09's
saved response-validation error remains in the 20 overall case counts and is not
sent to the judge. No new generation or embedding calls are made.

Outputs must be new `.json` and sibling `.md` paths. JSON retains input hashes,
prompt version/hash/text, configured and returned model identities, generation
settings, exact requests, raw responses, token usage when provided, per-case and
per-claim verdicts/reasons, human labels and summary. The short Markdown report
separates the calibration subset and judge-only counts, lists all verdicts and
every disagreement with both rationales. Human reasons are only combined with
judge results after inference. Faithfulness agreement excludes human n/a (N01)
and lists these cases separately. Each dimension reports exact matches and the
number of successfully judged eligible human answers; judge errors are separately
counted and excluded, never silently treated as disagreements. With no errors,
the agreement denominators are 10 for Completeness and nine for Faithfulness.

An exit code of 1 indicates judge/provider/schema or setup errors; semantic fail
verdicts and the preexisting baseline error alone do not cause nonzero exit.
Results are written after the completed run; an interrupted process has no resume
support. Judge output is fallible: review disagreements rather than changing the
human labels or treating agreement as objective accuracy.

## Offline checks

```powershell
python -m pytest -q tests/test_rag_judge.py --basetemp=.pytest_tmp_task9b_check -p no:cacheprovider
python -m pytest -q --basetemp=.pytest_tmp_task9b_all -p no:cacheprovider
```

All judge responses in tests are mocked. No test makes a hosted API call.
Actual agreement numbers require an explicitly approved judge run; mock test
verdicts are never published as real evaluation results.
