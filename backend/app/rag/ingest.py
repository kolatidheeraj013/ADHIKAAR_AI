"""Read MOCK markdown rulebooks and build a persistent rulebook retriever."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)\s*$")
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RULEBOOKS_PATH = _REPOSITORY_ROOT / "data" / "rulebooks"
DEFAULT_CHROMA_PATH = Path(os.getenv("CHROMA_PATH", ".chroma"))


def _flush_chunk(
    chunks: list[dict[str, str]],
    *,
    source: str,
    scheme_id: str,
    heading: str,
    body: list[str],
) -> None:
    content = "\n".join(body).strip()
    if not content and heading == "Overview":
        return
    text = f"{heading}\n\n{content}" if content else heading
    chunks.append(
        {
            "text": text,
            "source": source,
            "scheme_id": scheme_id,
            "heading": heading,
        }
    )


def chunk_markdown(markdown: str, source: str, scheme_id: str) -> list[dict[str, str]]:
    """Split markdown into one chunk per heading and attach source metadata.

    A short preamble is retained as an ``Overview`` chunk. Content belongs to
    the most recent heading, which keeps citations useful without imposing a
    particular heading depth on the rulebooks.
    """

    chunks: list[dict[str, str]] = []
    heading = "Overview"
    body: list[str] = []
    for line in markdown.splitlines():
        match = _HEADING.match(line)
        if match:
            _flush_chunk(
                chunks,
                source=source,
                scheme_id=scheme_id,
                heading=heading,
                body=body,
            )
            heading = match.group(2).strip()
            body = []
        else:
            body.append(line)
    _flush_chunk(
        chunks,
        source=source,
        scheme_id=scheme_id,
        heading=heading,
        body=body,
    )
    return chunks


def load_rulebook_chunks(rulebooks_dir: str | Path) -> list[dict[str, str]]:
    """Load all markdown rulebooks below ``rulebooks_dir``.

    Missing directories are an explicit configuration error. An existing but
    empty directory is valid and produces an empty index, which is useful for
    minimal deployments and tests.
    """

    directory = Path(rulebooks_dir)
    if not directory.exists():
        raise FileNotFoundError(f"rulebook directory does not exist: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"rulebook path is not a directory: {directory}")

    chunks: list[dict[str, str]] = []
    for path in sorted(directory.glob("*.md")):
        markdown = path.read_text(encoding="utf-8")
        source = path.relative_to(directory).as_posix()
        chunks.extend(chunk_markdown(markdown, source, path.stem))
    return chunks


def ingest_rulebooks(
    rulebooks_dir: str | Path | None = None,
    chroma_path: str | Path | None = None,
    *,
    collection_name: str = "adhikaar_rulebooks",
    use_chroma: bool = True,
    force_fallback: bool = False,
) -> Any:
    """Ingest markdown rulebooks and return a retriever.

    ChromaDB and a locally available sentence-transformers model are used when
    both can be loaded without downloading anything. Otherwise the returned
    retriever uses a deterministic lexical index and stores that index under
    ``chroma_path`` so it remains usable across process restarts.
    """

    from app.rag.retriever import RulebookRetriever

    directory = Path(rulebooks_dir or os.getenv("RULEBOOKS_PATH", str(DEFAULT_RULEBOOKS_PATH)))
    storage_path = Path(chroma_path or os.getenv("CHROMA_PATH", str(DEFAULT_CHROMA_PATH)))
    chunks = load_rulebook_chunks(directory)
    return RulebookRetriever(
        chunks,
        chroma_path=storage_path,
        collection_name=collection_name,
        use_chroma=use_chroma,
        force_fallback=force_fallback,
    )


# A concise alias for callers that use the operation name from the spec.
ingest = ingest_rulebooks
load_rulebooks = load_rulebook_chunks
build_retriever = ingest_rulebooks
