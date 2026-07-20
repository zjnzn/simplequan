from dataclasses import dataclass


@dataclass
class Signal:
    """交易信号。value 统一表达方向+强度：[-1,+1]，正=多，负=空，0=观望。"""

    value: float     # [-1, +1]，正=做多，负=做空，0=观望
    reason: str
    signal_type: str = "entry"  # "entry" | "exit"

    @staticmethod
    def _clamp(v: float) -> float:
        """限制信号到 [-1, 1]。"""
        return max(-1.0, min(1.0, v))

    @property
    def direction(self) -> str:
        """信号方向：LONG / SHORT / HOLD。"""
        if self.value > 0:
            return "LONG"
        if self.value < 0:
            return "SHORT"
        return "HOLD"

    @property
    def strength(self) -> float:
        """信号强度绝对值 [0, 1]。"""
        return abs(self.value)

    @property
    def is_exit(self) -> bool:
        return self.signal_type == "exit"
