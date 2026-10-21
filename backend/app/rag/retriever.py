"""Persistent rulebook retrieval with an offline lexical fallback."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

_TOKEN = re.compile(r"[\w]+", re.UNICODE)
_INDEX_FILENAME = "rulebooks.lexical.json"
_DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


def _tokens(value: str) -> list[str]:
    return [token.casefold() for token in _TOKEN.findall(value)]


class _SentenceTransformerEmbedding:
    """Small Chroma embedding-function adapter kept behind optional imports."""

    def __init__(self, model: Any) -> None:
        self.model = model

    def __call__(self, input: list[str]) -> list[list[float]]:
        vectors = self.model.encode(
            input,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return vectors.tolist()


def _load_local_embedding() -> Any | None:
    """Load only a local model; never make network access part of retrieval."""

    try:
        from sentence_transformers import SentenceTransformer

        try:
            return SentenceTransformer(_DEFAULT_MODEL, local_files_only=True)
        except TypeError:
            # Recent sentence-transformers versions pass Hugging Face loading
            # flags through ``model_kwargs`` instead of accepting them at the
            # top level. Both forms keep retrieval offline when the model is
            # already cached and avoid an accidental download at startup.
            return SentenceTransformer(
                _DEFAULT_MODEL,
                model_kwargs={"local_files_only": True},
            )
    except Exception:
        return None


class RulebookRetriever:
    """Retrieve rulebook chunks using Chroma or deterministic token overlap."""

    def __init__(
        self,
        chunks: Iterable[dict[str, str]] | None = None,
        *,
        chroma_path: str | Path | None = None,
        collection_name: str = "adhikaar_rulebooks",
        use_chroma: bool = True,
        force_fallback: bool = False,
    ) -> None:
        configured_path = chroma_path or os.getenv("CHROMA_PATH")
        self.chroma_path = Path(configured_path) if configured_path else None
        self.collection_name = collection_name
        self.chunks = [self._normalize_chunk(chunk) for chunk in (chunks or [])]
        self._collection: Any | None = None

        if not self.chunks and self.chroma_path is not None:
            self.chunks = self._load_fallback_index()
        if self.chroma_path is not None and self.chunks:
            self._persist_fallback_index()
        if self.chunks and use_chroma and not force_fallback:
            self._try_enable_chroma()

    @staticmethod
    def _normalize_chunk(chunk: dict[str, str]) -> dict[str, str]:
        return {
            "text": str(chunk.get("text", "")),
            "source": str(chunk.get("source", "")),
            "scheme_id": str(chunk.get("scheme_id", "")),
            "heading": str(chunk.get("heading", "Overview")),
        }

    @property
    def using_chroma(self) -> bool:
        return self._collection is not None

    @classmethod
    def from_persisted(
        cls,
        chroma_path: str | Path,
        *,
        collection_name: str = "adhikaar_rulebooks",
        use_chroma: bool = True,
    ) -> "RulebookRetriever":
        """Reopen the local index written by :func:`ingest_rulebooks`."""

        return cls(
            None,
            chroma_path=chroma_path,
            collection_name=collection_name,
            use_chroma=use_chroma,
        )

    def _index_path(self) -> Path | None:
        if self.chroma_path is None:
            return None
        return self.chroma_path / _INDEX_FILENAME

    def _persist_fallback_index(self) -> None:
        index_path = self._index_path()
        if index_path is None:
            return
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(
            json.dumps({"version": 1, "chunks": self.chunks}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_fallback_index(self) -> list[dict[str, str]]:
        index_path = self._index_path()
        if index_path is None or not index_path.is_file():
            return []
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            return [self._normalize_chunk(chunk) for chunk in payload.get("chunks", [])]
        except (OSError, json.JSONDecodeError, AttributeError, TypeError):
            return []

    def _try_enable_chroma(self) -> None:
        """Use Chroma only when both it and a local embedding model work."""

        embedding_model = _load_local_embedding()
        if embedding_model is None or self.chroma_path is None:
            return
        try:
            import chromadb

            self.chroma_path.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(self.chroma_path))
            collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
                embedding_function=_SentenceTransformerEmbedding(embedding_model),
            )
            existing = collection.get()
            if existing.get("ids"):
                collection.delete(ids=existing["ids"])
            if self.chunks:
                collection.upsert(
                    ids=[self._chunk_id(chunk) for chunk in self.chunks],
                    documents=[chunk["text"] for chunk in self.chunks],
                    metadatas=[
                        {
                            "source": chunk["source"],
                            "scheme_id": chunk["scheme_id"],
                            "heading": chunk["heading"],
                        }
                        for chunk in self.chunks
                    ],
                )
            self._collection = collection
        except Exception:
            # Optional vector packages should never prevent a deterministic
            # offline index from serving a request.
            self._collection = None

    @staticmethod
    def _chunk_id(chunk: dict[str, str]) -> str:
        identity = "\x1f".join((chunk["source"], chunk["heading"], chunk["text"]))
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def _retrieve_chroma(self, query: str, k: int) -> list[dict[str, Any]]:
        result = self._collection.query(query_texts=[query], n_results=k)
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        matches: list[dict[str, Any]] = []
        for index, text in enumerate(documents):
            metadata = (metadatas[index] if index < len(metadatas) else {}) or {}
            distance = distances[index] if index < len(distances) else 1.0
            matches.append(
                {
                    "text": str(text),
                    "source": str(metadata.get("source", "")),
                    "score": round(1.0 / (1.0 + max(float(distance), 0.0)), 6),
                }
            )
        return matches

    def _retrieve_lexical(self, query: str, k: int) -> list[dict[str, Any]]:
        query_tokens = Counter(_tokens(query))
        if not query_tokens:
            return []
        query_size = math.sqrt(sum(value * value for value in query_tokens.values()))
        scored: list[tuple[float, dict[str, str]]] = []
        for chunk in self.chunks:
            searchable = " ".join(
                (chunk["text"], chunk["heading"], chunk["scheme_id"], chunk["source"])
            )
            document_tokens = Counter(_tokens(searchable))
            overlap = sum(
                min(count, document_tokens.get(token, 0)) for token, count in query_tokens.items()
            )
            if not overlap:
                continue
            denominator = query_size * math.sqrt(
                sum(value * value for value in document_tokens.values())
            )
            score = overlap / denominator if denominator else 0.0
            scored.append((score, chunk))

        scored.sort(key=lambda item: (-item[0], item[1]["source"], item[1]["heading"]))
        return [
            {
                "text": chunk["text"],
                "source": chunk["source"],
                "score": round(score, 6),
            }
            for score, chunk in scored[:k]
        ]

    def retrieve(self, query: str, k: int = 4) -> list[dict[str, Any]]:
        """Return at most ``k`` ranked ``text``/``source``/``score`` records."""

        if k <= 0 or not str(query).strip() or not self.chunks:
            return []
        if self._collection is not None:
            try:
                return self._retrieve_chroma(str(query), k)
            except Exception:
                self._collection = None
        return self._retrieve_lexical(str(query), k)


# Concrete implementation name used by dependency injection callers.
Retriever = RulebookRetriever
