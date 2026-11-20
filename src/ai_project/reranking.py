"""Optional local cross-encoder inference; no heavyweight imports for other modes."""

import math
from pathlib import Path
from typing import Any, Protocol

DEFAULT_RERANKER = "BAAI/bge-reranker-v2-m3"
DEFAULT_BATCH_SIZE = 8
DEFAULT_MODEL_CACHE = Path("data/models/reranker")


class Reranker(Protocol):
    model_name: str

    def score(self, question: str, passages: list[str]) -> list[float]: ...


def passage_text(payload: dict[str, Any]) -> str:
    return (
        f"{payload['document_title']}\n{' > '.join(payload['section_path'])}\n\n{payload['text']}"
    )


class CrossEncoderReranker:
    def __init__(
        self,
        model_name: str = DEFAULT_RERANKER,
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
        device: str = "cpu",
        cache_folder: Path = DEFAULT_MODEL_CACHE,
        local_files_only: bool = True,
    ) -> None:
        if batch_size < 1 or not model_name.strip():
            raise ValueError("Reranker model must be nonempty and batch size positive")
        try:
            from sentence_transformers import CrossEncoder
            from torch import nn
        except ImportError:
            raise ValueError(
                'Install the optional reranker: python -m pip install -e ".[rerank]"'
            ) from None
        self.model_name = model_name
        self.batch_size = batch_size
        self.device = device
        self.model = CrossEncoder(
            model_name,
            device=device,
            cache_folder=str(cache_folder),
            trust_remote_code=False,
            token=False,
            activation_fn=nn.Identity(),
            local_files_only=local_files_only,
        )

    def score(self, question: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        scores = self.model.predict(
            [(question, passage) for passage in passages],
            batch_size=self.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [float(score) for score in scores]


def rerank_candidates(
    question: str,
    pool: list[dict[str, Any]],
    scorer: Reranker,
    access_groups: list[str],
    *,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Fail closed at the scorer boundary, score the whole pool, then apply final top-k."""
    if any(hit.get("access_group") not in access_groups for hit in pool):
        raise ValueError("Unauthorized candidate blocked before reranker scoring")
    if not pool:
        return []
    scores = scorer.score(question, [passage_text(hit) for hit in pool])
    if len(scores) != len(pool) or any(
        type(score) not in (int, float) or not math.isfinite(score) for score in scores
    ):
        raise ValueError("Reranker must return one finite numeric score per candidate")
    ranked = sorted(enumerate(scores), key=lambda item: (-item[1], item[0]))[:top_k]
    return [
        {
            **pool[index],
            "rrf_rank": index + 1,
            "rrf_score": pool[index]["score"],
            "score": score,
            "rank": rank,
        }
        for rank, (index, score) in enumerate(ranked, 1)
    ]
