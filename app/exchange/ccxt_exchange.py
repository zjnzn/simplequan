"""CcxtExchange —— ExchangePort 的 CCXT 实现。

从 ExchangeConfig 构建 ccxt.pro 实例，支持 sandbox/testnet 和代理。
"""
from __future__ import annotations

import importlib
import logging
from typing import Any

from core.domain.config import ExchangeConfig

log = logging.getLogger(__name__)


class CcxtExchange:
    """CCXT 交易所实现，从 ExchangeConfig 自动构建。"""

    def __init__(self, cfg: ExchangeConfig) -> None:
        ccxt_pro = importlib.import_module("ccxt.pro")
        exchange_cls = getattr(ccxt_pro, cfg.name)

        self._default_type = "spot"
        options: dict[str, Any] = {"defaultType": self._default_type}
        kwargs: dict[str, Any] = {
            "apiKey": cfg.api_key,
            "secret": cfg.api_secret,
            "options": options,
        }
        if cfg.proxy:
            kwargs["aiohttp_proxy"] = cfg.proxy

        self._exchange = exchange_cls(kwargs)
        if cfg.sandbox:
            self._exchange.set_sandbox_mode(True)

    # ============================================================
    # 账户
    # ============================================================

    async def fetch_balance(self) -> dict:
        return await self._exchange.fetch_balance()

    async def fetch_positions(self, symbols: list[str]) -> list[dict]:
        if self._default_type == "spot":
            return []
        return await self._exchange.fetch_positions(symbols)

    async def fetch_leverage(self, symbol: str) -> dict:
        if self._default_type == "spot":
            return {"leverage": 1, "marginMode": "cross"}
        return await self._exchange.fetch_leverage(symbol)

    # ============================================================
    # 市场
    # ============================================================

    async def load_markets(self) -> dict:
        return await self._exchange.load_markets()

    # ============================================================
    # 市场数据 (REST)
    # ============================================================

    async def fetch_ohlcv(self, symbol: str, timeframe: str, since: int | None = None, limit: int = 500) -> list:
        return await self._exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)

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
        return await self._exchange.create_order(
            symbol, order_type, side, amount, price
        )

    async def cancel_order(self, order_id: str, symbol: str) -> dict:
        return await self._exchange.cancel_order(order_id, symbol)

    # ============================================================
    # 数据流 (WebSocket)
    # ============================================================

    async def watch_ohlcv(self, symbol: str, timeframe: str) -> list:
        return await self._exchange.watch_ohlcv(symbol, timeframe)

    async def watch_order_book(self, symbol: str) -> dict:
        return await self._exchange.watch_order_book(symbol)

    async def watch_trades(self, symbol: str) -> list:
        return await self._exchange.watch_trades(symbol)

    async def watch_orders(self, symbol: str) -> list:
        return await self._exchange.watch_orders(symbol)

    # ============================================================
    # 生命周期
    # ============================================================

    async def close(self) -> None:
        await self._exchange.close()
