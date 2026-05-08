"""
scripts/init_db.py
───────────────────
Run once to initialize SQLite tables.
Usage:  python scripts/init_db.py
"""

import asyncio
import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.storage.database import ChatDatabase
from app.config import settings
import structlog

log = structlog.get_logger()


async def main():
    print(f"[init_db] Connecting to: {settings.sqlite_path}")
    db = ChatDatabase()
    await db.connect()
    print("[init_db] ✅  Tables created (chat_history, leads)")
    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
