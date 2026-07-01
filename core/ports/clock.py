"""Clock —— 时钟端口，抽象时间来源与节奏控制。

实现类可以是：
  - RealtimeClock: 真实时钟，sleep 按真实节奏等待（模拟实时行情）
  - BacktestClock: 回测时钟，sleep 立即返回（瞬时回放），时间戳来自历史数据

Exchange/Handler 不直接调用 asyncio.sleep 或 time.time，而是依赖 Clock，
从而在实时与回测间切换而无需改动业务代码。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """时钟端口 —— 抽象时间来源与节奏控制。"""

    def now_ms(self) -> int:
        """当前时间戳（毫秒）。实时时钟返回墙钟时间，回测时钟返回回放时间。"""
        ...

    async def sleep(self, seconds: float) -> None:
        """等待指定秒数。实时时钟真实等待，回测时钟立即返回（加速回放）。"""
        ...
