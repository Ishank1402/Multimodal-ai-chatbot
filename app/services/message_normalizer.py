"""
app/services/message_normalizer.py
───────────────────────────────────
Unified Router: converts raw JSON from Web
into a single NormalizedMessage object.
"""

from __future__ import annotations

import hashlib
from typing import Any

import structlog

from app.models import MessageChannel, MessageType, NormalizedMessage

log = structlog.get_logger(__name__)


def _make_session_id(channel: MessageChannel, user_id: str) -> str:
    """
    Deterministic session ID so the same user always resumes the same
    LangGraph thread across restarts.
    """
    raw = f"{channel.value}:{user_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


class MessageNormalizer:
    """
    Stateless helper that parses raw webhook payloads into NormalizedMessage.
    Each public method corresponds to one platform.
    """

    # ─────────────────────────────── Web ─────────────────────────────────────

    @staticmethod
    def from_web(session_id: str, text: str) -> NormalizedMessage:
        """Create a NormalizedMessage from the web chat widget payload."""
        return NormalizedMessage(
            channel=MessageChannel.WEB,
            message_type=MessageType.TEXT,
            user_id=session_id,  # For web, session_id is the user identifier
            session_id=session_id,
            text=text,
        )
