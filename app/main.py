"""FastAPI 入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
"""

import logging

from fastapi import FastAPI

from app.api.internal import router as internal_router
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)

app = FastAPI(
    title="AI Data Insights AI Service",
    version="0.1.0",
)
app.include_router(internal_router)


@app.get("/healthz", tags=["ops"])
async def healthz() -> dict:
    """供 Java 侧与容器探活使用。"""
    return {"status": "ok", "provider": settings.provider}