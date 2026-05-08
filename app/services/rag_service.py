"""
app/services/rag_service.py
────────────────────────────
ChromaDB-backed Retrieval Augmented Generation (RAG) service.
Provides FAQ / knowledge-base lookup before falling back to the LLM.
"""

from __future__ import annotations

from __future__ import annotations

import asyncio
from typing import Optional

import chromadb
import structlog
from chromadb.config import Settings as ChromaSettings

from app.config import settings

log = structlog.get_logger(__name__)

# Threshold below which a ChromaDB result is considered irrelevant
_RELEVANCE_THRESHOLD = 0.65
_TOP_K = 3


class RAGService:
    """Wraps ChromaDB for async-friendly FAQ retrieval."""

    def __init__(self):
        self._client: Optional[chromadb.HttpClient] = None
        self._collection = None

    # ─────────────────────────────── Lifecycle ────────────────────────────────

    async def connect(self) -> None:
        """
        Establish connection to ChromaDB.
        Called once during app startup.
        """
        max_attempts = 6
        for attempt in range(1, max_attempts + 1):
            try:
                self._client = chromadb.HttpClient(
                    host=settings.chroma_host,
                    port=settings.chroma_port,
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                self._collection = self._client.get_or_create_collection(
                    name=settings.chroma_collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
                log.info(
                    "rag.connected",
                    host=settings.chroma_host,
                    collection=settings.chroma_collection_name,
                    doc_count=self._collection.count(),
                )
                return
            except Exception as exc:
                log.error(
                    "rag.connect_failed",
                    error=str(exc),
                    attempt=attempt,
                    max_attempts=max_attempts,
                )
                self._collection = None
                if attempt < max_attempts:
                    await asyncio.sleep(2)
        log.error("rag.unavailable", message="ChromaDB could not be reached after retries")

    async def disconnect(self) -> None:
        self._client = None
        self._collection = None

    # ─────────────────────────────── Query API ────────────────────────────────

    async def query(self, user_text: str) -> Optional[str]:
        """
        Return the best-matching FAQ context string,
        or None if nothing relevant is found.
        """
        if not self._collection:
            log.warning("rag.not_connected")
            return None

        try:
            results = self._collection.query(
                query_texts=[user_text],
                n_results=min(_TOP_K, self._collection.count() or 1),
                include=["documents", "distances", "metadatas"],
            )

            docs = results.get("documents", [[]])[0]
            distances = results.get("distances", [[]])[0]

            # Cosine distance → similarity: 1 - distance
            relevant_docs = [
                doc
                for doc, dist in zip(docs, distances)
                if (1 - dist) >= _RELEVANCE_THRESHOLD
            ]

            if not relevant_docs:
                log.debug("rag.no_relevant_docs", query=user_text[:60])
                return None

            context = "\n\n---\n\n".join(relevant_docs)
            log.debug("rag.hit", n_docs=len(relevant_docs), query=user_text[:60])
            return context

        except Exception as exc:
            log.error("rag.query_failed", error=str(exc))
            return None

    # ────────────────────────────── Admin helpers ─────────────────────────────

    def upsert_documents(
        self,
        documents: list[str],
        ids: list[str],
        metadatas: Optional[list[dict]] = None,
    ) -> None:
        """
        Synchronous helper for the init script to load FAQ data.
        Use scripts/init_chroma.py to pre-populate the collection.
        """
        if not self._collection:
            raise RuntimeError("RAGService is not connected. Call connect() first.")
        self._collection.upsert(
            documents=documents,
            ids=ids,
            metadatas=metadatas or [{} for _ in ids],
        )
        log.info("rag.upserted", n=len(documents))

    @property
    def is_ready(self) -> bool:
        return self._collection is not None
