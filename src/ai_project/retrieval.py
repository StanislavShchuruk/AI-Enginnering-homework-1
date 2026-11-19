"""Local Ollama embeddings and persistent, access-filtered Qdrant retrieval."""

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Literal
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator
from qdrant_client import QdrantClient, models

from ai_project.chunking import Chunk
from ai_project.lexical import CANDIDATES, BM25Index, reciprocal_rank_fusion

DEFAULT_INPUT = Path("data/chunked/task3-run02/chunks.jsonl")
DEFAULT_INDEX = Path("data/index/peopleflow")
DEFAULT_URL = "http://localhost:11434"
ALIAS = "peopleflow"
ACCESS_GROUPS = {"all_employees", "managers_hr", "hr_payroll", "hr_confidential"}


class IndexChunk(Chunk):
    """Validate the canonical record, including identity and fail-closed access metadata."""

    model_config = ConfigDict(extra="forbid", strict=True)

    token_count: int = Field(gt=0)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_index_fields(self) -> "IndexChunk":
        if not re.fullmatch(re.escape(self.document_id) + r"-[0-9a-f]{64}", self.chunk_id):
            raise ValueError("Invalid canonical chunk ID")
        if not all(
            s.strip()
            for s in (self.document_id, self.text, self.document_title, self.source_reference)
        ):
            raise ValueError("Document identity, text, title and source must be nonempty")
        group = self.metadata.get("access_group")
        if not isinstance(group, str) or group not in ACCESS_GROUPS:
            raise ValueError("Missing or unknown access_group")
        if any(not section.strip() for section in self.section_path):
            raise ValueError("Section labels must be nonempty")
        return self


class IndexMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    embedding_model: str = Field(min_length=1)
    vector_dimension: int = Field(gt=0)
    source_file: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    chunk_count: int = Field(gt=0)
    embedding_format: str = "title-section-text-v1"
    distance: str = "Cosine"


def load_chunks(path: Path) -> tuple[list[IndexChunk], str]:
    if path.suffix.lower() != ".jsonl" or path.name.startswith(".env"):
        raise ValueError("Input must be a canonical chunks JSONL file")
    raw = path.read_bytes()
    chunks: list[IndexChunk] = []
    seen: set[str] = set()
    for line_number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        try:
            chunk = IndexChunk.model_validate_json(line)
            if chunk.chunk_id in seen:
                raise ValueError("Duplicate chunk ID")
        except ValueError:
            # Validation errors can contain document text; report only the location.
            raise ValueError(
                f"Invalid record or duplicate chunk ID at line {line_number}"
            ) from None
        seen.add(chunk.chunk_id)
        chunks.append(chunk)
    if not chunks:
        raise ValueError("Input must contain at least one chunk")
    return chunks, hashlib.sha256(raw).hexdigest()


def embedding_text(chunk: Chunk) -> str:
    return f"{chunk.document_title}\n{' > '.join(chunk.section_path)}\n\n{chunk.text}"


def validate_vectors(value: object, count: int, dimension: int | None = None) -> list[list[float]]:
    if not isinstance(value, list) or len(value) != count:
        raise ValueError("Embedding response count differs from input count")
    result = []
    for vector in value:
        if not isinstance(vector, list) or not vector:
            raise ValueError("Embedding vectors must be nonempty arrays")
        dimension = dimension or len(vector)
        if len(vector) != dimension or any(
            type(v) not in (float, int) or not math.isfinite(v) for v in vector
        ):
            raise ValueError("Embedding vectors must have consistent dimensions and finite numbers")
        if not any(vector):
            raise ValueError("Embedding vectors must be nonzero for cosine similarity")
        result.append([float(v) for v in vector])
    return result


class OllamaEmbedder:
    def __init__(self, base_url: str = DEFAULT_URL) -> None:
        url = urlsplit(base_url)
        if (
            url.scheme != "http"
            or url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
        ):
            raise ValueError("Ollama URL must be an HTTP loopback origin")
        self.endpoint = base_url.rstrip("/") + "/api/embed"

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        request = Request(
            self.endpoint,
            data=json.dumps({"model": model, "input": texts, "truncate": False}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            # Bypass environment proxies so local document text stays local.
            with build_opener(ProxyHandler({})).open(request, timeout=180) as response:
                payload = json.load(response)
        except (URLError, TimeoutError, ValueError):
            raise ValueError(
                "Local Ollama embedding request failed; check service and model"
            ) from None
        if not isinstance(payload, dict):
            raise ValueError("Invalid Ollama embedding response")
        return validate_vectors(payload.get("embeddings"), len(texts))


def active_collection(client: QdrantClient) -> str:
    for alias in client.get_aliases().aliases:
        if alias.alias_name == ALIAS:
            return alias.collection_name
    raise ValueError("No active index; run index-corpus first")


def indexed_chunks(
    client: QdrantClient,
    collection: str,
    metadata: IndexMetadata,
) -> list[IndexChunk]:
    """Verify canonical file provenance and exact membership/payloads of the active index."""
    chunks, digest = load_chunks(Path(metadata.source_file))
    if digest != metadata.source_sha256 or len(chunks) != metadata.chunk_count:
        raise ValueError("Canonical chunks differ from the current index metadata; rebuild first")
    corpus = {chunk.chunk_id: chunk for chunk in chunks}
    seen: set[str] = set()
    offset = None
    while True:
        points, offset = client.scroll(
            collection, limit=256, offset=offset, with_payload=True, with_vectors=False
        )
        for point in points:
            payload = point.payload or {}
            chunk_id = payload.get("chunk_id")
            chunk = corpus.get(chunk_id) if isinstance(chunk_id, str) else None
            if (
                chunk is None
                or chunk_id in seen
                or payload
                != {**chunk.model_dump(mode="json"), "access_group": chunk.metadata["access_group"]}
            ):
                raise ValueError("Persisted index payloads differ from canonical chunks")
            seen.add(chunk_id)
        if offset is None:
            break
    if seen != set(corpus):
        raise ValueError("Indexed chunk IDs differ from canonical chunks")
    return chunks


def build_index(
    input_path: Path = DEFAULT_INPUT,
    index_path: Path = DEFAULT_INDEX,
    *,
    model: str = "bge-m3",
    batch_size: int = 16,
    embedder: OllamaEmbedder | None = None,
) -> IndexMetadata:
    if batch_size < 1 or not model.strip():
        raise ValueError("Batch size and embedding model must be positive/nonempty")
    chunks, source_hash = load_chunks(input_path)
    embedder = embedder or OllamaEmbedder()
    index_path.mkdir(parents=True, exist_ok=True)
    collection = "chunks_" + uuid4().hex
    metadata_path = index_path / f"{collection}.json"
    client = QdrantClient(path=str(index_path / "qdrant"))
    published = False
    try:
        dimension = None
        for offset in range(0, len(chunks), batch_size):
            batch = chunks[offset : offset + batch_size]
            vectors = validate_vectors(
                embedder.embed([embedding_text(c) for c in batch], model), len(batch), dimension
            )
            if dimension is None:
                dimension = len(vectors[0])
                client.create_collection(
                    collection,
                    vectors_config=models.VectorParams(
                        size=dimension,
                        distance=models.Distance.COSINE,
                    ),
                )
            client.upsert(
                collection,
                points=[
                    models.PointStruct(
                        id=str(uuid5(NAMESPACE_URL, chunk.chunk_id)),
                        vector=vector,
                        payload={
                            **chunk.model_dump(mode="json"),
                            "access_group": chunk.metadata["access_group"],
                        },
                    )
                    for chunk, vector in zip(batch, vectors, strict=True)
                ],
                wait=True,
            )
        count = client.count(collection, exact=True).count
        if count != len(chunks):
            raise ValueError("Persisted point count differs from JSONL count")
        metadata = IndexMetadata(
            embedding_model=model,
            vector_dimension=dimension,
            source_file=str(input_path.resolve()),
            source_sha256=source_hash,
            chunk_count=count,
        )
        metadata_path.write_text(metadata.model_dump_json(indent=2) + "\n", encoding="utf-8")
        old = [a.collection_name for a in client.get_aliases().aliases if a.alias_name == ALIAS]
        operations = (
            [models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=ALIAS))]
            if old
            else []
        )
        operations.append(
            models.CreateAliasOperation(
                create_alias=models.CreateAlias(
                    collection_name=collection,
                    alias_name=ALIAS,
                )
            )
        )
        client.update_collection_aliases(operations)
        published = True
        for previous in old:
            client.delete_collection(previous)
            (index_path / f"{previous}.json").unlink(missing_ok=True)
        return metadata
    finally:
        try:
            if not published:
                if client.collection_exists(collection):
                    client.delete_collection(collection)
                metadata_path.unlink(missing_ok=True)
        finally:
            client.close()


def search(
    question: str,
    index_path: Path = DEFAULT_INDEX,
    *,
    top_k: int = 5,
    access_groups: list[str] | None = None,
    embedder: OllamaEmbedder | None = None,
    mode: Literal["vector", "hybrid"] = "vector",
) -> list[dict[str, Any]]:
    groups = ["all_employees"] if access_groups is None else access_groups
    if not question.strip() or top_k < 1 or not groups or set(groups) - ACCESS_GROUPS:
        raise ValueError("Provide a nonempty question, positive top-k and known access groups")
    if mode not in {"vector", "hybrid"}:
        raise ValueError("Search mode must be vector or hybrid")
    if not (index_path / "qdrant").is_dir():
        raise ValueError("No local index; run index-corpus first")
    client = QdrantClient(path=str(index_path / "qdrant"))
    try:
        collection = active_collection(client)
        metadata = IndexMetadata.model_validate_json(
            (index_path / f"{collection}.json").read_text(encoding="utf-8")
        )
        lexical = None
        if mode == "hybrid":
            chunks = indexed_chunks(client, collection, metadata)
            lexical = BM25Index(
                [
                    {
                        **chunk.model_dump(mode="json"),
                        "access_group": chunk.metadata["access_group"],
                    }
                    for chunk in chunks
                ]
            )
        vectors = validate_vectors(
            (embedder or OllamaEmbedder()).embed([question], metadata.embedding_model),
            1,
            metadata.vector_dimension,
        )
        hits = client.query_points(
            collection,
            query=vectors[0],
            limit=CANDIDATES if mode == "hybrid" else top_k,
            with_payload=True,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="access_group",
                        match=models.MatchAny(any=groups),
                    )
                ]
            ),
        ).points
        if mode == "hybrid":
            hits.sort(key=lambda hit: (-hit.score, (hit.payload or {})["chunk_id"]))
        vector = [
            {"rank": rank, "score": hit.score, **(hit.payload or {})}
            for rank, hit in enumerate(hits, 1)
        ]
        if lexical is not None:
            return reciprocal_rank_fusion(
                vector,
                lexical.search(question, groups, limit=CANDIDATES),
                top_k=top_k,
            )
        return vector
    finally:
        client.close()


def retrieval_main(command: str, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Local PeopleFlow vector indexing and search.")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--ollama-url", default=DEFAULT_URL)
    if command == "index-corpus":
        parser.add_argument(
            "--input",
            type=Path,
            default=DEFAULT_INPUT,
            help=f"Canonical chunks JSONL (default: {DEFAULT_INPUT}).",
        )
        parser.add_argument("--embedding-model", default="bge-m3")
        parser.add_argument("--batch-size", type=int, default=16)
    else:
        parser.add_argument("question")
        parser.add_argument("--top-k", type=int, default=5)
        parser.add_argument("--mode", choices=["vector", "hybrid"], default="vector")
        parser.add_argument(
            "--access-group",
            action="append",
            choices=sorted(ACCESS_GROUPS),
            help="Additional allowed group; repeatable. Local testing only.",
        )
        parser.add_argument(
            "--hr-access", action="store_true", help="Local HR smoke test: include hr_confidential."
        )
    args = parser.parse_args(argv)
    try:
        embedder = OllamaEmbedder(args.ollama_url)
        if command == "index-corpus":
            result = build_index(
                args.input,
                args.index,
                model=args.embedding_model,
                batch_size=args.batch_size,
                embedder=embedder,
            ).model_dump()
        else:
            groups = ["all_employees", *(args.access_group or [])]
            if args.hr_access:
                groups.append("hr_confidential")
            result = search(
                args.question,
                args.index,
                top_k=args.top_k,
                access_groups=groups,
                embedder=embedder,
                mode=args.mode,
            )
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f"Local retrieval failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
