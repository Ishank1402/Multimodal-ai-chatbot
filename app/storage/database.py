"""
app/storage/database.py
────────────────────────
Async SQLite data layer using SQLAlchemy Core (no ORM overhead).
Tables: chat_history, leads
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
import structlog

from app.config import settings

log = structlog.get_logger(__name__)

# =============================================================================
# Schema definitions
# =============================================================================

metadata = sa.MetaData()

chat_history = sa.Table(
    "chat_history",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("session_id", sa.String(64), nullable=False, index=True),
    sa.Column("channel", sa.String(20), nullable=False),
    sa.Column("role", sa.String(10), nullable=False),     # "user" | "assistant"
    sa.Column("content", sa.Text, nullable=False),
    sa.Column("timestamp", sa.DateTime, default=datetime.utcnow),
)

leads = sa.Table(
    "leads",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("session_id", sa.String(64), nullable=False, index=True),
    sa.Column("channel", sa.String(20), nullable=False),
    sa.Column("user_id", sa.String(128), nullable=False),
    sa.Column("name", sa.String(256)),
    sa.Column("email", sa.String(256)),
    sa.Column("phone", sa.String(64)),
    sa.Column("notes", sa.Text),
    sa.Column("timestamp", sa.DateTime, default=datetime.utcnow),
)


# =============================================================================
# Database service
# =============================================================================

class ChatDatabase:
    def __init__(self):
        self._engine: Optional[AsyncEngine] = None

    # ─────────────────────────────── Lifecycle ────────────────────────────────

    async def connect(self) -> None:
        import os
        os.makedirs(settings.sqlite_path.rsplit("/", 1)[0], exist_ok=True)

        self._engine = create_async_engine(
            settings.sqlite_url,
            echo=settings.app_debug,
            connect_args={"check_same_thread": False},
        )
        async with self._engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
        log.info("database.connected", path=settings.sqlite_path)

    async def disconnect(self) -> None:
        if self._engine:
            await self._engine.dispose()
            log.info("database.disconnected")

    # ──────────────────────────── Chat history ────────────────────────────────

    async def save_turn(
        self,
        session_id: str,
        channel: str,
        user_text: str,
        assistant_text: str,
    ) -> None:
        """Persist a complete user ↔ assistant turn."""
        async with self._engine.begin() as conn:
            now = datetime.utcnow()
            await conn.execute(
                chat_history.insert(),
                [
                    {"session_id": session_id, "channel": channel, "role": "user",
                     "content": user_text, "timestamp": now},
                    {"session_id": session_id, "channel": channel, "role": "assistant",
                     "content": assistant_text, "timestamp": now},
                ],
            )

    async def get_history(
        self, session_id: str, limit: int = 20
    ) -> list[dict[str, str]]:
        """Return the last `limit` turns as a list of {role, content} dicts."""
        async with self._engine.connect() as conn:
            result = await conn.execute(
                sa.select(chat_history.c.role, chat_history.c.content)
                .where(chat_history.c.session_id == session_id)
                .order_by(chat_history.c.id.desc())
                .limit(limit)
            )
            rows = result.fetchall()
        # Reverse so oldest turn is first
        return [{"role": r.role, "content": r.content} for r in reversed(rows)]

    # ────────────────────────────── Lead capture ──────────────────────────────

    async def upsert_lead(
        self,
        session_id: str,
        channel: str,
        user_id: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> None:
        """Insert or update a lead record (upsert by session_id)."""
        async with self._engine.begin() as conn:
            existing = await conn.execute(
                sa.select(leads.c.id).where(leads.c.session_id == session_id)
            )
            row = existing.fetchone()

            if row:
                await conn.execute(
                    leads.update()
                    .where(leads.c.session_id == session_id)
                    .values(name=name, email=email, phone=phone, notes=notes)
                )
            else:
                await conn.execute(
                    leads.insert().values(
                        session_id=session_id,
                        channel=channel,
                        user_id=user_id,
                        name=name,
                        email=email,
                        phone=phone,
                        notes=notes,
                        timestamp=datetime.utcnow(),
                    )
                )

    async def get_leads(self, limit: int = 100) -> list[dict]:
        """Fetch all leads (for admin use)."""
        async with self._engine.connect() as conn:
            result = await conn.execute(
                sa.select(leads).order_by(leads.c.timestamp.desc()).limit(limit)
            )
            return [dict(row._mapping) for row in result.fetchall()]
