# Offline evaluation

Temperature: 0.0; top_p: 1.0.

Golden records: 15. Input predictions: 100. Declared total: 100.

Valid-output rate: 100/100 (100.00%).

## Field accuracy

| Field | Correct/total | Accuracy |
| --- | --- | --- |
| category | 15/15 | 100.00% |
| priority | 15/15 | 100.00% |
| application | 15/15 | 100.00% |
| language | 15/15 | 100.00% |
| requires_support | 15/15 | 100.00% |
| details.error_code | 15/15 | 100.00% |
| details.error_message | 15/15 | 100.00% |

## Latency (seconds)

Samples: 100; p50: 1.4112974999879953; p95: 6.464130240012309.

## Mismatches

`null` means explicit null; JSON quotes preserve empty strings. **MISSING/INVALID** means no usable unique prediction.

| Ticket ID | Field | Expected | Actual |
| --- | --- | --- | --- |
| — | — | No mismatches | — |

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
