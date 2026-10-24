# AI HR Support Assistant

A Python 3.11+ AI Engineering homework project for converting messy HR support
messages into validated JSON with Pydantic v2. Supports single-ticket and sequential
batch processing through OpenRouter or local Ollama, with offline mocked tests.
See [project context](docs/PROJECT_CONTEXT.md) for dataset requirements,
planned evaluation, and future RAG and agent work.

The inherited mock command still echoes prompts offline. The parse-ticket command
calls the selected provider only when you explicitly run it. Saved batch results can be
evaluated entirely offline.

## Quick start

Open a terminal in this directory. On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
ai-project "Hello, AI!"
```

On macOS/Linux, activate with `source .venv/bin/activate` instead.
You can also run `python -m ai_project "Hello, AI!"` after installation.

Expected output: `[mock] You said: Hello, AI!`

## Configuration

Settings read process environment variables. Defaults are `AI_PROVIDER=mock`
and `AI_MODEL=demo`. The model setting is reserved for a future real provider;
the mock provider does not use it. `.env.example` documents these variables;
copying it to `.env` does not load them automatically.

PowerShell example:

```powershell
$env:AI_PROVIDER = "mock"
```

Keep API keys in environment variables and out of source control.

## Project structure

```text
src/ai_project/
  models.py       Pydantic ticket models and enums
  config.py       Environment settings
  providers.py    Provider interface and offline mock
  service.py      Application logic and input validation
  cli.py          Command-line interface
tests/            Unit tests
docs/             Persistent project context
data/             Local datasets (ignored by Git)
models/           Local model artifacts (ignored by Git)
```

## Development

```powershell
python -m unittest discover -s tests -v
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

To run without installing the package, set `$env:PYTHONPATH = "src"` in
PowerShell, then run `python -m ai_project "Hello"` or the unit test command.
On macOS/Linux, use `PYTHONPATH=src python -m unittest discover -s tests -v`.

## Phase 1: parse one ticket with OpenRouter

Install from the project root in your virtual environment:

```powershell
python -m pip install -e ".[dev]"
```

Set OPENROUTER_API_KEY and OPENROUTER_MODEL in your process environment.
The current config also loads .env from the working directory at application runtime.
Tests mock that loader and never read the file. .env.example documents names and
defaults only; it must not contain real secrets. To enter the key without putting
it in shell history (PowerShell 7):

```powershell
$env:OPENROUTER_API_KEY = Read-Host "OpenRouter API key" -MaskInput
$env:OPENROUTER_MODEL = "openai/gpt-4o-mini"
```

Choose a model/endpoint that supports Structured Outputs and all supplied parameters.
The example model is a starting choice, not a guarantee of endpoint availability.
Run the first manual request yourself:

```powershell
ai-project parse-ticket --ticket-id 1 --prompt-version v1
```

Equivalent: python -m ai_project parse-ticket --ticket-id 1 --prompt-version v1.
Run from the project root, or supply --project-root with its absolute path.
This sends one selected ticket to OpenRouter and can incur API charges.

The command reads data/tickets.json by integer ID. It loads prompts/v1.txt when
present; this checkout currently stores the unchanged prompt at docs/prompts/v1.txt,
which is the supported alternate location. Only v1 is accepted. Prompts are external
project files, not embedded in the installed wheel.

The provider sends HRSupportTicket.model_json_schema() with json_schema and
strict=true, plus provider.require_parameters=true to require compatible routing.
Unsupported requests fail explicitly: no json_object/text fallback and no repair.
The service validates the returned content with HRSupportTicket.model_validate_json().
Output is a JSON envelope containing ticket, elapsed_seconds (request, retries,
and validation), returned model, and usage (null when unavailable).

Optional environment settings:

| Name | Default | Allowed values |
| --- | --- | --- |
| OPENROUTER_TEMPERATURE | 0 | 0 through 2 |
| OPENROUTER_TOP_P | 1 | greater than 0, at most 1 |
| OPENROUTER_TIMEOUT_SECONDS | 30 | positive finite seconds per SDK request |
| OPENROUTER_MAX_RETRIES | 2 | integer 0 through 5, additional attempts |

Retries apply only to 429, 5xx, connection failures, and network timeouts. The SDK's
built-in retries are disabled; exponential delays are capped at 8 seconds. Timeout
is not a total wall-clock deadline. Authentication, unsupported schema/parameters,
refusals, truncated responses, and invalid JSON are not retried. Errors preserve
HTTP status and attempt count without printing provider response bodies or keys;
original SDK exceptions remain available as chained causes to callers.

```powershell
python -m pytest -q
```

All API tests mock the SDK and use dummy keys; no live API call is needed for tests.

## Sequential batch processing

From the project root, after configuring OpenRouter as above, run:

```powershell
python -m ai_project parse-all --prompt-version v1 --output results/openrouter_v1.json
```

This makes sequential requests for every input ticket using the same service,
Pydantic validation, and provider retries as parse-ticket. It can incur API costs.
--output is required. Existing output is refused unless you deliberately add
--overwrite; use a fresh filename to retain previous runs. Relative output paths
are relative to the working directory. --project-root selects the input project.
Datasets and prompt files cannot be used as output destinations.

The output format is:

```json
{
  "metadata": {
    "provider": "openrouter",
    "configured_model": "openai/gpt-4o-mini",
    "prompt_version": "v1",
    "temperature": 0.0,
    "top_p": 1.0,
    "timestamp": "2026-10-18T12:00:00+00:00"
  },
  "total_tickets": 30,
  "completed": false,
  "results": []
}
```

Each results entry contains ticket_id, status (success or error), output (the full
validated HRSupportTicket on success, otherwise null), elapsed_seconds, model,
usage, and error (null on success). Successful model/usage values come from the
provider response. Failed entries use the configured model and null usage because
the service did not return a successful TicketResult. Error messages use safe
fixed descriptions, optionally preserving an HTTP status; raw exception bodies,
response text, and credentials are never written to error messages or metadata.

An initial snapshot is published before processing. Each completed result is saved
in input order by flushing a temporary file in the output directory and atomically
replacing the destination. Filesystem write errors stop the run while preserving
the previous snapshot. Individual ticket errors are saved and processing continues.
Ctrl+C leaves the last saved results with completed=false; the interrupted ticket
may already have incurred API costs. completed=true means all tickets were attempted,
including failures. Exit code is 1 if any tickets failed, otherwise 0. There is no
automatic resume: rerunning requires a new path or --overwrite and processes all
tickets again. Do not run concurrent writers against the same output file.

## Local Ollama

Install Ollama from https://ollama.com/download, then prepare the local server/model:

```powershell
ollama pull qwen3:8b
ollama serve
```

If the Ollama desktop application is already serving localhost:11434, skip
ollama serve. Run the parser in a separate terminal from the project root:

```powershell
python -m ai_project parse-ticket --provider ollama --ticket-id 1 --prompt-version v1
python -m ai_project parse-all --provider ollama --prompt-version v1 --output results/ollama_v1.json
```

The batch command processes all 30 tickets in the current dataset. Existing output
is protected; choose a new path or explicitly supply --overwrite for another run.
Keep --provider openrouter for hosted processing; omitting --provider preserves the
previous OpenRouter default. Both providers use the same AIService, HRSupportTicket
validation, v1 prompt loading, and atomic batch progress saving.

Ollama reads only these process environment variables (not .env); no API key is needed:

| Name | Default |
| --- | --- |
| OLLAMA_BASE_URL | http://localhost:11434 |
| OLLAMA_MODEL | qwen3:8b |
| OLLAMA_TEMPERATURE | 0 |
| OLLAMA_TOP_P | 1 |
| OLLAMA_TIMEOUT_SECONDS | 120 |

For example, use $env:OLLAMA_MODEL = "qwen3:8b" in PowerShell. Sampling/timeout
validation is shared with OpenRouter. OLLAMA_BASE_URL accepts loopback HTTP(S)
addresses, with optional /v1; /v1 is appended exactly once. Remote endpoints,
embedded credentials, query parameters, and custom API paths are rejected. Local
requests ignore environment proxies and do not follow redirects, preventing provider
mix-ups. OpenRouter always uses its fixed hosted URL. The local SDK uses the
non-secret placeholder key "ollama" and has automatic retries disabled; Ollama
defaults to one attempt with the configured timeout. OpenRouter retry settings
continue to apply only to OpenRouter.

Use a recent Ollama version supporting JSON Schema response_format and
reasoning_effort="none". For Qwen3 this requests thinking disabled; any separate
reasoning_content is ignored. Only message.content reaches Pydantic. If thinking
text is mixed into content, validation fails without stripping or repairing it.
Unsupported schema/thinking options fail explicitly rather than silently changing
formats. See [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility).

Successful batch records now also contain provider, temperature, and top_p alongside
the returned model, elapsed_seconds, and usage. Missing token counts are null; usage
itself is null if absent. Run metadata retains configured_model. Failed records use
the configured model and a provider-specific sanitized error; raw reasoning and
provider error bodies are never persisted. The existing result fields remain intact.

Offline unit tests without reading the real datasets:

```powershell
python -m pytest -q tests/test_app.py tests/test_models.py tests/test_openrouter.py tests/test_batch.py tests/test_ollama.py
```

## Offline evaluation

Evaluate the existing OpenRouter and Ollama baselines without contacting either provider:

```powershell
python -m ai_project eval --predictions results/openrouter_v1.json --golden data/golden_set.json --output results/openrouter_v1_eval.md
python -m ai_project eval --predictions results/ollama_qwen3_8b_v1.json --golden data/golden_set.json --output results/ollama_qwen3_8b_v1_eval.md
```

Omit `--output` for a console summary only. Use a new `.json` output path for a
machine-readable report, or `.md` for a human-readable Markdown report. Both print
the same concise console summary. Add `--overwrite` to replace an existing report.
Predictions and golden data cannot be used as output destinations, even with `--overwrite`.
JSON reports preserve available run and per-record provider/model/prompt/sampling metadata.
The eval command does not load provider settings, read `.env`, or make API calls.

Records match by integer `ticket_id` to golden `id`, independently of list order.
Each of the seven scored fields uses **all golden records** as its denominator:
category, priority, application, language, requires_support, details.error_code,
and details.error_message. Missing, failed, schema-invalid, and duplicate-ID
predictions count as incorrect in every field. Duplicate golden IDs and malformed
golden outputs are rejected; duplicate prediction IDs are reported and never
arbitrarily resolved. Extra prediction IDs do not enter field accuracy.

Enums and booleans compare exactly. Nullable text (application and both details
fields) uses Python `strip().casefold()` to ignore surrounding whitespace and case,
including Unicode case folding. Null remains distinct from an empty string.
Punctuation, quotes, and internal whitespace are preserved. Detailed mismatches
retain the original values. Markdown escapes table delimiters, HTML characters,
backticks, and backslashes; JSON quotes distinguish empty strings from null, and
missing/unusable predictions have an explicit marker.

Valid-output rate covers the entire batch, including non-golden tickets: successful
outputs must validate against `HRSupportTicket` and have an integer ticket ID.
The denominator is `max(total_tickets, len(results))`, so declared but absent
entries count as invalid and extra entries cannot disappear from the denominator.
Duplicate entries remain individual input predictions for schema validity, but are
unusable for golden matching. Failed, missing, and invalid outputs are invalid.
Count inconsistencies, malformed entries, missing IDs, incomplete batches, and
invalid timings appear in report issues. Malformed top-level structures/counts
are rejected. An empty validity denominator yields null/N/A.

Latency uses all success-status predictions with finite, nonnegative numeric
`elapsed_seconds`, even if schema validation fails. Booleans and numeric strings
are excluded. Percentiles use linear interpolation (type 7): sort the n samples,
locate `(n - 1) * p`, then interpolate between neighboring samples for p=0.50/0.95.
One sample returns itself; no samples yields null. Failures are excluded from latency.

`summary` and `suggested_actions` are excluded from automated exact-match accuracy:
equivalent summaries can use different wording, and several action selections,
orders, and phrasings can be appropriate. They still participate in schema validation.
No LLM judge is used. Run all offline tests with `python -m pytest`.

## Offline multi-run comparison and cost estimates

Compare saved runs using the same golden set, without reading `.env` or contacting
OpenRouter or Ollama:

```powershell
python -m ai_project compare --predictions results/openrouter_v1.json results/ollama_qwen3_8b_v1.json --golden data/golden_set.json --output results/comparison.md
```

The output must be a new `.md` file. Existing files are protected; choose a new
filename for another comparison. Predictions, tickets, golden labels, and prompts
are never updated. The table includes run metadata, golden document count, input
record count, aggregate and field-level accuracy, valid-output rate, and latency
p50/p95. Accuracy and latency reuse the offline evaluator described above.

Hosted token costs require an explicit model-keyed `--pricing` JSON file. Each key
must match `metadata.configured_model`. For example, a **hypothetical illustration,
not current provider prices**, saved as `pricing.example.json`:

```json
{
  "your-configured-model-id": {
    "input_usd_per_million": 2.0,
    "output_usd_per_million": 4.0
  }
}
```

Supply rates you have chosen for the recorded model and run; no prices are fetched
or assumed. Both prices must be finite nonnegative numbers. Explicit zero is
allowed. The report prints the configured rates for review.

```powershell
python -m ai_project compare --predictions results/openrouter_v1.json results/ollama_qwen3_8b_v1.json --golden data/golden_set.json --pricing pricing.example.json --power-watts 200 --electricity-usd-per-kwh 0.25 --output results/comparison_with_costs.md
```

The power and electricity values above are also illustrative. Local options apply
to every Ollama run in that comparison; compare separately if machines or tariffs
differ. The report shows Ollama API fee as $0, independently of whether electricity
can be estimated. Local inference still has energy, hardware, and operating costs.

Hosted USD per 1,000 attempted documents is:
`(sum(prompt_tokens) * input_price + sum(completion_tokens) * output_price) / 1_000_000 * 1_000 / record_count`.
Usage comes from each saved record's `usage.prompt_tokens` and
`usage.completion_tokens`, including failed records. Missing prices, missing or
invalid usage (even for one failure), or an incomplete/empty/count-inconsistent
batch yield N/A, never an assumed zero. Prices apply to the configured model;
recorded response model names are listed to expose aliases or routing differences.
These are **estimated token-based costs, not actual billed charges**. Unrecorded
retries, caching, discounts, routing fees, taxes, and billing adjustments are not
accounted for. Failed requests can incur charges not present in saved usage.

Local estimated electricity USD per 1,000 attempted documents is:
`power_watts / 1_000 * sum(elapsed_seconds) / 3_600 * electricity_usd_per_kwh * 1_000 / record_count`.
It uses all measured record times, including failures. Missing power, tariff, or
any timing yields N/A; incomplete/empty/count-inconsistent batches also yield N/A.
Power and tariff must be finite nonnegative numbers. Summing record times assumes
sequential processing and approximates active processing energy; it is not a
measurement of electricity use. It excludes idle time outside the records,
hardware amortization, and other operating costs. Latency retains the evaluator's
success-only sampling, whereas costs include all recorded attempts. Different
hardware, system load, model routing, and missing metadata limit comparisons.
