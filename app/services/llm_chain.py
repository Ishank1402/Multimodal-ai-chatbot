"""
app/services/llm_chain.py
──────────────────────────
LLM integration layer supporting Groq (Llama 3) and Google Gemini.
Implements a fallback strategy: try Groq → fall back to Gemini on error.
"""

from __future__ import annotations

from typing import Optional

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.language_models.chat_models import BaseChatModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.models import LLMProvider

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """Your name is Nova. You are a helpful and friendly AI assistant integrated into a messaging platform. Introduce yourself as Nova if asked.
Answer concisely and accurately. If you don't know something, say so clearly.
When given context from a knowledge base, prioritise it over your general knowledge.
Keep responses under 300 words unless a longer answer is genuinely necessary."""


def _build_groq_llm() -> Optional[BaseChatModel]:
    if not settings.groq_api_key:
        log.warning("llm.groq_key_missing")
        return None
    try:
        from langchain_groq import ChatGroq  # type: ignore
        return ChatGroq(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            temperature=0.3,
            max_tokens=1024,
        )
    except Exception as exc:
        log.error("llm.groq_init_failed", error=str(exc))
        return None


def _build_gemini_llm() -> Optional[BaseChatModel]:
    if not settings.google_api_key:
        log.warning("llm.gemini_key_missing")
        return None
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore
        return ChatGoogleGenerativeAI(
            google_api_key=settings.google_api_key,
            model=settings.gemini_model,
            temperature=0.3,
            max_output_tokens=1024,
            convert_system_message_to_human=True,  # Gemini quirk
            max_retries=1,  # Fail fast on rate-limit; our fallback handles retries
        )
    except Exception as exc:
        log.error("llm.gemini_init_failed", error=str(exc))
        return None


class LLMService:
    """
    Wraps Groq and Gemini behind a unified async interface.
    Supports three strategies: groq-only, gemini-only, fallback (groq → gemini).
    """

    def __init__(self):
        self._groq = _build_groq_llm()
        self._gemini = _build_gemini_llm()

    # ─────────────────────────────── Public API ───────────────────────────────

    async def generate(
        self,
        user_message: str,
        history: list[dict[str, str]],
        rag_context: Optional[str] = None,
    ) -> tuple[str, LLMProvider]:
        """
        Generate a reply. Returns (response_text, provider_used).
        Raises RuntimeError if all providers fail.
        """
        messages = self._build_messages(user_message, history, rag_context)

        provider = settings.llm_provider

        if provider == "groq":
            return await self._call(self._groq, messages, LLMProvider.GROQ)

        if provider == "gemini":
            return await self._call(self._gemini, messages, LLMProvider.GEMINI)

        # Fallback: try groq first, then gemini
        if self._groq:
            try:
                return await self._call(self._groq, messages, LLMProvider.GROQ)
            except Exception as exc:
                log.warning("llm.groq_failed_falling_back", error=str(exc))

        if self._gemini:
            return await self._call(self._gemini, messages, LLMProvider.GEMINI)

        raise RuntimeError("All LLM providers failed or are unconfigured.")

    # ────────────────────────────── Private helpers ───────────────────────────

    @staticmethod
    def _build_messages(
        user_message: str,
        history: list[dict[str, str]],
        rag_context: Optional[str],
    ) -> list:
        """Construct LangChain message list from history + optional RAG context."""
        system_content = _SYSTEM_PROMPT
        if rag_context:
            system_content += (
                "\n\n### Relevant knowledge base context:\n" + rag_context
            )

        msgs = [SystemMessage(content=system_content)]

        # Replay conversation history (last 10 turns to stay within token limits)
        for turn in history[-10:]:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "user":
                msgs.append(HumanMessage(content=content))
            else:
                from langchain_core.messages import AIMessage
                msgs.append(AIMessage(content=content))

        msgs.append(HumanMessage(content=user_message))
        return msgs

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    async def _call(
        self,
        llm: Optional[BaseChatModel],
        messages: list,
        provider: LLMProvider,
    ) -> tuple[str, LLMProvider]:
        if llm is None:
            raise RuntimeError(f"LLM provider {provider} is not initialised.")

        import asyncio
        log.debug("llm.calling", provider=provider)
        try:
            response = await asyncio.wait_for(llm.ainvoke(messages), timeout=30)
        except asyncio.TimeoutError:
            raise RuntimeError(f"LLM provider {provider} timed out after 30s.")
        text = response.content.strip()
        log.info("llm.response", provider=provider, chars=len(text))
        return text, provider
