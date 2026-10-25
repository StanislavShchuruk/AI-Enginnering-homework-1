# Offline evaluation

Temperature: 0.0; top_p: 1.0.

Golden records: 40. Input predictions: 100. Declared total: 100.

Valid-output rate: 100/100 (100.00%).

## Field accuracy

| Field | Correct/total | Accuracy |
| --- | --- | --- |
| category | 38/40 | 95.00% |
| priority | 33/40 | 82.50% |
| application | 40/40 | 100.00% |
| language | 39/40 | 97.50% |
| requires_support | 40/40 | 100.00% |
| details.error_code | 40/40 | 100.00% |
| details.error_message | 40/40 | 100.00% |

## Latency (seconds)

Samples: 100; p50: 2.3851341500412673; p95: 11.819117265040404.

## Mismatches

`null` means explicit null; JSON quotes preserve empty strings. **MISSING/INVALID** means no usable unique prediction.

| Ticket ID | Field | Expected | Actual |
| --- | --- | --- | --- |
| 31 | priority | "medium" | "high" |
| 38 | category | "other" | "technical" |
| 38 | priority | "unknown" | "medium" |
| 43 | priority | "medium" | "high" |
| 46 | category | "other" | "employee_profile" |
| 48 | priority | "medium" | "high" |
| 80 | priority | "medium" | "high" |
| 86 | priority | "unknown" | "medium" |
| 94 | priority | "medium" | "high" |
| 95 | language | "ru" | "uk" |

## Data issues

None.

## Scoring and excluded fields

- normalization: Nullable text uses strip().casefold(); null differs from empty string. Enums and booleans compare exactly. No punctuation or internal whitespace changes.
- scoring: Every golden ID is in every field denominator. Missing, failed, invalid, or duplicate-ID predictions are incorrect for all fields. Extra IDs affect validity only.
- validity: Valid successful HRSupportTicket outputs / max(total_tickets, result count). Absent batch entries count as invalid; malformed entries and failed outputs are invalid.
- percentiles: Linear interpolation on sorted samples at index (n-1)*p (type 7). Latency includes success-status records with finite nonnegative numeric elapsed_seconds, even if their output is invalid; booleans are excluded. No samples yields null.
- summary excluded: Free-text summaries can express the same meaning with different wording.
- suggested_actions excluded: Multiple valid action selections, phrasings, and orders are possible.
- No LLM judge is used.
