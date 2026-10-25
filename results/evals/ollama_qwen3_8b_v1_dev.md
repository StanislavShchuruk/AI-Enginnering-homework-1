# Offline evaluation

Temperature: 0.0; top_p: 1.0.

Golden records: 15. Input predictions: 100. Declared total: 100.

Valid-output rate: 100/100 (100.00%).

## Field accuracy

| Field | Correct/total | Accuracy |
| --- | --- | --- |
| category | 15/15 | 100.00% |
| priority | 9/15 | 60.00% |
| application | 11/15 | 73.33% |
| language | 15/15 | 100.00% |
| requires_support | 14/15 | 93.33% |
| details.error_code | 14/15 | 93.33% |
| details.error_message | 14/15 | 93.33% |

## Latency (seconds)

Samples: 100; p50: 3.2133695000084117; p95: 3.960791689995676.

## Mismatches

`null` means explicit null; JSON quotes preserve empty strings. **MISSING/INVALID** means no usable unique prediction.

| Ticket ID | Field | Expected | Actual |
| --- | --- | --- | --- |
| 1 | priority | "medium" | "high" |
| 1 | application | "HR Portal" | null |
| 1 | details.error_message | "Incorrect password" | "'incorrect password'" |
| 7 | priority | "medium" | "high" |
| 7 | application | "HR Portal" | null |
| 7 | details.error_code | "500" | "HTTP 500" |
| 14 | priority | "medium" | "high" |
| 17 | priority | "low" | "medium" |
| 17 | requires_support | false | true |
| 18 | priority | "medium" | "high" |
| 24 | application | "HR portal" | null |
| 31 | priority | "medium" | "high" |
| 34 | application | "Shifts" | null |

## Data issues

None.

## Scoring and excluded fields

- normalization: Nullable text uses strip().casefold(); null differs from empty string. Enums and booleans compare exactly. No punctuation or internal whitespace changes.
- scoring: Every selected golden ID is in every field denominator. Missing, failed, invalid, or duplicate-ID predictions are incorrect for all fields. Extra IDs affect validity only.
- validity: Valid successful HRSupportTicket outputs / max(total_tickets, result count). Absent batch entries count as invalid; malformed entries and failed outputs are invalid.
- percentiles: Linear interpolation on sorted samples at index (n-1)*p (type 7). Latency includes success-status records with finite nonnegative numeric elapsed_seconds, even if their output is invalid; booleans are excluded. No samples yields null.
- scope: Field accuracy and mismatches use selected golden IDs: [1, 2, 7, 10, 12, 14, 17, 18, 23, 24, 31, 32, 33, 34, 35]. Valid-output rate and latency use the entire prediction batch, without ID filtering.
- summary excluded: Free-text summaries can express the same meaning with different wording.
- suggested_actions excluded: Multiple valid action selections, phrasings, and orders are possible.
- No LLM judge is used.
