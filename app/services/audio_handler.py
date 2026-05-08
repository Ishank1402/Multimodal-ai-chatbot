"""
app/services/audio_handler.py
──────────────────────────────
Downloads voice notes from Telegram and transcribes them
using OpenAI Whisper (running locally, no API calls).

Flow:
    1. Resolve the audio download URL for the given platform.
    2. Stream-download the file to a temp location.
    3. Run Whisper to get the transcript.
    4. Clean up temp files.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Optional

import httpx
import structlog

from app.config import settings
from app.models import MessageChannel, NormalizedMessage

log = structlog.get_logger(__name__)

# Whisper model is loaded once and shared — it's expensive to reload.
_whisper_model = None


def _get_whisper_model():
    """Lazy-load Whisper model on first use (avoids slowing app startup)."""
    global _whisper_model
    if _whisper_model is None:
        import whisper  # type: ignore
        log.info("whisper.loading_model", size=settings.whisper_model_size)
        os.makedirs(settings.whisper_model_dir, exist_ok=True)
        _whisper_model = whisper.load_model(
            settings.whisper_model_size,
            device=settings.whisper_device,
            download_root=settings.whisper_model_dir,
        )
        log.info("whisper.model_ready")
    return _whisper_model


class AudioHandler:
    """Handles downloading and transcribing voice messages."""

    def __init__(self):
        self._http = httpx.AsyncClient(timeout=60.0)

    # ─────────────────────────────── Public API ───────────────────────────────

    async def transcribe(self, message: NormalizedMessage) -> Optional[str]:
        """
        Main entry point. Returns transcribed text or None on failure.
        """
        try:
            audio_bytes = await self._download_audio(message)
            if not audio_bytes:
                return None
            transcript = await self._run_whisper(audio_bytes)
            log.info(
                "audio.transcription_complete",
                channel=message.channel,
                chars=len(transcript or ""),
            )
            return transcript
        except Exception as exc:
            log.error("audio.transcribe_failed", error=str(exc), exc_info=True)
            return None

    # ─────────────────────────── Download helpers ─────────────────────────────

    async def _download_audio(self, message: NormalizedMessage) -> Optional[bytes]:
        if message.channel == MessageChannel.TELEGRAM:
            return await self._download_telegram_voice(message.audio_file_id)
        elif message.audio_url:
            return await self._download_url(message.audio_url)
        log.warning("audio.no_source", channel=message.channel)
        return None

    async def _download_telegram_voice(self, file_id: Optional[str]) -> Optional[bytes]:
        """
        Two-step Telegram download:
        1. getFile  → get file_path from Telegram servers
        2. Download from https://api.telegram.org/file/bot{token}/{file_path}
        """
        if not file_id:
            return None
        try:
            base = f"https://api.telegram.org/bot{settings.telegram_bot_token}"

            # Step 1: resolve file_path
            resp = await self._http.get(f"{base}/getFile", params={"file_id": file_id})
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                log.error("telegram.get_file_failed", response=data)
                return None
            file_path = data["result"]["file_path"]

            # Step 2: download binary content
            download_url = f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_path}"
            return await self._download_url(download_url)
        except Exception as exc:
            log.error("telegram.download_voice_failed", error=str(exc))
            return None

    async def _download_url(
        self, url: str, headers: Optional[dict] = None
    ) -> Optional[bytes]:
        try:
            resp = await self._http.get(url, headers=headers or {}, follow_redirects=True)
            resp.raise_for_status()
            return resp.content
        except Exception as exc:
            log.error("audio.download_url_failed", url=url, error=str(exc))
            return None

    # ───────────────────────────── Whisper runner ─────────────────────────────

    async def _run_whisper(self, audio_bytes: bytes) -> Optional[str]:
        """
        Write audio to a temp file and run Whisper in a thread pool
        so we don't block the async event loop.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_transcribe, audio_bytes)

    @staticmethod
    def _sync_transcribe(audio_bytes: bytes) -> Optional[str]:
        """Synchronous transcription — runs in thread pool."""
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        try:
            model = _get_whisper_model()
            result = model.transcribe(tmp_path, fp16=False)
            return result.get("text", "").strip() or None
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    async def aclose(self):
        await self._http.aclose()
