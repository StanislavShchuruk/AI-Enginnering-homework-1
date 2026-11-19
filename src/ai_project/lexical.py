"""Small Unicode BM25 index and equal-weight reciprocal rank fusion."""

import math
import re
import unicodedata
from collections import Counter
from typing import Any

BM25_K1 = 1.5
BM25_B = 0.75
RRF_K = 60
CANDIDATES = 20
TOKENIZER_VERSION = "unicode-compounds-v1"
TOKEN = re.compile(r"[^\W_]+(?:[-.'][^\W_]+)*", re.UNICODE)
PUNCTUATION = str.maketrans({"’": "'", "‘": "'", "‐": "-", "‑": "-", "–": "-", "—": "-"})


def tokenize(text: str) -> list[str]:
    """Keep compounds plus their components, e.g. att-lock/att/lock and v1.8/v1/8."""
    normalized = unicodedata.normalize("NFKC", text).translate(PUNCTUATION).casefold()
    tokens = []
    for match in TOKEN.finditer(normalized):
        term = match.group()
        tokens.append(term)
        # Apostrophes remain internal to Ukrainian words; hyphens/dots also expose parts.
        components = re.split(r"[-.]", term)
        if len(components) > 1:
            tokens.extend(components)
    return tokens


class BM25Index:
    """Corpus statistics are fixed; only visible documents can enter the ranking."""

    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = payloads
        self.frequencies = [
            Counter(
                tokenize(f"{p['document_title']}\n{' > '.join(p['section_path'])}\n\n{p['text']}")
            )
            for p in payloads
        ]
        self.lengths = [sum(f.values()) for f in self.frequencies]
        self.average_length = sum(self.lengths) / len(payloads) if payloads else 0.0
        document_frequencies: Counter[str] = Counter()
        for frequencies in self.frequencies:
            document_frequencies.update(frequencies.keys())
        self.idf = {
            term: math.log1p((len(payloads) - df + 0.5) / (df + 0.5))
            for term, df in document_frequencies.items()
        }

    def search(
        self,
        question: str,
        access_groups: list[str],
        *,
        limit: int = CANDIDATES,
    ) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("BM25 limit must be positive")
        terms = sorted(set(tokenize(question)))
        results = []
        for payload, frequencies, length in zip(
            self.payloads, self.frequencies, self.lengths, strict=True
        ):
            if payload.get("access_group") not in access_groups:
                continue
            if not length:
                continue
            norm = BM25_K1 * (1 - BM25_B + BM25_B * length / self.average_length)
            score = sum(
                self.idf[term] * frequencies[term] * (BM25_K1 + 1) / (frequencies[term] + norm)
                for term in terms
                if frequencies[term]
            )
            if score > 0:
                results.append({**payload, "score": score})
        results.sort(key=lambda hit: (-hit["score"], hit["chunk_id"]))
        return [{**hit, "rank": rank} for rank, hit in enumerate(results[:limit], 1)]


def reciprocal_rank_fusion(
    vector: list[dict[str, Any]],
    bm25: list[dict[str, Any]],
    *,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Each unique chunk contributes at most once per branch, with weight 1/(60+rank)."""
    if top_k < 1:
        raise ValueError("Fusion top-k must be positive")
    scores: dict[str, float] = {}
    payloads: dict[str, dict[str, Any]] = {}
    for branch in (vector, bm25):
        seen: set[str] = set()
        for hit in branch:
            chunk_id = hit["chunk_id"]
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            rank = len(seen)
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (RRF_K + rank)
            payloads.setdefault(chunk_id, hit)
    ordered = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))[:top_k]
    return [
        {**payloads[chunk_id], "score": scores[chunk_id], "rank": rank}
        for rank, chunk_id in enumerate(ordered, 1)
    ]
