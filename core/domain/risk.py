from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskResult:
    passed: bool
    reason: str = ""

    @staticmethod
    def approve() -> RiskResult:
        return RiskResult(True)

    @staticmethod
    def reject(reason: str) -> RiskResult:
        return RiskResult(False, reason)
