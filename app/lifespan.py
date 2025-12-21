import asyncio
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from tortoise import Tortoise

from app.config import settings


# Global state for PostgreSQL LISTEN/NOTIFY
pg_listener_conn = None
pg_listener_task = None
chat_update_subscribers = {}  # {chat_id: [queue1, queue2, ...]}


async def pg_listener():
    """Background task to listen for PostgreSQL notifications."""
    global pg_listener_conn

    # Connect to PostgreSQL
    pg_listener_conn = await asyncpg.connect(settings.DATABASE_URL)

    # Listen to chat_updates channel
    await pg_listener_conn.add_listener('chat_updates', handle_chat_update)

    # Keep the connection alive
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        await pg_listener_conn.close()


async def handle_chat_update(connection, pid, channel, payload):
    """Handle incoming chat update notifications."""
    # Payload format: "chat_id"
    chat_id = int(payload)

    # Notify all subscribers for this chat
    if chat_id in chat_update_subscribers:
        for queue in chat_update_subscribers[chat_id]:
            try:
                await queue.put({"chat_id": chat_id})
            except:
                pass  # Subscriber might have disconnected


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    global pg_listener_task

    # Startup
    await Tortoise.init(config=settings.TORTOISE_ORM)
    await Tortoise.generate_schemas()  # Create tables if they don't exist

    # Start PostgreSQL listener
    pg_listener_task = asyncio.create_task(pg_listener())

    yield

    # Shutdown
    if pg_listener_task:
        pg_listener_task.cancel()
        try:
            await pg_listener_task
        except asyncio.CancelledError:
            pass

    await Tortoise.close_connections()