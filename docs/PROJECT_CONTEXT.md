# AI HR Support Assistant

## Goal

Parse unstructured HR support tickets into validated JSON and eventually provide
preliminary troubleshooting. The current AI Engineering homework focuses on
structured outputs, model evaluation, and prompt engineering.

## Planned data

- Input: 30 synthetic, realistic, messy HR support messages.
- Languages: 21 English, 6 Ukrainian, and 3 Russian messages.
- Golden set: 10 manually reviewed examples from the 30 messages.

These are requirements for future dataset work; no dataset is generated yet.

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
Do not change dataset/golden labels or v1 prompt, generate datasets, implement
evaluations, prompt v2, or repair logic in this phase. Sequential batch
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
