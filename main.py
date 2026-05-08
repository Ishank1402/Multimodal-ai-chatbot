"""
main.py — FastAPI application entry point.
Wires together all services and mounts all routers.
"""

from __future__ import annotations

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.graph.workflow import ChatWorkflow
from app.routers import telegram, webchat
from app.services.audio_handler import AudioHandler
from app.services.llm_chain import LLMService
from app.services.monitoring import configure_langsmith
from app.services.rag_service import RAGService
from app.storage.database import ChatDatabase

# Configure structured logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer() if settings.app_debug else structlog.processors.JSONRenderer(),
    ]
)

log = structlog.get_logger("main")


# =============================================================================
# Lifespan — startup & shutdown hooks
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initialise all services on startup; cleanly shut them down on exit.
    Services are attached to app.state so routers can access them.
    """
    log.info("app.starting", env=settings.app_env)

    # Configure tracing before any LangChain calls
    configure_langsmith()

    # ── Database ─────────────────────────────────────────────────────────────
    db = ChatDatabase()
    await db.connect()
    app.state.db = db

    # ── ChromaDB / RAG ────────────────────────────────────────────────────────
    rag = RAGService()
    await rag.connect()
    app.state.rag = rag

    # ── LLM ───────────────────────────────────────────────────────────────────
    llm = LLMService()
    app.state.llm = llm

    # ── Audio handler ─────────────────────────────────────────────────────────
    audio_handler = AudioHandler()
    app.state.audio_handler = audio_handler

    # ── LangGraph workflow ────────────────────────────────────────────────────
    workflow = ChatWorkflow(db=db, rag=rag, llm=llm)
    app.state.workflow = workflow

    log.info("app.ready")
    yield

    # ── Graceful shutdown ─────────────────────────────────────────────────────
    log.info("app.shutting_down")
    await db.disconnect()
    await rag.disconnect()
    await audio_handler.aclose()
    log.info("app.stopped")


# =============================================================================
# FastAPI app
# =============================================================================

app = FastAPI(
    title="AI Chatbot — Telegram / Web",
    description="Multi-channel AI chatbot powered by LangGraph, Groq, and Gemini.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_debug else None,
    redoc_url="/redoc" if settings.app_debug else None,
)

# ── CORS (allow the local web widget) ─────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.app_debug else ["https://your-domain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(telegram.router)
app.include_router(webchat.router)


# =============================================================================
# Health & info endpoints
# =============================================================================

@app.get("/health", tags=["System"])
async def health_check():
    """Liveness probe used by Docker and load balancers."""
    return {
        "status": "ok",
        "env": settings.app_env,
        "rag_ready": app.state.rag.is_ready,
    }


@app.get("/info", tags=["System"])
async def app_info():
    """Basic app metadata (non-sensitive)."""
    return {
        "app": "AI Chatbot",
        "version": "1.0.0",
        "provider": settings.llm_provider,
        "whisper_model": settings.whisper_model_size,
        "chroma_collection": settings.chroma_collection_name,
    }
