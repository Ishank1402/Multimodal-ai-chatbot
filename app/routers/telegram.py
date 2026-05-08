"""
app/routers/telegram.py
────────────────────────
Telegram Bot API webhook endpoint.

Telegram sends all updates to:  POST /webhook/telegram

Setup (one-time, call after deployment):
    curl -X POST "https://api.telegram.org/bot{TOKEN}/setWebhook" \
         -d "url=https://your-domain.com/webhook/telegram"
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from app.models import MessageType
from app.services.audio_handler import AudioHandler
from app.services.message_normalizer import MessageNormalizer

log = structlog.get_logger(__name__)
router = APIRouter(tags=["Telegram"])

_http = httpx.AsyncClient(timeout=30.0)


@router.post("/webhook/telegram", status_code=status.HTTP_200_OK)
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receive and process Telegram updates.
    Always return 200 immediately — Telegram retries on non-200 responses.
    """
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        # Malformed JSON — return 200 anyway so Telegram doesn't retry
        log.warning("telegram.malformed_json")
        return {"ok": True}

    # Normalise the incoming payload
    message = MessageNormalizer.from_telegram(payload)
    if message is None:
        return {"ok": True}

    # Retrieve app-level services injected into request.app.state
    workflow = request.app.state.workflow
    audio_handler: AudioHandler = request.app.state.audio_handler

    # Process voice notes: transcribe first, then treat as text
    if message.message_type == MessageType.VOICE:
        transcript = await audio_handler.transcribe(message)
        if not transcript:
            await _send_telegram_message(
                chat_id=_get_chat_id(payload),
                text="Sorry, I couldn't understand the voice message. Please try again.",
            )
            return {"ok": True}
        message.text = transcript
        message.message_type = MessageType.TEXT

    if not message.text:
        return {"ok": True}

    # Run the LangGraph workflow in the background so we can return 200 fast
    chat_id = _get_chat_id(payload)
    background_tasks.add_task(
        _process_and_reply_telegram, workflow, message, chat_id
    )
    return {"ok": True}


async def _process_and_reply_telegram(workflow, message, chat_id: int):
    """Background task: run workflow and send reply via Telegram."""
    try:
        result = await workflow.run(message)
        reply = result.get("llm_response", "Sorry, something went wrong.")
        await _send_telegram_message(chat_id=chat_id, text=reply)
    except Exception as exc:
        log.error("telegram.reply_failed", error=str(exc), chat_id=chat_id)
        await _send_telegram_message(
            chat_id=chat_id, text="An error occurred. Please try again later."
        )


async def _send_telegram_message(chat_id: int, text: str) -> None:
    """Send a text message back to the user via the Telegram Bot API."""
    from app.config import settings
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        resp = await _http.post(url, json={"chat_id": chat_id, "text": text})
        resp.raise_for_status()
        log.debug("telegram.message_sent", chat_id=chat_id)
    except Exception as exc:
        log.error("telegram.send_failed", error=str(exc), chat_id=chat_id)


def _get_chat_id(payload: dict) -> int:
    """Extract chat.id from a Telegram Update payload."""
    msg = payload.get("message") or payload.get("edited_message", {})
    return msg.get("chat", {}).get("id", 0)
