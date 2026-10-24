# AI HR Support Assistant

A Python 3.11+ AI Engineering homework project for converting messy HR support
messages into validated JSON with Pydantic v2. Supports single-ticket and sequential
batch processing through OpenRouter or local Ollama, with offline mocked tests.
See [project context](docs/PROJECT_CONTEXT.md) for dataset requirements,
planned evaluation, and future RAG and agent work.

The inherited mock command still echoes prompts offline. The parse-ticket command
calls the selected provider only when you explicitly run it. No evaluation pipeline is included.

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
