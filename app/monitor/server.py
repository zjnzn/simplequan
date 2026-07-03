"""Monitor HTTP 服务 —— FastAPI 端点暴露监控数据。"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

_INDEX_HTML = (Path(__file__).parent / "templates" / "index.html").read_text(encoding="utf-8")


def build_app(monitor) -> FastAPI:
    """构建 FastAPI app，端点委托给 Monitor 查询。"""
    app = FastAPI(title="Quanquan Monitor", docs_url="/docs")

    @app.get("/")
    async def snapshot():
        """总览：master + 各 channel 一行汇总。"""
        return monitor.snapshot()

    @app.get("/ui", response_class=HTMLResponse)
    async def ui():
        """前端监控面板。"""
        return _INDEX_HTML

    @app.get("/channels")
    async def channels():
        """channel 列表。"""
        return monitor.channel_summary()

    @app.get("/channels/{cid}")
    async def channel_detail(cid: str):
        """单 channel 详情。"""
        detail = monitor.channel_detail(cid)
        if detail is None:
            raise HTTPException(404, f"channel '{cid}' 未找到")
        return detail

    @app.get("/channels/{cid}/klines")
    async def klines(cid: str, limit: int = Query(20, ge=1, le=500)):
        data = monitor.history(cid, "klines", limit)
        if data is None:
            raise HTTPException(404, f"channel '{cid}' 未找到")
        return data

    @app.get("/channels/{cid}/indicators")
    async def indicators(cid: str, limit: int = Query(20, ge=1, le=500)):
        data = monitor.history(cid, "indicators", limit)
        if data is None:
            raise HTTPException(404, f"channel '{cid}' 未找到")
        return data

    @app.get("/channels/{cid}/signals")
    async def signals(cid: str, limit: int = Query(20, ge=1, le=500)):
        data = monitor.history(cid, "signals", limit)
        if data is None:
            raise HTTPException(404, f"channel '{cid}' 未找到")
        return data

    @app.get("/channels/{cid}/orders")
    async def orders(cid: str, limit: int = Query(20, ge=1, le=500)):
        data = monitor.history(cid, "orders", limit)
        if data is None:
            raise HTTPException(404, f"channel '{cid}' 未找到")
        return data

    @app.get("/master")
    async def master():
        """主账号详情。"""
        return monitor.master_detail()

    return app


async def serve(app: FastAPI, host: str, port: int) -> None:
    """异步启动 uvicorn。"""
    import uvicorn
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()
