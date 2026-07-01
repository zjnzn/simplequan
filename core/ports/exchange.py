"""ExchangePort —— 交易所端口，定义交易所原始能力。

实现类可以是：
  - CcxtExchange: 封装 CCXT 库，对接真实交易所
  - SimulatedExchange: 模拟交易所，用于测试
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ExchangePort(Protocol):
    """交易所端口 —— 定义交易所原始能力。"""

    # ============================================================
    # 账户
    # ============================================================

    async def fetch_balance(self) -> dict:
        """获取账户余额。"""
        ...

    async def fetch_positions(self, symbols: list[str]) -> list[dict]:
        """获取持仓信息。"""
        ...

    async def fetch_leverage(self, symbol: str) -> dict:
        """获取杠杆配置。"""
        ...

    # ============================================================
    # 市场
    # ============================================================

    async def load_markets(self) -> dict:
        """加载市场信息。"""
        ...

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
        ...

    async def cancel_order(self, order_id: str, symbol: str) -> dict:
        """取消订单。"""
        ...

    # ============================================================
    # 数据流 (WebSocket)
    # ============================================================

    async def watch_ohlcv(self, symbol: str, timeframe: str) -> list:
        """订阅 K 线数据。"""
        ...

    async def watch_order_book(self, symbol: str) -> dict:
        """订阅订单簿。"""
        ...

    async def watch_trades(self, symbol: str) -> list:
        """订阅成交数据。"""
        ...

    async def watch_orders(self, symbol: str) -> list:
        """订阅订单状态更新。"""
        ...

    # ============================================================
    # 生命周期
    # ============================================================

    async def close(self) -> None:
        """关闭连接。"""
        ...
