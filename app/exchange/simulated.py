"""SimulatedExchange —— ExchangePort 的内存模拟实现。

不连网，纯内存驱动。用于离线开发 handler 闭环和测试。
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from core.domain.config import AppConfig, ExchangeConfig

logger = logging.getLogger(__name__)


class SimulatedExchange:
    """模拟交易所。实现 ExchangePort 全部方法，纯内存。"""

    def __init__(
        self,
        cfg: ExchangeConfig | None = None,
        app_config: AppConfig | None = None,
    ) -> None:
        self._cfg = cfg or ExchangeConfig()
        self._app_config = app_config

        # 内部状态
        self._markets: dict[str, dict] = {}
        self._orders: dict[str, dict] = {}
        self._balance: dict[str, dict] = {
            "USDT": {"total": 10000.0, "free": 10000.0, "used": 0.0},
        }

        # watch_* 的数据通道：key → list[pending_data]，配合 asyncio.Event
        self._ohlcv_queues: dict[str, asyncio.Queue] = {}
        self._order_book_queues: dict[str, asyncio.Queue] = {}
        self._trade_queues: dict[str, asyncio.Queue] = {}
        self._order_queues: dict[str, asyncio.Queue] = {}

        self._closed = False

    # ============================================================
    # 账户
    # ============================================================

    async def fetch_balance(self) -> dict:
        return {"info": {}, **{k: dict(v) for k, v in self._balance.items()}}

    async def fetch_positions(self, symbols: list[str]) -> list[dict]:
        return []

    async def fetch_leverage(self, symbol: str) -> dict:
        return {"leverage": 1, "marginMode": "cross"}

    # ============================================================
    # 市场
    # ============================================================

    async def load_markets(self) -> dict:
        """返回 config 中所有 symbol 的占位市场信息。"""
        if self._app_config is None:
            return {}

        for ch in self._app_config.channels:
            if ch.symbol in self._markets:
                continue
            self._markets[ch.symbol] = {
                "symbol": ch.symbol,
                "market": ch.market,
                "precision": {"amount": 8, "price": 8},
                "limits": {
                    "amount": {"min": 0.001, "max": 1000000},
                    "cost": {"min": 1.0, "max": None},
                    "price": {"min": None, "max": None},
                },
                "fees": {"trading": {"maker": 0.0002, "taker": 0.0004}},
                "contractSize": 1.0,
                "settle": "USDT",
                "linear": True,
            }
        return dict(self._markets)

    # ============================================================
    # 订单
    # ============================================================

    async def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: float | None = None,
    ) -> dict:
        order_id = str(uuid.uuid4())[:8]
        fill_price = price if price else 50000.0  # 占位成交价
        raw = {
            "id": order_id,
            "clientOrderId": order_id,
            "symbol": symbol,
            "side": side.lower(),
            "type": order_type.lower(),
            "amount": amount,
            "price": price,
            "filled": amount,
            "average": fill_price,
            "status": "closed",  # 立即成交
            "cost": amount * fill_price,
        }
        self._orders[order_id] = raw

        # 推送到 watch_orders 回报队列
        q = self._order_queues.setdefault(symbol, asyncio.Queue())
        await q.put(raw)

        logger.info("模拟下单: %s %s %s 数量=%s 成交价=%s", symbol, side, order_type, amount, fill_price)
        return raw

    async def cancel_order(self, order_id: str, symbol: str) -> dict:
        raw = self._orders.get(order_id, {})
        raw = {**raw, "status": "canceled"}
        self._orders[order_id] = raw
        q = self._order_queues.setdefault(symbol, asyncio.Queue())
        await q.put(raw)
        return raw

    # ============================================================
    # 数据流 (WebSocket 风格)
    # ============================================================

    async def watch_ohlcv(self, symbol: str, timeframe: str) -> list:
        """模拟 K 线推送。超时返回占位 K 线，避免无限阻塞。"""
        q = self._ohlcv_queues.setdefault(f"{symbol}@{timeframe}", asyncio.Queue())
        # 注入随机 OHLCV
        import time
        ts = int(time.time() * 1000)
        base = 50000.0
        ohlcv = [ts, base, base * 1.001, base * 0.999, base, 1.0]
        await q.put(ohlcv)
        try:
            return await asyncio.wait_for(q.get(), timeout=1.0)
        except asyncio.TimeoutError:
            return [ohlcv]

    async def watch_order_book(self, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "bids": [[50000.0, 1.0]],
            "asks": [[50001.0, 1.0]],
            "timestamp": None,
        }

    async def watch_trades(self, symbol: str) -> list:
        return [{"symbol": symbol, "side": "buy", "amount": 0.01, "price": 50000.0}]

    async def watch_orders(self, symbol: str) -> list:
        """等待 create_order 推送的回报。"""
        q = self._order_queues.setdefault(symbol, asyncio.Queue())
        try:
            raw = await asyncio.wait_for(q.get(), timeout=1.0)
            return [raw]
        except asyncio.TimeoutError:
            return []

    # ============================================================
    # 生命周期
    # ============================================================

    async def close(self) -> None:
        self._closed = True
        for q in (self._ohlcv_queues | self._order_queues
                  | self._order_book_queues | self._trade_queues).values():
            # 唤醒可能阻塞在 q.get() 的协程
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass
        logger.info("模拟交易所已关闭")
