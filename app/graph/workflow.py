"""
app/graph/workflow.py
──────────────────────
The core LangGraph stateful workflow.

Node execution order:
    load_history → rag_lookup → generate_response → save_history

If RAG returns relevant context → LLM uses it (grounded response).
If RAG returns nothing       → LLM falls back to its own knowledge.
"""

from __future__ import annotations

from typing import Any

import structlog
# pyrefly: ignore [missing-import]
from langgraph.graph import END, StateGraph

from app.models import ChatState, NormalizedMessage
from app.services.llm_chain import LLMService
from app.services.rag_service import RAGService
from app.storage.database import ChatDatabase

log = structlog.get_logger(__name__)


# =============================================================================
# Workflow nodes (each is a pure async function operating on ChatState)
# =============================================================================

async def node_load_history(state: dict[str, Any], db: ChatDatabase) -> dict[str, Any]:
    """Load the last N turns of conversation from SQLite."""
    try:
        msg: NormalizedMessage = state["message"]
        history = await db.get_history(session_id=msg.session_id, limit=10)
        state["history"] = history
        log.debug("graph.history_loaded", turns=len(history), session=msg.session_id)
    except Exception as exc:
        log.error("graph.load_history_failed", error=str(exc))
        state["history"] = []
    return state


async def node_rag_lookup(state: dict[str, Any], rag: RAGService) -> dict[str, Any]:
    """Query ChromaDB for relevant FAQ context."""
    try:
        msg: NormalizedMessage = state["message"]
        query_text = msg.text or ""
        if query_text:
            context = await rag.query(query_text)
            state["rag_context"] = context
            log.debug(
                "graph.rag_result",
                found=bool(context),
                query=query_text[:60],
            )
        else:
            state["rag_context"] = None
    except Exception as exc:
        log.error("graph.rag_lookup_failed", error=str(exc))
        state["rag_context"] = None
    return state


async def node_generate_response(
    state: dict[str, Any], llm: LLMService
) -> dict[str, Any]:
    """Call the LLM (Groq / Gemini) with history and optional RAG context."""
    try:
        msg: NormalizedMessage = state["message"]
        user_text = msg.text or "(no text)"

        response, provider = await llm.generate(
            user_message=user_text,
            history=state.get("history", []),
            rag_context=state.get("rag_context"),
        )
        state["llm_response"] = response
        state["provider_used"] = provider
        log.info("graph.response_generated", provider=provider.value, session=msg.session_id)
    except Exception as exc:
        log.error("graph.generate_response_failed", error=str(exc))
        state["llm_response"] = (
            "I'm having trouble generating a response right now. Please try again shortly."
        )
        state["error"] = str(exc)
    return state


async def node_save_history(state: dict[str, Any], db: ChatDatabase) -> dict[str, Any]:
    """Persist the user message and assistant reply to SQLite."""
    try:
        msg: NormalizedMessage = state["message"]
        await db.save_turn(
            session_id=msg.session_id,
            channel=msg.channel.value,
            user_text=msg.text or "",
            assistant_text=state.get("llm_response", ""),
        )
        log.debug("graph.history_saved", session=msg.session_id)
    except Exception as exc:
        log.error("graph.save_history_failed", error=str(exc))
    return state


# =============================================================================
# Graph factory
# =============================================================================

def build_workflow(
    db: ChatDatabase,
    rag: RAGService,
    llm: LLMService,
) -> Any:
    """
    Compile and return the LangGraph StateGraph.
    Dependencies are injected at build time via closures.
    """

    # Wrap nodes with injected dependencies
    async def _load_history(state):
        return await node_load_history(state, db)

    async def _rag_lookup(state):
        return await node_rag_lookup(state, rag)

    async def _generate_response(state):
        return await node_generate_response(state, llm)

    async def _save_history(state):
        return await node_save_history(state, db)

    # Build graph
    graph = StateGraph(dict)
    graph.add_node("load_history", _load_history)
    graph.add_node("rag_lookup", _rag_lookup)
    graph.add_node("generate_response", _generate_response)
    graph.add_node("save_history", _save_history)

    # Define execution order
    graph.set_entry_point("load_history")
    graph.add_edge("load_history", "rag_lookup")
    graph.add_edge("rag_lookup", "generate_response")
    graph.add_edge("generate_response", "save_history")
    graph.add_edge("save_history", END)

    return graph.compile()


class ChatWorkflow:
    """
    High-level wrapper around the compiled LangGraph.
    Used by all router endpoints.
    """

    def __init__(self, db: ChatDatabase, rag: RAGService, llm: LLMService):
        self._graph = build_workflow(db, rag, llm)

    async def run(self, message: NormalizedMessage) -> dict[str, Any]:
        """
        Execute the full workflow for a given NormalizedMessage.
        Returns the final state dict.
        """
        initial_state: dict[str, Any] = {
            "message": message,
            "history": [],
            "rag_context": None,
            "llm_response": None,
            "provider_used": None,
            "error": None,
            "metadata": {},
        }

        config = {"configurable": {"thread_id": message.session_id}}

        try:
            final_state = await self._graph.ainvoke(initial_state, config=config)
            return final_state
        except Exception as exc:
            log.error("workflow.run_failed", error=str(exc), exc_info=True)
            return {
                **initial_state,
                "llm_response": "An unexpected error occurred. Please try again.",
                "error": str(exc),
            }
