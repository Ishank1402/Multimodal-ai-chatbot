"""
app/services/monitoring.py
───────────────────────────
LangSmith + Langfuse tracing hooks.
Configures environment variables so LangChain picks them up automatically,
and provides a Langfuse callback handler when enabled.
"""

from __future__ import annotations

import os
from typing import Optional

import structlog

from app.config import settings

log = structlog.get_logger(__name__)


def configure_langsmith() -> None:
    """
    Set LangSmith environment variables.
    LangChain reads these automatically for all chain/model calls.
    """
    if settings.langchain_tracing_v2 and settings.langchain_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
        log.info("monitoring.langsmith_enabled", project=settings.langchain_project)
    else:
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        log.info("monitoring.langsmith_disabled")


def get_langfuse_callback():
    """
    Return a Langfuse callback handler if Langfuse is enabled and configured.
    Pass this into LangChain chain.invoke(config={"callbacks": [handler]}).
    """
    if not settings.langfuse_enabled:
        return None
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        log.warning("monitoring.langfuse_keys_missing")
        return None
    try:
        from langfuse.callback import CallbackHandler  # type: ignore
        handler = CallbackHandler(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        log.info("monitoring.langfuse_enabled")
        return handler
    except ImportError:
        log.warning("monitoring.langfuse_not_installed")
        return None
    except Exception as exc:
        log.error("monitoring.langfuse_init_failed", error=str(exc))
        return None
