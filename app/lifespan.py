from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.db import engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    # Example: test DB connectivity at startup
    async with engine.begin() as conn:
        await conn.run_sync(lambda _: None)

    yield

    # --- Shutdown ---
    await engine.dispose()
