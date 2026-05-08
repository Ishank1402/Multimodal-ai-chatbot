"""
app/services/message_normalizer.py
───────────────────────────────────
Unified Router: converts raw JSON from Telegram and Web
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

    # ─────────────────────────────── Telegram ────────────────────────────────

    @staticmethod
    def from_telegram(payload: dict[str, Any]) -> NormalizedMessage | None:
        """
        Parse an Update object from the Telegram Bot API.
        Supports text messages and voice notes.
        Returns None if the update type is unsupported.
        """
        try:
            update = payload.get("message") or payload.get("edited_message")
            if not update:
                log.debug("telegram.unsupported_update_type", keys=list(payload.keys()))
                return None

            user = update.get("from", {})
            user_id = str(user.get("id", "unknown"))
            session_id = _make_session_id(MessageChannel.TELEGRAM, user_id)

            # ── Voice note ───────────────────────────────────────────────────
            if "voice" in update:
                voice = update["voice"]
                return NormalizedMessage(
                    channel=MessageChannel.TELEGRAM,
                    message_type=MessageType.VOICE,
                    user_id=user_id,
                    session_id=session_id,
                    audio_file_id=voice.get("file_id"),
                    raw_payload=payload,
                )

            # ── Text message ─────────────────────────────────────────────────
            if "text" in update:
                return NormalizedMessage(
                    channel=MessageChannel.TELEGRAM,
                    message_type=MessageType.TEXT,
                    user_id=user_id,
                    session_id=session_id,
                    text=update["text"],
                    raw_payload=payload,
                )

            log.debug("telegram.unhandled_message_type", update_keys=list(update.keys()))
            return None

        except Exception as exc:
            log.error("telegram.normalizer_error", error=str(exc), payload=payload)
            return None

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
