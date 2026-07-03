"""VPT 成交量价格趋势指标。"""
from __future__ import annotations

from collections import deque
from decimal import Decimal

from ._helpers import ema, _ds


class VptCalculator:
    """成交量价格趋势计算器。

    VPT[i] = VPT[i-1] + Volume[i] * (Close[i] - Close[i-1]) / Close[i-1]

    params:
        signal_period: VPT 信号线 EMA 周期，默认 9
    """

    name = "vpt"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["vpt", "vpt_signal"]

    def compute(self, bars: deque, params: dict) -> dict[str, Decimal]:
        signal_p = params.get("signal_period", 9)
        n = len(bars)
        if n < 2:
            return {}

        closes = [float(b.close) for b in bars]
        volumes = [float(b.volume) for b in bars]

        vpt = [0.0]
        for i in range(1, n):
            if closes[i - 1] != 0:
                vpt.append(vpt[-1] + volumes[i] * (closes[i] - closes[i - 1]) / closes[i - 1])
            else:
                vpt.append(vpt[-1])

        vpt_signal = ema(vpt, signal_p)
        return {"vpt": _ds(vpt[-1]), "vpt_signal": _ds(vpt_signal[-1])}
