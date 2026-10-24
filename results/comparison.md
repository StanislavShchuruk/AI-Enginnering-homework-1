# Offline run comparison

All costs are USD estimates per 1,000 attempted documents; token estimates are not actual billed charges. N/A means unavailable, not zero.

| Run | Provider | Model (configured) | Prompt | Temperature | top_p | Evaluated documents (golden) | Input records | Field accuracy (correct/total) | Valid-output rate | p50 (s) | p95 (s) | API fee / 1,000 | Electricity / 1,000 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | "openrouter" | "google/gemini-3.1-flash-lite" | "v1" | 0.0 | 1.0 | 10 | 30 | 70/70 (100.00%) | 30/30 (100.00%) | 1.240154 | 1.529827 | $0.504217 | N/A |
| 2 | "openrouter" | "google/gemini-3.1-flash-lite" | "v1" | 0.3 | 0.9 | 10 | 30 | 69/70 (98.57%) | 30/30 (100.00%) | 1.248331 | 1.917907 | $0.505117 | N/A |
| 3 | "ollama" | "qwen3:8b" | "v1" | 0.0 | 1.0 | 10 | 30 | 59/70 (84.29%) | 30/30 (100.00%) | 3.133763 | 3.822610 | $0.000000 | N/A |
| 4 | "ollama" | "qwen3:8b" | "v1" | 0.3 | 0.9 | 10 | 30 | 59/70 (84.29%) | 30/30 (100.00%) | 3.102519 | 3.862271 | $0.000000 | N/A |

## Field accuracy

| Field | Run 1 | Run 2 | Run 3 | Run 4 |
| --- | --- | --- | --- | --- |
| category | 10/10 (100.00%) | 10/10 (100.00%) | 10/10 (100.00%) | 10/10 (100.00%) |
| priority | 10/10 (100.00%) | 9/10 (90.00%) | 5/10 (50.00%) | 5/10 (50.00%) |
| application | 10/10 (100.00%) | 10/10 (100.00%) | 7/10 (70.00%) | 7/10 (70.00%) |
| language | 10/10 (100.00%) | 10/10 (100.00%) | 10/10 (100.00%) | 10/10 (100.00%) |
| requires_support | 10/10 (100.00%) | 10/10 (100.00%) | 9/10 (90.00%) | 9/10 (90.00%) |
| details.error_code | 10/10 (100.00%) | 10/10 (100.00%) | 9/10 (90.00%) | 9/10 (90.00%) |
| details.error_message | 10/10 (100.00%) | 10/10 (100.00%) | 9/10 (90.00%) | 9/10 (90.00%) |

## Runs and data issues

- Run 1: "results&#92;&#92;openrouter_v1.json". Configured-model token rates applied to all recorded usage.
  - Recorded response models: "google/gemini-3.1-flash-lite".
- Run 2: "results&#92;&#92;openrouter_v1_t03_p09.json". Configured-model token rates applied to all recorded usage.
  - Recorded response models: "google/gemini-3.1-flash-lite".
- Run 3: "results&#92;&#92;ollama_qwen3_8b_v1.json". Average power or electricity price not configured.
  - Recorded response models: "qwen3:8b".
- Run 4: "results&#92;&#92;ollama_qwen3_8b_v1_t03_p09.json". Average power or electricity price not configured.
  - Recorded response models: "qwen3:8b".

## Pricing assumptions

- "google/gemini-3.1-flash-lite": input $0.25/1M tokens; output $1.5/1M tokens.
- Local average power: None W; electricity: None USD/kWh. None means not configured.

## Methodology and limitations

- Field accuracy sums correct counts across the seven scored fields and divides by seven times the golden document count. All runs use the same golden set.
- Nullable text uses strip().casefold(); null differs from empty string. Enums and booleans compare exactly. No punctuation or internal whitespace changes.
- Every golden ID is in every field denominator. Missing, failed, invalid, or duplicate-ID predictions are incorrect for all fields. Extra IDs affect validity only.
- Valid successful HRSupportTicket outputs / max(total_tickets, result count). Absent batch entries count as invalid; malformed entries and failed outputs are invalid.
- Linear interpolation on sorted samples at index (n-1)*p (type 7). Latency includes success-status records with finite nonnegative numeric elapsed_seconds, even if their output is invalid; booleans are excluded. No samples yields null.
- summary excluded: Free-text summaries can express the same meaning with different wording.
- suggested_actions excluded: Multiple valid action selections, phrasings, and orders are possible.
- Hosted estimate: (prompt tokens × input price + completion tokens × output price) / 1,000,000 × 1,000 / input record count. Both usage counts must be recorded for every record, including failures; missing usage is never assumed zero. Rates are explicitly assigned to the configured model, including returned model aliases.
- Local API fee is $0. Electricity estimate: watts / 1,000 × summed elapsed seconds / 3,600 × USD/kWh × 1,000 / input record count. All records, including failures, need valid timing. Costs require a complete nonempty batch with matching counts.
- Local inference has hardware, energy, and operating costs. Electricity excludes idle time outside records and hardware amortization. Summed sequential processing time is an approximation, not a power measurement or parallel wall-clock time.
- Token estimates exclude unrecorded retries, discounts, caching, routing surcharges, taxes, and other billing adjustments. Failed requests may incur unrecorded charges. Latency excludes failures, whereas cost includes recorded failed attempts. Model aliases and hardware/load differences can limit comparability.
- No .env is read, no models are called, and no LLM judge is used.
