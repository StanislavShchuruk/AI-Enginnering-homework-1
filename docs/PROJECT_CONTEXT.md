# AI HR Support Assistant

## Goal

Parse unstructured HR support tickets into validated JSON and eventually provide
preliminary troubleshooting. The current AI Engineering homework focuses on
structured outputs, model evaluation, and prompt engineering.

## Current dataset

- 100 synthetic HR support messages: 70 English, 20 Ukrainian, 10 Russian.
- 40 reference labels: 15 development examples and 25 holdout examples.
- Existing 30 tickets and 10 labels are preserved; all original labels are in development.
- See data/README.md for split usage, language inventory, and review status.

## Agreed output schema

All fields must be present, including nullable fields. No extra fields are allowed.

| Field | Type / values |
| --- | --- |
| summary | string |
| category | authentication, absence, attendance, shifts, payroll, employee_profile, technical, other |
| priority | low, medium, high, unknown |
| application | string or null |
| language | en, uk, ru |
| requires_support | boolean |
| details | object with required error_code and error_message fields, each string or null |
| suggested_actions | list of strings, zero to three items |

The models live in src/ai_project/models.py. JSON parsing uses
HRSupportTicket.model_validate_json; JSON Schema is available through
HRSupportTicket.model_json_schema().

## Planned comparison and evaluation

Compare a hosted LLM provider with a local model served through Ollama.
OpenRouter is the hosted service currently used during experimentation;
the comparison models are not finalized.

Metrics:

- Field accuracy against the golden set.
- Schema validity.
- Latency p50 and p95.
- Estimated cost per 1,000 documents.

Metric implementation and detailed scoring rules are deferred.

## Current implementation scope

Phase 1 adds single-ticket OpenRouter parsing through the OpenAI Python SDK,
strict JSON Schema requests, Pydantic response validation, bounded transient
retries, and offline mocked tests. The inherited mock CLI remains available.
The existing schema is packaged at src/ai_project/models.py; the preexisting
models/models.py copy is retained unchanged. The current v1 prompt is stored at
docs/prompts/v1.txt, with prompts/v1.txt supported as the primary location.
The original provider implementation phase excluded dataset changes. The separately
authorized dataset extension now contains 100 tickets and 40 reference labels;
prompts, provider implementations, and prediction results remain unchanged. Sequential batch
processing is now supported through parse-all, reusing single-ticket parsing and
saving atomic incremental results. No automatic resume is implemented.
Live API requests require explicit approval; automated tests use mocks only.

Local Ollama is supported through the existing OpenAI SDK at a loopback /v1 endpoint.
Both parse-ticket and parse-all accept --provider openrouter|ollama (default openrouter).
The default local model is qwen3:8b. Requests disable thinking through
reasoning_effort=none and validate only final message content using the unchanged
AIService. Schema validation failures are not repaired. Ollama settings come from
the process environment without reading .env or requiring a hosted API key.

## Future extensions

- Versioned prompts stored separately from application code.
- RAG-based troubleshooting using relevant HR support knowledge.
- Agentic troubleshooting workflows.
