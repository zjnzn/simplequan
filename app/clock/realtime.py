"""RealtimeClock —— 真实时钟，按真实节奏等待。

用于模拟实时行情：K 线按 _TICK 秒间隔推送，时间戳为墙钟时间。
"""
from __future__ import annotations

import asyncio
import time

from core.ports.clock import Clock


class RealtimeClock(Clock):
    """真实时钟。sleep 真实等待，now_ms 返回墙钟毫秒时间戳。"""

    def now_ms(self) -> int:
        return int(time.time() * 1000)

    async def sleep(self, seconds: float) -> None:
        if seconds > 0:
            await asyncio.sleep(seconds)
