from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.domain.signal import Signal



@runtime_checkable
class Strategy(Protocol):
    name: str
    version: str
    required_indicators: list[str]

    async def on_bar(self, bar, ctx) -> Signal | None: ...
