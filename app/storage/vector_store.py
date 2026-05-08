"""
app/storage/vector_store.py
────────────────────────────
Thin helpers for initialising and managing the ChromaDB collection.
Used by init scripts and admin endpoints.
"""

from __future__ import annotations

import chromadb
import structlog
from chromadb.config import Settings as ChromaSettings

from app.config import settings

log = structlog.get_logger(__name__)


def get_chroma_client() -> chromadb.HttpClient:
    return chromadb.HttpClient(
        host=settings.chroma_host,
        port=settings.chroma_port,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def get_or_create_collection(client: chromadb.HttpClient = None):
    c = client or get_chroma_client()
    return c.get_or_create_collection(
        name=settings.chroma_collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def load_faq_documents(faq_data: list[dict]) -> int:
    """
    Batch-upsert FAQ documents into ChromaDB.

    Each dict in faq_data should have:
        id       : unique string identifier
        document : the text content to embed
        metadata : optional dict (e.g. {"category": "billing"})

    Returns the number of documents upserted.
    """
    client = get_chroma_client()
    collection = get_or_create_collection(client)

    ids = [item["id"] for item in faq_data]
    documents = [item["document"] for item in faq_data]
    metadatas = [item.get("metadata", {}) for item in faq_data]

    collection.upsert(documents=documents, ids=ids, metadatas=metadatas)
    log.info("vector_store.upserted", n=len(ids), collection=settings.chroma_collection_name)
    return len(ids)
