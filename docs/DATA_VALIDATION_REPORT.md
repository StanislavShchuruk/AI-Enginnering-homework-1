# Dataset validation report

Validated on 2026-10-25. No external LLM APIs were called and no prediction files
were used to author reference labels. Prompts, providers and prediction results
were not modified.

- `python -m pytest -q tests/test_datasets.py -p no:cacheprovider`: **11 passed**.
- Full offline suite (`python -m pytest -q --tb=short`): **153 passed, 1 failed**,
  plus **21 passing unittest subtests**. The failure is
  `tests/test_ollama.py::test_defaults_do_not_load_secrets`: the unchanged
  configuration calls the mocked dotenv loader although the test expects no call.
  The initial sandbox run had temporary-directory permission errors; the full
  suite was rerun outside the sandbox to obtain the result above.

The dataset has 100 unique, sequential integer ticket IDs (1–100), 40 valid
HRSupportTicket reference labels, and language totals of 70 English, 20 Ukrainian,
and 10 Russian. Language totals use the manually authored ID inventory; tests
cannot independently prove linguistic correctness.

All original 30 ticket records and 10 labels match their pre-extension canonical
SHA-256 hashes. Every golden ID references a ticket. The 15 development and 25
holdout IDs are unique, non-overlapping, and partition the golden set, with the
original 10 in development. All eight categories and four priorities are represented.

The new labels are independently authored reference candidates for human review;
structural validation does not establish semantic correctness or human approval.
See data/README.md for split restrictions and review notes. Historical prediction
results cover the previous dataset and have not been regenerated.
