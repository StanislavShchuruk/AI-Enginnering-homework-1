# Offline evaluation

Temperature: 0.0; top_p: 1.0.

Golden records: 25. Input predictions: 100. Declared total: 100.

Valid-output rate: 100/100 (100.00%).

## Field accuracy

| Field | Correct/total | Accuracy |
| --- | --- | --- |
| category | 20/25 | 80.00% |
| priority | 16/25 | 64.00% |
| application | 21/25 | 84.00% |
| language | 25/25 | 100.00% |
| requires_support | 23/25 | 92.00% |
| details.error_code | 23/25 | 92.00% |
| details.error_message | 23/25 | 92.00% |

## Latency (seconds)

Samples: 100; p50: 3.2133695000084117; p95: 3.960791689995676.

## Mismatches

`null` means explicit null; JSON quotes preserve empty strings. **MISSING/INVALID** means no usable unique prediction.

| Ticket ID | Field | Expected | Actual |
| --- | --- | --- | --- |
| 36 | priority | "low" | "medium" |
| 36 | requires_support | false | true |
| 37 | priority | "medium" | "high" |
| 37 | details.error_code | "502" | "HTTP 502" |
| 38 | category | "other" | "technical" |
| 38 | priority | "unknown" | "medium" |
| 40 | details.error_message | "File too large" | "'File too large'" |
| 43 | priority | "medium" | "high" |
| 43 | application | "HR Portal" | null |
| 43 | details.error_message | "Account disabled" | "'Account disabled'" |
| 44 | category | "employee_profile" | "technical" |
| 45 | application | "ESS" | null |
| 46 | category | "other" | "employee_profile" |
| 46 | priority | "medium" | "high" |
| 47 | application | "ESS" | null |
| 48 | priority | "medium" | "high" |
| 80 | priority | "medium" | "high" |
| 83 | details.error_code | null | "invalid sequence" |
| 84 | application | "ShiftBoard" | null |
| 86 | category | "other" | "technical" |
| 86 | priority | "unknown" | "medium" |
| 94 | priority | "medium" | "high" |
| 95 | category | "shifts" | "attendance" |
| 95 | requires_support | false | true |

## Data issues

None.

## Scoring and excluded fields

- normalization: Nullable text uses strip().casefold(); null differs from empty string. Enums and booleans compare exactly. No punctuation or internal whitespace changes.
- scoring: Every selected golden ID is in every field denominator. Missing, failed, invalid, or duplicate-ID predictions are incorrect for all fields. Extra IDs affect validity only.
- validity: Valid successful HRSupportTicket outputs / max(total_tickets, result count). Absent batch entries count as invalid; malformed entries and failed outputs are invalid.
- percentiles: Linear interpolation on sorted samples at index (n-1)*p (type 7). Latency includes success-status records with finite nonnegative numeric elapsed_seconds, even if their output is invalid; booleans are excluded. No samples yields null.
- scope: Field accuracy and mismatches use selected golden IDs: [36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 80, 81, 82, 83, 84, 85, 86, 94, 95, 96]. Valid-output rate and latency use the entire prediction batch, without ID filtering.
- summary excluded: Free-text summaries can express the same meaning with different wording.
- suggested_actions excluded: Multiple valid action selections, phrasings, and orders are possible.
- No LLM judge is used.
