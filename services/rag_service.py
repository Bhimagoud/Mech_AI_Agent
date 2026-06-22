"""
Service: RAG (Retrieval-Augmented Generation)
----------------------------------------------
Responsibilities:
  1. Chunk raw document text into overlapping windows.
  2. Embed chunks using a local sentence-transformers model
     (all-MiniLM-L6-v2 — ~80 MB, runs on CPU, no API key needed).
  3. Store embeddings in memory for the current session.
  4. Retrieve the top-k most relevant chunks for any query.

Usage:
    from services.rag_service import ingest_and_index, retrieve

    # After parsing the SAR document:
    ingest_and_index(raw_text, source="SAR.docx")

    # Inside an agent:
    chunks = retrieve("PEO competency technical skills", top_k=4)
"""

import os
import re
import logging
from typing import List, Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Config from env ──────────────────────────────────────────────────────────
_EMBED_MODEL_NAME = os.getenv("RAG_EMBED_MODEL", "all-MiniLM-L6-v2")
_DEFAULT_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "1500"))
_DEFAULT_OVERLAP    = int(os.getenv("RAG_CHUNK_OVERLAP", "200"))
_DEFAULT_TOP_K      = int(os.getenv("RAG_TOP_K", "4"))

# ── Module-level in-memory store (one document per session) ──────────────────
_embed_model   = None          # SentenceTransformer loaded lazily
_store_chunks  : List[str]       = []
_store_embeds  : Optional[np.ndarray] = None
_store_meta    : List[Dict]      = []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest_and_index(
    text: str,
    source: str = "",
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    overlap: int   = _DEFAULT_OVERLAP,
) -> int:
    """
    Split *text* into overlapping chunks, embed them, and store in memory.

    Args:
        text:       Full raw text of the uploaded document.
        source:     Original filename (stored as metadata).
        chunk_size: Target chunk length in characters.
        overlap:    Character overlap between consecutive chunks.

    Returns:
        Number of chunks indexed.
    """
    global _store_chunks, _store_embeds, _store_meta

    chunks = _split_text(text, chunk_size, overlap)
    if not chunks:
        logger.warning("RAG: No usable chunks extracted from '%s'", source)
        return 0

    logger.info("RAG: Embedding %d chunks from '%s' …", len(chunks), source)
    model = _get_model()
    embeds = model.encode(chunks, show_progress_bar=False, batch_size=32)

    _store_chunks = chunks
    _store_embeds = np.array(embeds, dtype=np.float32)
    _store_meta   = [{"source": source, "chunk_idx": i} for i in range(len(chunks))]

    logger.info("RAG: Indexed %d chunks (embed dim=%d).", len(chunks), _store_embeds.shape[1])
    return len(chunks)


def retrieve(query: str, top_k: int = _DEFAULT_TOP_K) -> List[str]:
    """
    Return the *top_k* most semantically similar chunks for *query*.

    Returns an empty list if no document has been indexed yet.
    """
    if _store_embeds is None or len(_store_chunks) == 0:
        logger.debug("RAG: retrieve() called but store is empty.")
        return []

    model   = _get_model()
    q_emb   = model.encode([query], show_progress_bar=False)[0].astype(np.float32)

    # Cosine similarity via dot-product after L2 normalisation
    doc_norm = np.linalg.norm(_store_embeds, axis=1, keepdims=True)
    doc_norm = np.where(doc_norm == 0, 1e-9, doc_norm)
    q_norm   = np.linalg.norm(q_emb) or 1e-9

    scores   = (_store_embeds / doc_norm) @ (q_emb / q_norm)   # shape (N,)
    k        = min(top_k, len(_store_chunks))
    top_idx  = np.argsort(scores)[::-1][:k]

    return [_store_chunks[i] for i in top_idx]


def retrieve_as_context(query: str, top_k: int = _DEFAULT_TOP_K, header: str = "## Relevant Document Context") -> str:
    """
    Retrieve chunks and format them as a single markdown-style context block
    ready to be prepended to an LLM prompt.
    """
    chunks = retrieve(query, top_k)
    if not chunks:
        return ""
    parts = [header, ""]
    for i, chunk in enumerate(chunks, 1):
        parts.append(f"[Chunk {i}]\n{chunk}")
        parts.append("")
    return "\n".join(parts)


def is_indexed() -> bool:
    """Return True if a document has been indexed and is ready for retrieval."""
    return _store_embeds is not None and len(_store_chunks) > 0


def clear() -> None:
    """Flush the in-memory store (call between unrelated uploads if needed)."""
    global _store_chunks, _store_embeds, _store_meta
    _store_chunks = []
    _store_embeds = None
    _store_meta   = []
    logger.info("RAG: Store cleared.")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_model():
    """Load the sentence-transformers model once and cache it."""
    global _embed_model
    if _embed_model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise RuntimeError(
                "sentence-transformers is not installed. "
                "Run: pip install sentence-transformers"
            )
        logger.info("RAG: Loading embedding model '%s' (first-time download ~80 MB) …", _EMBED_MODEL_NAME)
        _embed_model = SentenceTransformer(_EMBED_MODEL_NAME)
        logger.info("RAG: Embedding model ready.")
    return _embed_model


def _split_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """
    Split text into overlapping chunks that respect paragraph boundaries.

    Strategy:
      1. Split on blank lines (paragraph boundaries).
      2. Accumulate paragraphs into a chunk until chunk_size is reached.
      3. When a chunk is full, save it and start the next chunk with
         *overlap* characters of tail from the previous chunk.
      4. Paragraphs longer than chunk_size are hard-split with overlap.
    """
    # Normalise whitespace and split into paragraphs
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) > 30]

    chunks: List[str] = []
    current = ""

    for para in paragraphs:
        # Hard-split oversized paragraphs
        if len(para) > chunk_size:
            for start in range(0, len(para), chunk_size - overlap):
                sub = para[start : start + chunk_size].strip()
                if sub:
                    chunks.append(sub)
            current = ""
            continue

        if len(current) + len(para) + 2 <= chunk_size:
            current = (current + "\n\n" + para).strip() if current else para
        else:
            if current:
                chunks.append(current)
            # Begin next chunk with overlap tail from the previous chunk
            tail = current[-overlap:] if overlap and current else ""
            current = (tail + "\n\n" + para).strip() if tail else para

    if current and len(current) > 30:
        chunks.append(current)

    return chunks
