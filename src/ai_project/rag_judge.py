"""Offline input validation, hosted judging, and human calibration of saved RAG answers."""

import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import Field, ValidationError, model_validator

from ai_project.config import Settings
from ai_project.providers import AIProvider, OpenRouterProvider, ProviderError
from ai_project.rag import RagAnswer, StrictModel, validate_citations
from ai_project.rag_evaluation import AnswerCase, RagCases
from ai_project.retrieval_evaluation import Text

PROMPT_VERSION = "rag-judge-v1"
PROMPT_PATH = Path(f"docs/prompts/{PROMPT_VERSION}.txt")


class ClaimVerdict(StrictModel):
    claim_index: int = Field(ge=1)
    support: Literal["pass", "fail"]
    reason: Text = Field(max_length=1000)


class JudgeVerdict(StrictModel):
    completeness: Literal["pass", "fail"]
    completeness_reason: Text = Field(max_length=1000)
    faithfulness: Literal["pass", "fail", "n/a"]
    faithfulness_reason: Text = Field(max_length=1000)
    claim_verdicts: list[ClaimVerdict]

    @model_validator(mode="after")
    def consistent_support(self) -> "JudgeVerdict":
        expected = (
            "n/a"
            if not self.claim_verdicts
            else "fail"
            if any(c.support == "fail" for c in self.claim_verdicts)
            else "pass"
        )
        if self.faithfulness != expected:
            raise ValueError("Faithfulness must agree with per-claim support")
        if [c.claim_index for c in self.claim_verdicts] != list(
            range(1, len(self.claim_verdicts) + 1)
        ):
            raise ValueError("Claim indices must be unique, ordered, and consecutive")
        return self


class JudgeProvider(OpenRouterProvider):
    response_model = JudgeVerdict
    schema_name = "peopleflow_judge"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_inputs(
    baseline_path: Path,
    cases_path: Path,
    human_path: Path,
) -> tuple[dict[str, Any], dict[str, AnswerCase], dict[str, dict[str, str]]]:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    suite = RagCases.model_validate_json(cases_path.read_text(encoding="utf-8"))
    if baseline.get("cases_sha256") != sha256(cases_path):
        raise ValueError("Baseline test-set hash differs from the cases file")
    if baseline.get("completed") is not True:
        raise ValueError("Baseline is incomplete")
    cases = {case.id: case for case in suite.cases}
    rows = baseline["cases"]
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)) or set(ids) != set(cases):
        raise ValueError("Baseline and test-set case IDs must match uniquely")
    valid = set()
    for row in rows:
        case = cases[row["id"]]
        if row["question"] != case.question:
            raise ValueError("Saved question differs from test set")
        if row["outcome"] != "valid_answer":
            continue
        generation = row["generation"]
        answer = RagAnswer.model_validate(generation["answer"])
        sources = generation["sources"]
        request = json.loads(generation["generation_request"])
        if (
            generation["question"] != case.question
            or request["question"] != case.question
            or request["excerpts"] != sources
            or row["sources"] != sources
            or len({s["source_id"] for s in sources}) != len(sources)
        ):
            raise ValueError("Saved generation context is inconsistent")
        validate_citations(answer, sources)
        valid.add(case.id)
    humans: dict[str, dict[str, str]] = {}
    with human_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        headers = [h.strip() for h in reader.fieldnames or []]
        if len(set(headers)) != len(headers) or set(headers) != {
            "Case",
            "Completeness",
            "Faithfulness",
            "Reason",
        }:
            raise ValueError("Unexpected human-label CSV headers")
        reader.fieldnames = headers
        for row in reader:
            # The supplied CSV has unquoted commas in its final free-text Reason.
            # Accept that legacy form without changing the source file.
            overflow = row.pop(None, [])
            if overflow:
                if headers[-1] != "Reason":
                    raise ValueError("Unquoted trailing CSV fields require Reason last")
                row["Reason"] = ",".join([row["Reason"], *overflow])
            if any(value is None for value in row.values()):
                raise ValueError("Malformed human-label CSV row")
            row = {key: value.strip() for key, value in row.items()}
            case_id = row["Case"]
            if case_id not in valid or case_id in humans:
                raise ValueError("Human case IDs must uniquely reference valid saved answers")
            if row["Completeness"] not in {"pass", "fail"} or row["Faithfulness"] not in {
                "pass",
                "fail",
                "n/a",
            }:
                raise ValueError("Invalid human verdict")
            humans[case_id] = row
    if len(humans) != 10:
        raise ValueError("Exactly 10 human-labeled answers are required")
    return baseline, cases, humans


def judge_request(case: AnswerCase, generation: dict[str, Any]) -> str:
    """Explicit allowlist: no human judgments, reasons, or baseline scores."""
    return json.dumps(
        {
            "question": case.question,
            "candidate_answer": generation["answer"],
            "excerpts": generation["sources"],
            "expectations": {
                "expected_status": case.expected_status,
                "required_facts": [
                    {
                        "id": f.id,
                        "required_fact": f.required_fact,
                        "qualifications": f.qualifications,
                    }
                    for f in case.required_facts
                ],
                "unsupported_parts": case.unsupported_parts,
            },
        },
        ensure_ascii=False,
    )


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    calibration = [r for r in rows if r["subset"] == "calibration"]
    agreement = {}
    disagreements = []
    for dimension, header in [("completeness", "Completeness"), ("faithfulness", "Faithfulness")]:
        eligible = [r for r in calibration if r["human"][header] != "n/a"]
        scored = [r for r in eligible if r["outcome"] == "judged"]
        matches = sum(r["verdict"][dimension] == r["human"][header] for r in scored)
        agreement[dimension] = {
            "matches": matches,
            "denominator": len(scored),
            "agreement": matches / len(scored) if scored else None,
            "eligible_human_cases": len(eligible),
            "judge_errors_excluded": len(eligible) - len(scored),
        }
        for row in scored:
            if row["verdict"][dimension] != row["human"][header]:
                disagreements.append(
                    {
                        "id": row["id"],
                        "dimension": dimension,
                        "human_verdict": row["human"][header],
                        "human_reason": row["human"]["Reason"],
                        "judge_verdict": row["verdict"][dimension],
                        "judge_reason": row["verdict"][dimension + "_reason"],
                    }
                )
    groups = {}
    for subset in ["calibration", "judge_only", "baseline_error"]:
        selected = [r for r in rows if r["subset"] == subset]
        groups[subset] = {
            "cases": len(selected),
            "outcomes": dict(Counter(r["outcome"] for r in selected)),
            **{
                dim: dict(Counter(r["verdict"][dim] for r in selected if r["outcome"] == "judged"))
                for dim in ["completeness", "faithfulness"]
            },
        }
    return {
        "total_cases": len(rows),
        "outcomes": dict(Counter(r["outcome"] for r in rows)),
        "subsets": groups,
        "agreement": agreement,
        "disagreements": disagreements,
        "human_faithfulness_na": [
            r["id"] for r in calibration if r["human"]["Faithfulness"] == "n/a"
        ],
    }


def evaluate_judge(
    baseline: dict[str, Any],
    cases: dict[str, AnswerCase],
    humans: dict[str, dict[str, str]],
    provider: AIProvider,
    system: str,
) -> list[dict[str, Any]]:
    rows = []
    for saved in baseline["cases"]:
        case_id = saved["id"]
        row: dict[str, Any] = {
            "id": case_id,
            "baseline_outcome": saved["outcome"],
            "subset": "calibration" if case_id in humans else "judge_only",
        }
        if case_id in humans:
            row["human"] = humans[case_id]
        if saved["outcome"] != "valid_answer":
            row["subset"] = "baseline_error"
            row["outcome"] = "baseline_" + saved["outcome"]
            rows.append(row)
            continue
        request = judge_request(cases[case_id], saved["generation"])
        row["request"] = request
        try:
            result = provider.generate(request, system_prompt=system)
            row.update(raw_response=result.text, model=result.model, usage=result.usage)
            verdict = JudgeVerdict.model_validate_json(result.text)
            if len(verdict.claim_verdicts) != len(saved["generation"]["answer"]["claims"]):
                raise ValueError("Judge must assess every candidate claim exactly once")
            row.update(outcome="judged", verdict=verdict.model_dump(mode="json"))
        except ProviderError:
            row.update(outcome="judge_provider_error", error="Judge request failed")
        except (ValidationError, ValueError):
            row.update(
                outcome="judge_schema_error", error="Invalid judge structure or claim coverage"
            )
        rows.append(row)
    return rows


def markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# PeopleFlow RAG judge and calibration",
        "",
        f"Judge: `{report['model']}`; prompt: `{report['prompt_version']}`.",
        f"Prompt SHA-256: `{report['prompt_sha256']}`.",
        "",
        "Input SHA-256:",
        "",
    ]
    lines += [f"- {name}: `{value}`" for name, value in report["input_hashes"].items()]
    lines += [
        "",
        f"Overall: {s['total_cases']} cases; outcomes: {s['outcomes']}.",
        "",
        "## Human calibration (10 answers)",
        "",
    ]
    for dim, agreement in s["agreement"].items():
        lines.append(
            f"- {dim.title()}: {agreement['matches']}/{agreement['denominator']} exact agreement; "
            f"{agreement['judge_errors_excluded']} judge errors excluded."
        )
    lines += [
        f"- Human Faithfulness n/a (excluded): {', '.join(s['human_faithfulness_na']) or 'none'}.",
        "",
        "## Results by subset",
        "",
    ]
    for subset, counts in s["subsets"].items():
        lines.append(f"- {subset}: {json.dumps(counts)}")
    lines += [
        "",
        "## Per-case verdicts",
        "",
        "| Case | Subset | Outcome | Completeness | Faithfulness |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report["cases"]:
        v = row.get("verdict", {})
        lines.append(
            f"| {row['id']} | {row['subset']} | {row['outcome']} | "
            f"{v.get('completeness', '')} | {v.get('faithfulness', '')} |"
        )
    lines += ["", "## Disagreements", ""]
    for d in s["disagreements"]:
        lines += [
            f"### {d['id']} / {d['dimension']}",
            "",
            f"Human: **{d['human_verdict']}**. {d['human_reason'] or '(No reason supplied.)'}",
            "",
            f"Judge: **{d['judge_verdict']}**. {d['judge_reason']}",
            "",
        ]
    if not s["disagreements"]:
        lines.append("No scored disagreements.")
    lines += [
        "",
        "Judge verdicts are fallible semantic assessments, not ground truth. "
        "Blank human reasons are reported as absent, never inferred. "
        "Provider/schema errors are excluded from agreement, never counted as semantic failures.",
        "",
        "Full per-claim reasons, requests, raw judge responses, and token usage are in the JSON.",
    ]
    return "\n".join(lines) + "\n"


def judge_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Judge saved RAG answers via OpenRouter.")
    parser.add_argument("--baseline", type=Path, default=Path("results/rag_baseline.json"))
    parser.add_argument("--cases", type=Path, default=Path("evals/rag_cases.json"))
    parser.add_argument("--human-labels", type=Path, default=Path("evals/rag_human_labels.csv"))
    parser.add_argument("--model", help="OpenRouter model ID; otherwise OPENROUTER_MODEL.")
    parser.add_argument("--output", type=Path, default=Path("results/rag_judge.json"))
    parser.add_argument(
        "--validate-only", action="store_true", help="Validate inputs without API calls."
    )
    args = parser.parse_args(argv)
    stage = "input validation"
    try:
        baseline, cases, humans = load_inputs(args.baseline, args.cases, args.human_labels)
        stage = "loading the judge prompt"
        system = PROMPT_PATH.read_text(encoding="utf-8")
        if args.validate_only:
            print(f"Validated {len(cases)} cases and {len(humans)} human labels; no API calls.")
            return 0
        output = args.output
        md_path = output.with_suffix(".md")
        stage = "output validation"
        if output.suffix.lower() != ".json":
            raise ValueError("--output must have a .json extension")
        if output.exists() or md_path.exists():
            raise ValueError(
                "Output JSON or sibling Markdown already exists; choose a new --output"
            )
        stage = "OpenRouter configuration"
        if args.model and args.model.strip() == "provider/model-id":
            raise ValueError(
                "provider/model-id is a documentation placeholder; use a real model ID"
            )
        # User-authorized local configuration; existing process settings take precedence.
        load_dotenv(Path.cwd() / ".env", override=False)
        settings = Settings.openrouter_from_env(
            {
                **os.environ,
                **({"OPENROUTER_MODEL": args.model} if args.model else {}),
            }
        )
        settings = replace(settings, temperature=0.0, top_p=1.0)
        hashes = {
            "baseline": sha256(args.baseline),
            "cases": sha256(args.cases),
            "human_labels": sha256(args.human_labels),
        }
        stage = "judge execution"
        rows = evaluate_judge(baseline, cases, humans, JudgeProvider(settings), system)
        report = {
            "schema_version": "1.0",
            "model": settings.model,
            "prompt_version": PROMPT_VERSION,
            "prompt_sha256": sha256(PROMPT_PATH),
            "system_prompt": system,
            "input_hashes": hashes,
            "finished_at": datetime.now(UTC).isoformat(),
            "settings": {
                "temperature": settings.temperature,
                "top_p": settings.top_p,
                "max_retries": settings.max_retries,
                "timeout": settings.timeout,
            },
            "cases": rows,
            "summary": summarize(rows),
        }
        stage = "writing results"
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        with md_path.open("x", encoding="utf-8") as stream:
            stream.write(markdown(report))
    except (ValueError, KeyError, TypeError, OSError, ProviderError) as exc:
        # Only plain ValueErrors contain our fixed validation/configuration messages.
        # Never display Pydantic inputs, raw JSON, provider bodies, or credentials.
        if type(exc) is ValueError:
            detail = str(exc)
        elif isinstance(exc, OSError):
            detail = exc.strerror or "File could not be read or written"
        else:
            detail = "Invalid saved data structure or provider response; no raw data displayed"
        hint = (
            " Set OPENROUTER_API_KEY and OPENROUTER_MODEL in the project .env "
            "or PowerShell environment (or use --model for the model)."
            if stage == "OpenRouter configuration"
            else ""
        )
        parser.exit(1, f"Judge evaluation failed during {stage}: {detail.rstrip('.')}.{hint}\n")
    print(f"Saved judge results to {output} and {md_path}")
    return int(any(r["outcome"].startswith("judge_") for r in rows))
