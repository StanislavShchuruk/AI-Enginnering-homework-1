# Dataset validation report

Validation performed on 2026-10-17 using python -m pytest.

Result after manual JSON fixes: 21 passed, 0 failed (plus 21 passing unittest subtests).

## Input tickets

data/tickets.json is valid JSON with a top-level array of exactly 30 objects.
All ticket IDs are unique integers.

## Golden set

data/golden_set.json is valid JSON with exactly 10 cases and unique integer IDs.
Every golden ID matches an input ticket. Every expected output validates against
the existing HRSupportTicket Pydantic model, including required nullable fields,
enum values, and the maximum of three suggested actions.

The validation code does not modify either data file or any golden label.
These checks establish structural validity, not semantic correctness of the labels.
Rerun python -m pytest after future dataset edits.
