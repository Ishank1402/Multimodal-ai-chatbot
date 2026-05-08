"""
app/models.py — Shared Pydantic models used across the application.
All incoming messages (Telegram, Web) are normalised into
a single `NormalizedMessage` before reaching the LangGraph workflow.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class MessageChannel(str, Enum):
    TELEGRAM = "telegram"
    WEB = "web"


class MessageType(str, Enum):
    TEXT = "text"
    VOICE = "voice"
    SYSTEM = "system"


class LLMProvider(str, Enum):
    GROQ = "groq"
    GEMINI = "gemini"


# =============================================================================
# Canonical message format — everything flows through this
# =============================================================================

class NormalizedMessage(BaseModel):
    """
    Platform-agnostic representation of an incoming user message.
    Created by MessageNormalizer from raw webhook payloads.
    """
    channel: MessageChannel
    message_type: MessageType
    user_id: str                          # Platform-specific user identifier
    session_id: str                       # Used as the LangGraph thread_id
    text: Optional[str] = None            # Populated for text msgs or after STT
    audio_url: Optional[str] = None       # Raw audio URL before transcription
    audio_file_id: Optional[str] = None   # Telegram file_id for voice notes
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# LangGraph workflow state
# =============================================================================

class ChatState(BaseModel):
    """State object threaded through the LangGraph workflow nodes."""
    message: NormalizedMessage
    history: list[dict[str, str]] = Field(default_factory=list)
    rag_context: Optional[str] = None     # Retrieved FAQ snippets
    llm_response: Optional[str] = None
    provider_used: Optional[LLMProvider] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Webhook payload models (for FastAPI request validation)
# =============================================================================

class WebChatMessage(BaseModel):
    """Incoming payload from the local web chat widget."""
    session_id: str
    text: str


class WebChatResponse(BaseModel):
    """Response returned to the web chat widget."""
    session_id: str
    reply: str
    provider: Optional[str] = None


# =============================================================================
# Storage models
# =============================================================================

class ChatHistoryRecord(BaseModel):
    session_id: str
    role: str              # "user" | "assistant"
    content: str
    channel: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class LeadRecord(BaseModel):
    session_id: str
    channel: str
    user_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
