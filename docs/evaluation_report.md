# AI HR Support Ticket Parser — Evaluation Report

## 1. Executive Summary

This report compares two zero-shot prompt versions (`v1` baseline and `v2` refined instructions) across two language models: **Google Gemini 3.1 Flash Lite** (via OpenRouter) and **Qwen3 8B** (via local Ollama). On the **25-ticket holdout set**, Gemini with Prompt v2 achieved the highest aggregate **field accuracy: 172/175 (98.29%)**, compared with 166/175 (94.86%) for Gemini v1. Qwen3 improved from 151/175 (86.29%) to 156/175 (89.14%). All four runs achieved **100/100 valid structured outputs**.

**Selected configuration:** Gemini 3.1 Flash Lite, Prompt v2, temperature `0`, top_p `1`. This is a recommendation based on the observed evaluation results, not a guarantee of production performance.

## 2. Task and Dataset

The system converts unstructured HR support requests into a validated `HRSupportTicket` JSON object. The schema includes `summary`, `category`, `priority`, `application`, `language`, `requires_support`, `details.error_code`, `details.error_message`, and `suggested_actions`.

- **Input dataset:** 100 synthetic HR support tickets, including English, Ukrainian, and Russian messages.
- **Golden set:** 40 manually labeled tickets.
- **Development split:** 15 golden tickets, used for prompt analysis and iteration.
- **Holdout split:** 25 golden tickets, reserved for final assessment.
- **Prediction batches:** 100 tickets per model/prompt configuration.

The holdout labels were not used as the intended basis for prompt iteration. However, results from earlier baseline analysis may have exposed some holdout mismatches before final testing; consequently, the holdout should be described as a **reserved evaluation split**, not a perfectly blind test.

## 3. Experimental Setup

| Parameter | Setting |
|---|---|
| Models | `google/gemini-3.1-flash-lite` (OpenRouter); `qwen3:8b` (Ollama) |
| Prompt versions | `v1` and `v2` |
| Temperature | `0` |
| Top-p | `1` |
| Output validation | Pydantic `HRSupportTicket` schema |
| Evaluation | Exact comparison for enums/booleans; case-insensitive trimmed comparison for nullable text |
| Evaluation unit | Individual structured field, not complete ticket |

Seven fields are scored: `category`, `priority`, `application`, `language`, `requires_support`, `details.error_code`, and `details.error_message`. With 15 development examples, there are **105 field comparisons** per configuration; with 25 holdout examples, **175 field comparisons**.

Free-text `summary` and `suggested_actions` are **excluded** because multiple valid phrasings and action sets may exist. No LLM judge or manual quality rubric was used for these fields. Valid-output rate and latency are computed over the **full 100-ticket batch**, whereas field accuracy and mismatch lists are scoped to the selected golden split.

## 4. Prompt Iteration

### v1 — Baseline

The initial zero-shot prompt defined the schema extraction rules, HR categories, priority levels, multilingual handling, null handling, and safe suggested actions. It included no few-shot examples.

### v2 — Refined Rules

The second zero-shot prompt clarified:

1. `technical` versus `other`, especially for vague reports without a concrete technical symptom.
2. Priority thresholds, to avoid interpreting isolated errors or frustration as automatically `high` priority.
3. Explicit application-name extraction, including names such as HR Portal, ESS, Shifts, and ShiftBoard.
4. Error-code and error-message extraction, including numeric HTTP codes and surrounding quotation marks.
5. Classification boundaries while preserving the overall schema and zero-shot approach.

These changes targeted baseline weaknesses, especially priority overestimation and omitted application names. Improvements were hypotheses until evaluated.

## 5. Development Set Results

**15 tickets × 7 fields = 105 comparisons per run.**

| Model | v1 correct | v1 accuracy | v2 correct | v2 accuracy | Change |
|---|---:|---:|---:|---:|---:|
| Gemini 3.1 Flash Lite | 104/105 | 99.05% | 105/105 | 100.00% | +0.95 pp |
| Qwen3 8B | 92/105 | 87.62% | 97/105 | 92.38% | +4.76 pp |

Gemini v2 resolved the only development mismatch from v1 (ticket #31, priority `high` instead of `medium`). Qwen3 v2 corrected all four development application-name mismatches and the `HTTP 500` versus `500` error-code mismatch, but still had five priority mismatches, one `requires_support` mismatch, and two error-message mismatches. Its error-message score declined from 14/15 to 13/15.

## 6. Holdout Set Results

**25 tickets × 7 fields = 175 comparisons per run.**

| Model | v1 correct | v1 accuracy | v2 correct | v2 accuracy | Change |
|---|---:|---:|---:|---:|---:|
| Gemini 3.1 Flash Lite | 166/175 | 94.86% | **172/175** | **98.29%** | **+3.43 pp** |
| Qwen3 8B | 151/175 | 86.29% | 156/175 | 89.14% | +2.86 pp |

### Holdout Field Accuracy

| Field | Gemini v1 | Gemini v2 | Qwen3 v1 | Qwen3 v2 |
|---|---:|---:|---:|---:|
| Category | 92% | 96% | 80% | 80% |
| Priority | 76% | **100%** | 64% | 72% |
| Application | 100% | 100% | 84% | 96% |
| Language | 96% | 96% | 100% | 100% |
| Requires support | 100% | 100% | 92% | 88% |
| Error code | 100% | 96% | 92% | 96% |
| Error message | 100% | 100% | 92% | 92% |

Both models improved in aggregate, but not uniformly across every field. Gemini's priority accuracy rose from 19/25 to 25/25; Qwen3's application extraction rose from 21/25 to 24/25. Conversely, Gemini's error-code accuracy decreased by one ticket and Qwen3's `requires_support` accuracy decreased by one ticket.

## 7. Error Analysis

The holdout evaluation revealed several recurring error patterns: category ambiguity, priority overestimation, multilingual classification errors, and incorrect extraction of application-specific error codes. The following five examples illustrate these issues.

### Five Representative Errors

| Ticket | Model | Field | Expected | Predicted |
|---|---|---|---|---|
| #46 | Gemini v2 | `category` | `other` | `employee_profile` |
| #94 | Gemini v2 | `language` | `ru` | `uk` |
| #96 | Gemini v2 | `details.error_code` | `EXPORT_500` | `500` |
| #38 | Qwen3 v2 | `category` | `other` | `technical` |
| #43 | Qwen3 v2 | `priority` | `medium` | `high` |

**1. Ticket #46 — Incorrect category for an HR document request (Gemini v2)**

The employee requested a standard employment confirmation letter for a rental application. The expected category was `other`, but Gemini predicted `employee_profile`.

A possible explanation is that the model associated employment-related personal information with the employee profile category, even though the request concerned document issuance rather than profile modification. This illustrates a classification boundary that Prompt v2 did not fully resolve.

**2. Ticket #94 — Russian classified as Ukrainian (Gemini v2)**

The ticket was written predominantly in Russian and described an `HTTP 401 Unauthorized` login error in HR Portal. The expected language was `ru`, but Gemini predicted `uk`.

The model may have confused closely related languages, particularly in an HR context containing shared terminology and English technical expressions. This demonstrates that otherwise accurate structured extraction does not guarantee correct language identification.

**3. Ticket #96 — Application-specific error code truncated (Gemini v2)**

The ticket reported a PayHub payroll export failure with the explicit error code `EXPORT_500`. Gemini extracted `500` instead of the complete code.

A plausible explanation is overgeneralization of Prompt v2's HTTP error-code normalization instructions. The model may have interpreted the numeric suffix as the relevant code and discarded the application-specific prefix. This is particularly important because incomplete error codes can reduce the usefulness of downstream troubleshooting and ticket routing.

**4. Ticket #38 — Vague report classified as a technical issue (Qwen3 v2)**

The employee wrote: "the thing wont save. same as before. can someone look?" The expected category was `other`, but Qwen3 predicted `technical`.

Although "won't save" suggests a possible software problem, the message does not identify an application or provide enough context to establish a concrete technical issue under the dataset's labeling rules. The model may have relied too strongly on a common technical symptom instead of preserving uncertainty. The same ticket also received `medium` priority instead of `unknown`.

**5. Ticket #43 — Priority overestimation (Qwen3 v2)**

The employee could not access HR Portal after a contract extension, despite HR confirming continued employment. The expected priority was `medium`, but Qwen3 predicted `high`.

A possible explanation is that the model treated account lockout and inability to sign in as sufficient evidence of high urgency. However, the ticket did not establish the broader operational impact or critical deadline required by the dataset's priority rules. This reflects Qwen3's recurring tendency to overestimate priority.

### Overall Error Patterns

Gemini v2 produced only **3 field mismatches out of 175 holdout comparisons**, but its remaining errors show weaknesses in category boundaries, language identification, and preserving complete error codes.

Qwen3 v2 produced **19 field mismatches**, down from 24 with Prompt v1. Its recurring weaknesses included priority overestimation, classification of vague requests as technical issues, incorrect `requires_support` decisions, and inconsistent error-message extraction. Some regressions also appeared, demonstrating that improvements in aggregate accuracy do not guarantee improvements for every individual ticket.

These explanations are hypotheses based on the input messages, expected labels, and observed predictions. They are not verified descriptions of the models' internal reasoning.

**Methodological note:** These holdout errors are analyzed for reporting purposes only. Prompt v2 remains unchanged; any further prompt iteration should be evaluated using newly collected labeled examples rather than optimizing against the existing holdout set.

## 8. Validity and Latency

All four runs produced **100 valid structured outputs from 100 predictions (100%)**.

| Model / Prompt | p50 latency | p95 latency |
|---|---:|---:|
| Gemini v1 | 2.385 s | 11.819 s |
| Gemini v2 | **1.411 s** | **6.464 s** |
| Qwen3 v1 | 3.213 s | 3.961 s |
| Qwen3 v2 | 3.193 s | 4.028 s |

These latency statistics cover all 100 predictions in each batch, not only golden tickets. Differences between runs can reflect infrastructure, runtime conditions, and sampling variability; the results do **not** establish that prompt changes alone caused the latency improvement.

## 9. Sampling Parameters Experiment (Prompt v1)

A separate experiment tested whether changing generation sampling parameters affected extraction quality. Both models used the **same Prompt v1** and the **same 100-ticket dataset**, with two configurations:

- **Baseline:** temperature `0`, top_p `1`.
- **Alternative:** temperature `0.3`, top_p `0.9`.

Unlike the development and holdout comparisons above, this experiment's field accuracies were calculated across **all 40 golden labels** (40 tickets × 7 fields = 280 comparisons). Valid-output rate and latency were calculated over all 100 predictions per run. The 40-label aggregate combines development and reserved holdout labels, so it is presented as a descriptive sampling comparison, not as a new blind holdout test.

### Overall Results

| Model | Sampling | Correct fields | Field accuracy | Valid outputs | p50 latency | p95 latency |
|---|---|---:|---:|---:|---:|---:|
| Gemini 3.1 Flash Lite | T=0, P=1 | 270/280 | **96.43%** | 100/100 | 2.385 s | 11.819 s |
| Gemini 3.1 Flash Lite | T=0.3, P=0.9 | 267/280 | 95.36% | 100/100 | 1.399 s | 1.955 s |
| Qwen3 8B | T=0, P=1 | 243/280 | **86.79%** | 100/100 | 3.213 s | 3.961 s |
| Qwen3 8B | T=0.3, P=0.9 | 243/280 | **86.79%** | 100/100 | 3.687 s | 4.834 s |

The alternative sampling configuration reduced Gemini's aggregate field accuracy by **1.07 percentage points** (three additional incorrect fields). Qwen3's aggregate score was unchanged. Neither alternative run produced invalid structured outputs.

### Field-Level Comparison

| Field | Gemini T=0, P=1 | Gemini T=0.3, P=0.9 | Qwen3 T=0, P=1 | Qwen3 T=0.3, P=0.9 |
|---|---:|---:|---:|---:|
| Category | 95.0% | 92.5% | 87.5% | 87.5% |
| Priority | 82.5% | 80.0% | 62.5% | 62.5% |
| Application | 100.0% | 100.0% | 80.0% | 80.0% |
| Language | 97.5% | 95.0% | 100.0% | 100.0% |
| Requires support | 100.0% | 100.0% | 92.5% | 92.5% |
| Error code | 100.0% | 100.0% | 92.5% | 92.5% |
| Error message | 100.0% | 100.0% | 92.5% | 92.5% |

For Gemini, the alternative configuration introduced errors in `category`, `priority`, and `language`, while the other four fields retained their baseline accuracy. Qwen3's field-level accuracies remained identical, although this does not prove its individual predictions were identical.

### Interpretation

- **Extraction accuracy:** These results provide no evidence that the tested nonzero temperature/top_p combination improved structured extraction. The deterministic baseline was at least as accurate for both models in this experiment.
- **Latency:** Gemini's alternative run had lower observed p50/p95 latency, while Qwen3's alternative run was slower. These are single-batch observations; infrastructure and runtime variation prevent attributing the differences to sampling settings alone.
- **Scope:** Temperature and top_p were **changed together**, so this experiment cannot isolate the individual effect of either parameter. There were no repeated trials to estimate run-to-run variance.
- **Decision:** Retain temperature `0` and top_p `1` for the final Prompt v2 configuration. The alternative sampling settings were evaluated only with **Prompt v1**, not v2.

## 10. Limitations

- The dataset is **synthetic**, so it may not reflect real-world ticket distributions or writing styles.
- Only **40 labeled tickets** are available (15 development, 25 holdout); differences may be sensitive to individual examples.
- Aggregate field accuracy treats all seven fields equally and does not measure **complete-ticket exact match**.
- `summary` and `suggested_actions` were not scored; safe and useful action quality remains unverified.
- Valid JSON/schema compliance does not guarantee factual correctness, safe recommendations, or adherence to organizational HR policy.
- There is no repeated-run variance estimate, confidence interval, formal significance test, cost comparison, or real-world user study.
- The sampling experiment changed temperature and top_p simultaneously, used Prompt v1 only, and was not replicated; causal effects of individual sampling parameters cannot be inferred.
- Earlier exposure to some holdout baseline mismatches limits the strength of claims about complete holdout blindness.

## 11. Conclusion and Recommendation

**Select Gemini 3.1 Flash Lite + Prompt v2 (`temperature=0`, `top_p=1`)** as the strongest tested configuration for this homework. It achieved **98.29% holdout field accuracy**, improved by **3.43 percentage points** relative to Gemini v1, and maintained a **100% valid-output rate**. Qwen3 8B with Prompt v2 is a viable local alternative with **89.14% holdout field accuracy**, though it remains less reliable on priority, category, and support-intervention decisions.



The Prompt v1 sampling experiment did not show an accuracy benefit from T=0.3/P=0.9, supporting the choice to retain T=0/P=1 for the tested final configuration. Prompt v2 is frozen for this evaluation. Further work should use **newly collected labeled examples** for subsequent prompt iterations, alongside a human-reviewed rubric for summaries and suggested actions, and tests of operational constraints such as cost, throughput, and policy safety.

## 12. Reproducibility

The reports were generated using the project's `eval` command with the same golden labels and an explicit ID split. Example:

```powershell
python -m ai_project eval `
  --predictions results/openrouter_v2.json `
  --golden data/golden_set.json `
  --ids-file data/holdout_ids.json `
  --output results/evals/openrouter_v2_holdout.md
```

Source evaluation files: `openrouter_v1_dev.md`, `openrouter_v2_dev.md`, `ollama_qwen3_8b_v1_dev.md`, `ollama_qwen3_8b_v2_dev.md`, and their four corresponding `_holdout.md` reports.

Additional sampling experiment reports: `openrouter_v1_t03_p09.md` and `ollama_qwen3_8b_v1_t03_p09.md` (40 golden labels each).
