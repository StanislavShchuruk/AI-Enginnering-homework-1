"""The local pipeline reuses each existing stage and stops on ingestion errors."""

from unittest.mock import patch

from ai_project.cli import main


def test_pipeline_uses_run_paths(tmp_path):
    output = tmp_path / "new-run"
    with (
        patch(
            "ai_project.rag_reproduction.process_corpus",
            return_value={"errors": [], "withheld_documents": 0},
        ) as ingest,
        patch("ai_project.rag_reproduction.build_index") as index,
        patch(
            "ai_project.rag_reproduction.evaluate_rag",
            return_value={"cases": [{"outcome": "valid_answer"}]},
        ) as evaluate,
    ):
        assert main(["reproduce-rag", "--output", str(output)]) == 0
    assert ingest.call_args.args[2] == output / "corpus"
    index.assert_called_once_with(output / "corpus/chunks.jsonl", output / "index", model="bge-m3")
    evaluate.assert_called_once_with(index_path=output / "index", output=output / "rag.json")


def test_failed_ingestion_prevents_model_calls(tmp_path):
    with (
        patch(
            "ai_project.rag_reproduction.process_corpus",
            return_value={"errors": ["failed"], "withheld_documents": 1},
        ),
        patch("ai_project.rag_reproduction.build_index") as index,
        patch("ai_project.rag_reproduction.evaluate_rag") as evaluate,
    ):
        assert main(["reproduce-rag", "--output", str(tmp_path / "new-run")]) == 1
    index.assert_not_called()
    evaluate.assert_not_called()
