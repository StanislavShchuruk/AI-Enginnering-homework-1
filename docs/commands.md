# Commands and experiment reproduction

Run commands from the repository root in PowerShell. Python 3.11+ is required.

## Installation and environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
# Create configuration only if it does not already exist.
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Set `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` locally. Keep credentials out of
version control. For local inference, install/start Ollama and make the configured
model available:

```powershell
ollama pull qwen3:8b
# In another terminal, if the Ollama service is not already running:
ollama serve
```

Configuration names are documented in `.env.example`:

| Provider | Settings |
| --- | --- |
| OpenRouter | `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_TIMEOUT_SECONDS`, `OPENROUTER_MAX_RETRIES`, `OPENROUTER_TEMPERATURE`, `OPENROUTER_TOP_P` |
| Ollama | `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT_SECONDS`, `OLLAMA_TEMPERATURE`, `OLLAMA_TOP_P` |

The existing provider uses OpenRouter's fixed endpoint. Ollama URLs must be
loopback HTTP(S), optionally ending in `/v1`. Its default model is `qwen3:8b`.
Process environment settings take precedence over `.env`. Parsing commands load
settings through the existing provider loaders. Reproduction reads the project
`.env` into a mapping and overlays process settings without changing either the
file or global environment. It explicitly overrides only temperature and top_p
for each experiment. Model names in filenames are historical labels: the configured
model is preserved and recorded, even if it differs from `qwen3:8b`.

Live parsing/reproduction invokes providers and OpenRouter may incur charges.
The examples below describe commands to run deliberately; offline evaluation,
comparison, and mocked tests do not call either provider.

## CLI reference

`python -m ai_project` and the installed `ai-project` entry point are equivalent.
Every command supports `-h` / `--help`.

| Command | Arguments |
| --- | --- |
| `python -m ai_project "text"` | Legacy positional prompt; offline mock by default. `AI_PROVIDER` and `AI_MODEL` configure this legacy path. |
| `parse-ticket` | Required `--ticket-id INTEGER`; optional `--provider openrouter\|ollama` (default openrouter), `--prompt-version v1\|v2` (default v1), `--project-root PATH` (default current directory). |
| `parse-all` | Required `--output PATH`; optional provider/version/project-root as above, `--overwrite` to replace existing output. |
| `eval` | Required `--predictions JSON`, `--golden JSON`; optional `--ids-file JSON`, `--output MD_OR_JSON`, `--overwrite`. Without output, prints a console summary. |
| `compare` | Required `--predictions JSON [JSON ...]`, `--golden JSON`, `--output MD`; optional `--pricing JSON`, `--power-watts NUMBER`, `--electricity-usd-per-kwh NUMBER`. Output must be a new Markdown file. |
| `reproduce` | Optional `--eval-only` or `--force`; they are mutually exclusive. Uses `experiments.json` in the current project root. |

## Single ticket and full batch

```powershell
python -m ai_project parse-ticket --provider openrouter --ticket-id 1 --prompt-version v2
python -m ai_project parse-ticket --provider ollama --ticket-id 1 --prompt-version v1
python -m ai_project parse-all --provider openrouter --prompt-version v2 --output results/manual_openrouter_v2.json
python -m ai_project parse-all --provider ollama --prompt-version v2 --output results/manual_ollama_v2.json
```

For each version, prompt loading checks `prompts/<version>.txt` first and then
`docs/prompts/<version>.txt`. Neither command changes prompt contents. Batch parsing
is sequential and incrementally saves results; a failed ticket does not abort the
underlying batch, but produces a nonzero CLI exit. The reproduction workflow
rejects any such batch and stops before starting another experiment.

## Evaluation: full, Development, and Holdout

```powershell
python -m ai_project eval --predictions results/openrouter_v2.json --golden data/golden_set.json --output results/manual_full_v2.md
python -m ai_project eval --predictions results/openrouter_v2.json --golden data/golden_set.json --ids-file data/development_ids.json --output results/manual_development_v2.md
python -m ai_project eval --predictions results/openrouter_v2.json --golden data/golden_set.json --ids-file data/holdout_ids.json --output results/manual_holdout_v2.json
```

Full evaluation scores all 40 golden labels; Development scores 15 and Holdout
scores 25. ID files must be nonempty arrays of unique integers present in the golden
set. Field accuracy and mismatches use selected IDs, while validity and latency
always cover the entire prediction batch. Reports explicitly preserve this distinction.
Missing/failed/invalid or duplicate-ID predictions count as incorrect for selected
fields. Free-text summary/actions are excluded from exact-match field scoring.
Reserve Holdout for final evaluation; do not use it for prompt optimization.

## Model comparison

```powershell
python -m ai_project compare --predictions results/openrouter_v1.json results/ollama_qwen3_8b_v1.json --golden data/golden_set.json --output results/manual_comparison.md
python -m ai_project compare --predictions results/openrouter_v1.json results/ollama_qwen3_8b_v1.json --golden data/golden_set.json --pricing config/pricing.json --power-watts 150 --electricity-usd-per-kwh 0.10 --output results/manual_comparison_costs.md
```

`compare --pricing` accepts the same configuration shown below, including electricity
settings. Legacy JSON mapping model names directly to token rates is also supported.
Explicit `--power-watts` and `--electricity-usd-per-kwh` flags override the corresponding
file values, including when a flag is zero.

Both normal reproduction and `reproduce --eval-only` automatically load
`config/pricing.json` relative to the project root. Reproduction uses this format:

```json
{
  "models": {
    "google/gemini-3.1-flash-lite": {
      "input_usd_per_million": 0.25,
      "output_usd_per_million": 1.50
    }
  },
  "power_watts": 500,
  "usd_per_kwh": 0.09557
}
```

`models` is required and validates each entry using `TokenPrices`: both rates
must be numeric, finite, and nonnegative, with no extra fields. Use the exact
configured model names as keys; an empty `models` object is valid.
`power_watts` and `usd_per_kwh` use `Electricity` validation: optional or null,
otherwise numeric, finite, and nonnegative. Unknown configuration fields are rejected.
A missing, unreadable, or invalid pricing file stops reproduction before inference
or report writes.

Both validated configurations are passed to the consolidated comparison. Missing
model prices or electricity settings produce N/A; local API fees remain zero.
With the configuration above, `python -m ai_project reproduce --eval-only`
regenerates `results/reproduction/comparison.md` with OpenRouter token costs and
Ollama electricity costs from saved predictions, without provider calls.
Electricity costs use 500 W and $0.09557/kWh applied to recorded elapsed time,
scaled to 1,000 attempted documents.

## Sampling

Standalone parsing reads sampling settings from the provider configuration; it has
no temperature/top_p CLI flags. For a one-off PowerShell session:

```powershell
$env:OPENROUTER_TEMPERATURE = '0.3'
$env:OPENROUTER_TOP_P = '0.9'
python -m ai_project parse-all --provider openrouter --prompt-version v1 --output results/manual_sampling.json
Remove-Item Env:OPENROUTER_TEMPERATURE
Remove-Item Env:OPENROUTER_TOP_P
```

Use `OLLAMA_TEMPERATURE` and `OLLAMA_TOP_P` for Ollama. Temperature must be in [0, 2];
top_p must be in (0, 1]. The reproduction matrix applies sampling explicitly per run,
regardless of sampling values in the environment. Other settings remain unchanged.

## Full reproduction and outputs

```powershell
python -m ai_project reproduce
# Reports only: no provider settings, credentials, or API access needed.
python -m ai_project reproduce --eval-only
# Deliberately rerun all inference and replace the configured prediction files.
python -m ai_project reproduce --force
```

`experiments.json` defines the sequential order and named outputs:

| Order | Provider | Prompt | Temperature | top_p | Prediction output |
| --- | --- | --- | --- | --- | --- |
| 1 | OpenRouter | v1 | 0 | 1 | `results/openrouter_v1.json` |
| 2 | Ollama | v1 | 0 | 1 | `results/ollama_qwen3_8b_v1.json` |
| 3 | OpenRouter | v2 | 0 | 1 | `results/openrouter_v2.json` |
| 4 | Ollama | v2 | 0 | 1 | `results/ollama_qwen3_8b_v2.json` |
| 5 | OpenRouter | v1 | 0.3 | 0.9 | `results/openrouter_v1_t03_p09.json` |
| 6 | Ollama | v1 | 0.3 | 0.9 | `results/ollama_qwen3_8b_v1_t03_p09.json` |

Generated reports are always regenerated under `results/reproduction/`:

- `<prediction_stem>_full.md`: six full-set reports.
- `<prediction_stem>_development.md` and `<prediction_stem>_holdout.md`: eight
  reports for the four temperature=0, top_p=1 runs.
- `comparison.md`: one consolidated full-set comparison of all six runs.

The total is 15 reports. `docs/evaluation_report.md` remains manually maintained
and is never an output destination. No historical reports elsewhere are overwritten.
Prediction paths must be unique JSON filenames directly inside `results/`;
configurations must be unique and contain only supported fields/providers/prompts.
Splits must contain 15/25 unique golden IDs without overlap. The full golden set
must contain 40 schema-valid labels and reference existing input tickets.

## Safe reruns and failures

By default, existing predictions are reused only when they parse, are complete,
match all current ticket IDs, contain valid successful outputs and timings, and
match the configured provider/prompt/sampling metadata. Recorded configured model
names are required. Skip validation does not verify ticket/prompt content hashes
or compare the recorded model to newly loaded settings. After editing input text,
prompts, or model settings, use `--force` deliberately to obtain fresh predictions.

Invalid or incomplete existing files cause an error with a `--force` hint; they
are never silently overwritten. `--eval-only` requires every saved run and rejects
invalid files, without loading provider settings or calling providers. It cannot
be combined with `--force`. Back up predictions before a forced rerun if needed.

All inputs and destinations are preflighted before inference; settings are loaded
only for runs needing inference. Runs and ticket requests are sequential. Any failed
batch stops the workflow, and failures return a nonzero exit with no completion
message. Incremental predictions may remain for diagnosis; reproduction does not
resume within a batch. Reports are prepared after successful experiments and then
written; a write failure may leave some updated reports, but is never reported as
success. Provider failures are summarized without exposing response bodies.

The workflow repeats configurations and scoring, not guaranteed byte-identical
model outputs: hosted model revisions, hardware, nondeterminism, and load can vary.

## Offline validation

```powershell
python -m pytest -q
python -m pytest -q tests/test_reproduction.py
python -m ruff check src tests
```

Tests use synthetic fixtures and mocked providers. No paid or local inference is
needed to validate the orchestration.
