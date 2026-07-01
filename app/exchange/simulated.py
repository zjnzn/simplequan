"""SimulatedExchange —— ExchangePort 的内存模拟实现。

不连网，纯内存驱动。用于离线开发 handler 闭环和测试。

通过注入 Clock 控制推送节奏：
  - RealtimeClock: 按真实间隔推送（模拟实时行情）
  - BacktestClock: 瞬时回放（加速回测）
"""
from __future__ import annotations

import asyncio
import logging
import random
import uuid
from typing import Any

from app.clock.realtime import RealtimeClock
from core.domain.config import AppConfig, ExchangeConfig
from core.ports.clock import Clock

logger = logging.getLogger(__name__)


class SimulatedExchange:
    """模拟交易所。实现 ExchangePort 全部方法，纯内存。"""

    # K 线推送间隔（秒），配合 RealtimeClock 模拟真实行情节奏
    _TICK: float = 0.1

    def __init__(
        self,
        cfg: ExchangeConfig | None = None,
        app_config: AppConfig | None = None,
        clock: Clock | None = None,
        fail_rate: float = 0.0,
        partial_rate: float = 0.0,
    ) -> None:
        self._cfg = cfg or ExchangeConfig()
        self._app_config = app_config
        # 默认真实时钟；回测时注入 BacktestClock 实现加速回放
        self._clock: Clock = clock or RealtimeClock()
        # 失败场景概率：fail_rate 拒单，partial_rate 部分成交（用于验证回滚）
        self._fail_rate = fail_rate
        self._partial_rate = partial_rate

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

        # 每 symbol 的价格序列种子，用于产生趋势性 K 线（close 递增）
        self._price_seed: dict[str, float] = {}

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
        fill_price = price if price else self._price_seed.get(symbol, 50000.0)

        # 失败场景模拟：fail_rate 拒单，partial_rate 部分成交
        r = random.random()
        if self._fail_rate > 0 and r < self._fail_rate:
            status, filled, avg = "rejected", 0.0, None
        elif self._partial_rate > 0 and r < self._fail_rate + self._partial_rate:
            status, filled, avg = "closed", amount * 0.5, fill_price
        else:
            status, filled, avg = "closed", amount, fill_price

        raw = {
            "id": order_id,
            "clientOrderId": order_id,
            "symbol": symbol,
            "side": side.lower(),
            "type": order_type.lower(),
            "amount": amount,
            "price": price,
            "filled": filled,
            "average": avg,
            "status": status,
            "cost": filled * fill_price if avg else 0.0,
        }
        self._orders[order_id] = raw

        # 推送到 watch_orders 回报队列
        q = self._order_queues.setdefault(symbol, asyncio.Queue())
        await q.put(raw)

        logger.info("模拟下单: %s %s %s 数量=%s 成交=%s 状态=%s 成交价=%s",
                    symbol, side, order_type, amount, filled, status, fill_price)
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
        """模拟 K 线推送。close 随时间递增产生趋势，使策略能产生非 HOLD 信号。

        推送节奏由注入的 Clock 决定：RealtimeClock 按 _TICK 秒间隔，BacktestClock 瞬时回放。
        时间戳取自 Clock，回测时可反映历史时间。超时返回空列表（不返回假数据）。
        """
        q = self._ohlcv_queues.setdefault(f"{symbol}@{timeframe}", asyncio.Queue())
        ts = self._clock.now_ms()
        # 趋势上行：每根 K 线 close 比上一根 +0.5%，起始 50000
        prev = self._price_seed.get(symbol, 50000.0)
        close = round(prev * 1.005, 2)
        self._price_seed[symbol] = close
        ohlcv = [ts, prev, close * 1.002, prev * 0.999, close, 1.0]
        # 节流：由 Clock 决定是否真实等待（实时）或立即返回（回测）
        await self._clock.sleep(self._TICK)
        await q.put(ohlcv)
        try:
            return await asyncio.wait_for(q.get(), timeout=1.0)
        except asyncio.TimeoutError:
            return []

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
