"""CcxtExchange —— ExchangePort 的 CCXT 实现。

封装 CCXT 库，提供交易所原始能力。
"""
from __future__ import annotations

from typing import Any


class CcxtExchange:
    """CCXT 交易所实现。"""

    def __init__(self, exchange: Any) -> None:
        self._exchange = exchange

    # ============================================================
    # 账户
    # ============================================================

    async def fetch_balance(self) -> dict:
        """获取账户余额。"""
        return await self._exchange.fetch_balance()

    async def fetch_positions(self, symbols: list[str]) -> list[dict]:
        """获取持仓信息。"""
        return await self._exchange.fetch_positions(symbols)

    async def fetch_leverage(self, symbol: str) -> dict:
        """获取杠杆配置。"""
        return await self._exchange.fetch_leverage(symbol)

    # ============================================================
    # 市场
    # ============================================================

    async def load_markets(self) -> dict:
        """加载市场信息。"""
        return await self._exchange.load_markets()

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
        """创建订单。"""
        return await self._exchange.create_order(
            symbol, order_type, side, amount, price
        )

    async def cancel_order(self, order_id: str, symbol: str) -> dict:
        """取消订单。"""
        return await self._exchange.cancel_order(order_id, symbol)

    # ============================================================
    # 数据流 (WebSocket)
    # ============================================================

    async def watch_ohlcv(self, symbol: str, timeframe: str) -> list:
        """订阅 K 线数据。"""
        return await self._exchange.watch_ohlcv(symbol, timeframe)

    async def watch_order_book(self, symbol: str) -> dict:
        """订阅订单簿。"""
        return await self._exchange.watch_order_book(symbol)

    async def watch_trades(self, symbol: str) -> list:
        """订阅成交数据。"""
        return await self._exchange.watch_trades(symbol)

    async def watch_orders(self, symbol: str) -> list:
        """订阅订单状态更新。"""
        return await self._exchange.watch_orders(symbol)

    # ============================================================
    # 生命周期
    # ============================================================

    async def close(self) -> None:
        """关闭连接。"""
        await self._exchange.close()
