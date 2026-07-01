from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.domain.risk import RiskResult


@runtime_checkable
class RiskMiddleware(Protocol):
    name: str

    async def check(self, payload, ctx) -> RiskResult: ...
