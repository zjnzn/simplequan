"""OBV 能量潮指标。"""
from __future__ import annotations

from collections import deque
from decimal import Decimal

from ._helpers import ema, _ds


class ObvCalculator:
    """能量潮计算器。

    params:
        signal_period: OBV 信号线 EMA 周期，默认 20
    """

    name = "obv"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["obv", "obv_signal"]

    def compute(self, bars: deque, params: dict) -> dict[str, Decimal]:
        signal_p = params.get("signal_period", 20)
        n = len(bars)
        if n < 2:
            return {}

        closes = [float(b.close) for b in bars]
        volumes = [float(b.volume) for b in bars]

        obv = [volumes[0]]
        for i in range(1, n):
            if closes[i] > closes[i - 1]:
                obv.append(obv[-1] + volumes[i])
            elif closes[i] < closes[i - 1]:
                obv.append(obv[-1] - volumes[i])
            else:
                obv.append(obv[-1])

        obv_signal = ema(obv, signal_p)
        return {"obv": _ds(obv[-1]), "obv_signal": _ds(obv_signal[-1])}
