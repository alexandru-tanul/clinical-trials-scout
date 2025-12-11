from contextlib import asynccontextmanager

from fastapi import FastAPI
from tortoise import Tortoise

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    # Startup
    await Tortoise.init(config=settings.TORTOISE_ORM)
    await Tortoise.generate_schemas()  # Create tables if they don't exist
    yield
    # Shutdown
    await Tortoise.close_connections()