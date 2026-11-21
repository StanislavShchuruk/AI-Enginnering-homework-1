"""One-command local pipeline, reusing ingestion, indexing and RAG evaluation."""

import argparse
from pathlib import Path

from ai_project.ingestion import process_corpus
from ai_project.rag_evaluation import evaluate_rag
from ai_project.retrieval import build_index


def reproduction_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New run directory.")
    args = parser.parse_args(argv)
    output = args.output
    if output.exists():
        parser.error("Use a new output directory; prior runs are preserved.")
    try:
        report = process_corpus(Path.cwd(), Path("data/manifest.json"), output / "corpus")
        if report["errors"] or report["withheld_documents"]:
            raise ValueError("Ingestion incomplete; inspect corpus/report.json.")
        build_index(output / "corpus/chunks.jsonl", output / "index", model="bge-m3")
        result = evaluate_rag(index_path=output / "index", output=output / "rag.json")
    except (ValueError, OSError, RuntimeError):
        print("Local RAG pipeline failed; inspect the run directory and local model setup.")
        return 1
    print(f"Saved ingestion, index and live RAG results in {output}")
    return int(any(row["outcome"] != "valid_answer" for row in result["cases"]))
