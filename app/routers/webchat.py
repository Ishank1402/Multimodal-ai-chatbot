"""
app/routers/webchat.py
───────────────────────
Web chat endpoint — supports both REST (POST) and WebSocket.

REST endpoint:   POST /chat
WebSocket:       WS   /ws/{session_id}
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, status, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse

from app.models import WebChatMessage, WebChatResponse
from app.services.message_normalizer import MessageNormalizer
from app.services.audio_handler import AudioHandler

log = structlog.get_logger(__name__)
router = APIRouter(tags=["Web Chat"])


# =============================================================================
# Serve the HTML widget
# =============================================================================

@router.get("/", response_class=FileResponse)
async def serve_widget():
    """Serve the standalone web chat widget."""
    return FileResponse("static/index.html")


# =============================================================================
# REST endpoint
# =============================================================================

@router.post("/chat", response_model=WebChatResponse, status_code=status.HTTP_200_OK)
async def chat_rest(body: WebChatMessage, request: Request):
    """
    Simple REST POST endpoint for the web chat widget.
    Body: { "session_id": "...", "text": "..." }
    """
    if not body.session_id:
        body.session_id = str(uuid.uuid4())

    workflow = request.app.state.workflow
    message = MessageNormalizer.from_web(session_id=body.session_id, text=body.text)

    result = await workflow.run(message)
    reply = result.get("llm_response", "I'm having trouble right now. Please try again.")
    provider = result.get("provider_used")

    return WebChatResponse(
        session_id=body.session_id,
        reply=reply,
        provider=provider.value if provider else None,
    )


@router.post("/chat/audio", response_model=WebChatResponse, status_code=status.HTTP_200_OK)
async def chat_audio(request: Request, session_id: str = Form(...), audio: UploadFile = File(...)):
    """
    Accepts an audio file from the web widget, transcribes it locally,
    and returns the LLM's text reply.
    """
    audio_bytes = await audio.read()
    
    audio_handler = AudioHandler()
    try:
        transcript = await audio_handler._run_whisper(audio_bytes)
    except Exception as e:
        import traceback
        return WebChatResponse(
            session_id=session_id,
            reply=f"Backend Error: {traceback.format_exc()}"
        )
    finally:
        await audio_handler.aclose()

    if not transcript:
        return WebChatResponse(
            session_id=session_id,
            reply="Sorry, I could not transcribe the audio. Please try again."
        )

    workflow = request.app.state.workflow
    message = MessageNormalizer.from_web(session_id=session_id, text=transcript)
    result = await workflow.run(message)
    
    reply = result.get("llm_response", "I'm having trouble right now. Please try again.")
    provider = result.get("provider_used")

    return WebChatResponse(
        session_id=session_id,
        reply=reply,
        provider=provider.value if provider else None,
        transcript=transcript,
    )


# =============================================================================
# WebSocket endpoint
# =============================================================================

@router.websocket("/ws/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str, request: Request = None):
    """
    WebSocket endpoint for real-time chat.
    Client sends plain text; server streams back the reply.
    """
    await websocket.accept()
    workflow = websocket.app.state.workflow  # type: ignore[attr-defined]

    log.info("websocket.connected", session_id=session_id)
    try:
        while True:
            user_text = await websocket.receive_text()
            if not user_text.strip():
                continue

            message = MessageNormalizer.from_web(session_id=session_id, text=user_text)
            result = await workflow.run(message)
            reply = result.get("llm_response", "Something went wrong.")

            await websocket.send_json(
                {
                    "reply": reply,
                    "session_id": session_id,
                    "provider": (
                        result["provider_used"].value
                        if result.get("provider_used")
                        else None
                    ),
                }
            )
    except WebSocketDisconnect:
        log.info("websocket.disconnected", session_id=session_id)
    except Exception as exc:
        log.error("websocket.error", error=str(exc), session_id=session_id)
        try:
            await websocket.send_json({"error": "An unexpected error occurred."})
        except Exception:
            pass
