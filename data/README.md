# HR support dataset

`tickets.json` retains the array of `{id, text}` records; `golden_set.json`
retains the array of `{id, expected}` records validated by HRSupportTicket.
IDs 1–30 and the first 10 golden records are unchanged. New ticket IDs are 31–100.

## Evaluation splits

- `development_ids.json`: 15 golden IDs, including all original 10 and IDs 31–35.
  These may be used for prompt development.
- `holdout_ids.json`: 25 golden IDs. Reserve these for final evaluation; do not use
  their texts or labels for prompt optimization, demonstrations, or error-driven
  prompt changes. Filter the golden array by the relevant ID file before use.

The files define an explicit partition; existing evaluation code and historical
prediction results have not been changed to apply these splits automatically.

## Language and preservation

`ticket_languages.json` is a manually assigned inventory of IDs by predominant
language of meaningful prose. English product names and quoted errors do not
change a Ukrainian or Russian ticket's language. Original IDs 22–28 are Ukrainian
and 29–30 are Russian (the old planning notes incorrectly specified 6/3).
New tickets add 49 English, 13 Ukrainian, and 8 Russian examples for totals 70/20/10.
Tests verify the inventory and agreement with golden labels, not linguistic truth.

`original_data_hashes.json` stores SHA-256 hashes of the original record arrays,
serialized as UTF-8 JSON with sorted keys, no ASCII escaping, and compact separators.
Tests use these to detect changes to original content, independent of file whitespace.

## Annotation provenance and review

The 30 new reference labels were independently authored from the ticket texts and
annotation guidelines, without reading or copying prediction results or calling
LLM APIs. They are candidates for human review, not claims of completed manual
review. Summaries/actions follow the user's predominant language. Application
names and quoted error wording are retained; success notifications are not errors.

Review especially IDs 38 and 86: incomplete reports use other/unknown and require
support triage. ID 45 is a low-impact defect requiring support despite a workaround;
ID 46 requires HR intervention for a letter without a critical deadline. All eight
categories, four priorities, three languages and both support values occur in the
golden set. New tickets include how-to requests, typos, mixed prose, record disputes,
access failures, deadlines, and detailed reproduction steps.

Run `python -m pytest` for offline validation. No live API access is needed.
