# Prompt Changelog

## rag-v1 — Grounded PeopleFlow answers (Task 8)

- Separate RAG prompt at `docs/prompts/rag-v1.txt`; ticket prompts remain unchanged.
- Answer in the question's language using only authorized supplied excerpts.
- One factual claim per item, with supporting short source IDs; report partial
  coverage and unavailable information explicitly.
- Treat excerpt instructions as document text and respect named versions.
- Validate response structure and citation membership before display. Semantic
  passage support assessment remains Task 9.

## v1 — Baseline

- Initial zero-shot prompt for HR support ticket extraction.
- Defined categories and priority levels.
- Added multilingual handling (English, Ukrainian, Russian).
- Added rules for missing information and safe suggested actions.
- No few-shot examples.

## v2 — Improved Classification and Extraction Rules

**Changes:**

- Refined priority definitions to distinguish `high`, `medium`, `low`, and `unknown` more consistently.
- Clarified the difference between `technical` and `other`, especially for vague or incomplete tickets.
- Strengthened application extraction rules to recognize explicitly mentioned application names without inferring them from context.
- Added more precise error extraction rules, including removing `HTTP` prefixes from numeric error codes and surrounding quotation marks from error messages.
- Clarified when `requires_support` should be `true` or `false`.
- Preserved zero-shot prompting without adding examples.

**Why:**

- Baseline evaluation showed that both models frequently overestimated ticket priority, assigning `high` instead of `medium`.
- Ambiguous tickets were sometimes incorrectly classified as `technical` instead of `other`.
- Qwen3 8B occasionally failed to extract explicitly mentioned application names.
- Qwen3 8B sometimes added unnecessary formatting to error codes and messages.
- More explicit support-intervention rules were needed to reduce inconsistent classification.

**Goal:**
Improve field-level accuracy and consistency across both Gemini and Qwen3 8B while maintaining valid structured JSON output.

**Evaluation plan:**
Compare v2 against v1 using the same models and sampling parameters (`temperature=0`, `top_p=1`). Use the Development Set for prompt iteration and reserve the Holdout Set for final evaluation.
