from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core.domain.signal import Signal


@runtime_checkable
class Strategy(Protocol):
    """策略插件接口（无状态模板）。参数在调用时注入，不进构造函数。"""
    name: str
    version: str

    def required_indicators(self, params: dict) -> list[str]:
        """根据 params 返回该策略依赖的指标 key 列表。"""
        ...

    async def on_bar(self, row: dict[str, Any], ctx, params: dict) -> Signal | None:
        """接收一行 bar dict（含 OHLCV + 指标列），返回 Signal 或 None。"""
        ...
