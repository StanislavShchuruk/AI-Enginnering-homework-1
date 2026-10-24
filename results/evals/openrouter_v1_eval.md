# Offline evaluation

Temperature: 0.0; top_p: 1.0.

Golden records: 10. Input predictions: 30. Declared total: 30.

Valid-output rate: 30/30 (100.00%).

## Field accuracy

| Field | Correct/total | Accuracy |
| --- | --- | --- |
| category | 10/10 | 100.00% |
| priority | 10/10 | 100.00% |
| application | 10/10 | 100.00% |
| language | 10/10 | 100.00% |
| requires_support | 10/10 | 100.00% |
| details.error_code | 10/10 | 100.00% |
| details.error_message | 10/10 | 100.00% |

## Latency (seconds)

Samples: 30; p50: 1.2401544999884209; p95: 1.5298268499929688.

## Mismatches

`null` means explicit null; JSON quotes preserve empty strings. **MISSING/INVALID** means no usable unique prediction.

| Ticket ID | Field | Expected | Actual |
| --- | --- | --- | --- |
| — | — | No mismatches | — |

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
