"""VWAP 成交量加权平均价格。"""
from __future__ import annotations

from collections import deque
from decimal import Decimal

from ._helpers import _ds


class VwapCalculator:
    """成交量加权平均价格计算器。

    params:
        period: 滚动窗口周期，默认 20
    """

    name = "vwap"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["vwap"]

    def compute(self, bars: deque, params: dict) -> dict[str, Decimal]:
        period = params.get("period", 20)
        n = len(bars)
        if n < period:
            return {}

        tp = [float((b.high + b.low + b.close)) / 3 for b in bars]
        vol = [float(b.volume) for b in bars]

        window_tp = tp[-period:]
        window_vol = vol[-period:]
        total_vol = sum(window_vol)
        vwap = sum(w * v for w, v in zip(window_tp, window_vol)) / total_vol if total_vol > 0 else float("nan")
        return {"vwap": _ds(vwap)}
