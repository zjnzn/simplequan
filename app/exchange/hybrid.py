"""HybridExchange —— 真实行情 + 虚拟撮合的组合实现。

实现 ExchangePort：
  - 行情类方法（watch_*/load_markets）→ MarketSource（真实 ccxt.pro）
  - 订单/账户类方法 → MatchingEngine（虚拟内存）
  - watch_ohlcv/watch_order_book/watch_trades 拿到真实数据后，触发限价单撮合检查
"""
from __future__ import annotations

import asyncio
import logging

from app.exchange.market_source import MarketSource
from app.exchange.matching_engine import MatchingEngine
from core.domain.config import AppConfig, ExchangeConfig

logger = logging.getLogger(__name__)


class HybridExchange:
    """混合交易所：真实行情 + 虚拟撮合。"""

    def __init__(
        self,
        cfg: ExchangeConfig,
        app_config: AppConfig,
        initial_balance: float = 10000.0,
    ) -> None:
        self._market = MarketSource(cfg, app_config, exchange_name=cfg.name)
        self._engine = MatchingEngine(self._market, initial_balance=initial_balance)

    # ============================================================
    # 行情（真实） —— 取数后触发限价单检查
    # ============================================================

    async def watch_ohlcv(self, symbol: str, timeframe: str) -> list:
        ohlcv = await self._market.watch_ohlcv(symbol, timeframe)
        await self._engine.check_limits(symbol)
        return ohlcv

    async def watch_order_book(self, symbol: str) -> dict:
        ob = await self._market.watch_order_book(symbol)
        await self._engine.check_limits(symbol)
        return ob

    async def watch_trades(self, symbol: str) -> list:
        trades = await self._market.watch_trades(symbol)
        await self._engine.check_limits(symbol)
        return trades

    async def load_markets(self) -> dict:
        return await self._market.load_markets()

    # ============================================================
    # 订单（虚拟）
    # ============================================================

    async def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: float | None = None,
    ) -> dict:
        return await self._engine.create_order(symbol, order_type, side, amount, price)

    async def cancel_order(self, order_id: str, symbol: str) -> dict:
        return await self._engine.cancel_order(order_id, symbol)

    async def watch_orders(self, symbol: str) -> list:
        return await self._engine.watch_orders(symbol)

    # ============================================================
    # 账户（虚拟）
    # ============================================================

    async def fetch_balance(self) -> dict:
        return await self._engine.fetch_balance()

    async def fetch_positions(self, symbols: list[str]) -> list[dict]:
        return await self._engine.fetch_positions(symbols)

    async def fetch_leverage(self, symbol: str) -> dict:
        return await self._engine.fetch_leverage(symbol)

    # ============================================================
    # 生命周期
    # ============================================================

    async def close(self) -> None:
        await self._engine.close()
        await self._market.close()
