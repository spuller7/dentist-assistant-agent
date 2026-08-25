"""
FILE: src/rag.py
WHY: LangChain RAG over a tiny office knowledge base. BM25 is used so the
     demo does not need a vector database or an embeddings API.

     dentists.md is split on ## headings (one segment per dentist). Other
     knowledge files are one document each. Every document keeps the source
     filename so retrieved notes can be labeled by origin.
"""

from __future__ import annotations

import re
from functools import lru_cache

from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

from src.paths import KNOWLEDGE_DIR

DENTISTS_FILE = "dentists.md"


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _heading_from_line(line: str) -> str | None:
    stripped = line.strip()
    if stripped.startswith("#"):
        return stripped.lstrip("#").strip()
    return None


def _first_heading(text: str, fallback: str) -> str:
    for line in text.splitlines():
        heading = _heading_from_line(line)
        if heading:
            return heading
    return fallback


def split_dentists_segments(text: str) -> list[tuple[str, str]]:
    """Split dentists.md on ## headings. Returns (section_title, segment_text)."""
    chunks: list[list[str]] = [[]]
    headings: list[str] = [""]

    for line in text.splitlines(keepends=True):
        if line.startswith("## ") and any(part.strip() for part in chunks[-1]):
            chunks.append([line])
            headings.append(line[3:].strip())
            continue
        chunks[-1].append(line)
        if not headings[-1]:
            heading = _heading_from_line(line)
            if heading:
                headings[-1] = heading

    segments: list[tuple[str, str]] = []
    for heading, chunk in zip(headings, chunks):
        body = "".join(chunk).strip()
        if body:
            segments.append((heading or "document", body))
    return segments


def load_knowledge_docs() -> list[Document]:
    docs: list[Document] = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        title = path.stem.replace("_", " ")
        text = path.read_text(encoding="utf-8")
        if path.name == DENTISTS_FILE:
            segments = split_dentists_segments(text)
        else:
            segments = [(_first_heading(text, title), text.strip())]
        for index, (section, content) in enumerate(segments):
            docs.append(
                Document(
                    page_content=content,
                    metadata={
                        "source": path.name,
                        "title": title,
                        "section": section,
                        "segment_index": index,
                    },
                )
            )
    if not docs:
        raise FileNotFoundError(f"No knowledge files found in {KNOWLEDGE_DIR}")
    return docs


@lru_cache(maxsize=1)
def get_retriever() -> BM25Retriever:
    retriever = BM25Retriever.from_documents(
        load_knowledge_docs(),
        preprocess_func=_tokenize,
        k=5,
    )
    return retriever


def retrieve(query: str) -> list[Document]:
    return get_retriever().invoke(query)


def format_docs(docs: list[Document]) -> str:
    chunks = []
    for doc in docs:
        source = doc.metadata.get("source", "unknown")
        section = doc.metadata.get("section")
        label = f"{source} — {section}" if section else source
        chunks.append(f"[source: {label}]\n{doc.page_content.strip()}")
    return "\n\n---\n\n".join(chunks)
