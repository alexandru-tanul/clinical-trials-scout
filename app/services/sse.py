"""Server-Sent Events utilities for real-time chat updates."""

import asyncio
from tortoise import connections


async def notify_chat_update(chat_id: int):
    """Send a PostgreSQL NOTIFY for chat update.

    This triggers all SSE listeners subscribed to this chat to receive an update.
    """
    conn = connections.get("default")
    await conn.execute_query(f"NOTIFY chat_updates, '{chat_id}'")
