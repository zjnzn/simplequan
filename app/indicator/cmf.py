"""CMF 蔡金资金流量指标。"""
from __future__ import annotations

from collections import deque
from decimal import Decimal

from ._helpers import _ds


class CmfCalculator:
    """蔡金资金流量指标计算器。

    CMF = sum(MFV, n) / sum(Volume, n)
    MFV = ((Close-Low)-(High-Close))/(High-Low) * Volume

    params:
        period: 周期，默认 20
    """

    name = "cmf"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["cmf"]

    def compute(self, bars: deque, params: dict) -> dict[str, Decimal]:
        period = params.get("period", 20)
        n = len(bars)
        if n < period:
            return {}

        high = [float(b.high) for b in bars]
        low = [float(b.low) for b in bars]
        close = [float(b.close) for b in bars]
        volume = [float(b.volume) for b in bars]

        # MFV
        mfv = [0.0] * n
        for i in range(n):
            hl = high[i] - low[i]
            if hl == 0:
                clv = 0.0
            else:
                clv = ((close[i] - low[i]) - (high[i] - close[i])) / hl
            mfv[i] = clv * volume[i]

        # Rolling CMF
        window_mfv = mfv[-period:]
        window_vol = volume[-period:]
        total_vol = sum(window_vol)
        cmf = sum(window_mfv) / total_vol if total_vol > 0 else float("nan")

        return {"cmf": _ds(cmf)}
