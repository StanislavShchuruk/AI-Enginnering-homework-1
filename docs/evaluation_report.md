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

### Gemini v2 — Three Holdout Mismatches

| Ticket | Field | Expected | Predicted |
|---|---|---|---|
| #46 | `category` | `other` | `employee_profile` |
| #94 | `language` | `ru` | `uk` |
| #96 | `details.error_code` | `EXPORT_500` | `500` |

Ticket #96 suggests a **possible** overgeneralization of the HTTP-code normalization rule: the model returned the numeric suffix rather than the complete application-specific code. This is a hypothesis, not a verified causal finding.

### Qwen3 v2 — Persistent and New Issues

Qwen3 v2 had **19 field mismatches** on the holdout split, compared with 24 in v1. Persistent examples include:

- #36: `priority=medium` instead of `low`, and `requires_support=true` instead of `false`.
- #38 and #86: `category=technical` instead of `other`, and `priority=medium` instead of `unknown`.
- #43, #80, and #94: `priority=high` instead of `medium`.
- #40 and #43: error messages retained surrounding quotation marks.
- #83: `invalid sequence` incorrectly placed in `details.error_code` instead of `null`.

Regressions also occurred: #50 changed to `attendance` instead of `shifts`, and #86 acquired an unsupported application value `ShiftBoard`. These errors show that better aggregate accuracy does not imply every instruction or ticket improved.

**Methodological note:** The holdout findings are documented for final analysis, **not used to revise Prompt v2**. Doing so would compromise the split's role as a final evaluation set.

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
