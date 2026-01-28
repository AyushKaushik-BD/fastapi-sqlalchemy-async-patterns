from fastapi import FastAPI
from app.lifespan import lifespan

app = FastAPI(lifespan=lifespan)

@app.get("/health")
async def health_check():
    return {"status": "ok"}
