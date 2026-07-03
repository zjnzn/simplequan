"""Ichimoku 一目均衡表。"""
from __future__ import annotations

from collections import deque
from decimal import Decimal

from ._helpers import highest, lowest, _ds


class IchimokuCalculator:
    """一目均衡表计算器。

    params:
        tenkan:   转折线周期，默认 9
        kijun:    基准线周期，默认 26
        senkou_b: 先行带 B 周期，默认 52
    """

    name = "ichimoku"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return [
            "ichimoku_tenkan",
            "ichimoku_kijun",
            "ichimoku_senkou_a",
            "ichimoku_senkou_b",
            "ichimoku_chikou",
        ]

    def compute(self, bars: deque, params: dict) -> dict[str, Decimal]:
        tenkan_p = params.get("tenkan", 9)
        kijun_p = params.get("kijun", 26)
        senkou_b = params.get("senkou_b", 52)
        n = len(bars)
        max_p = max(tenkan_p, kijun_p, senkou_b)
        if n < max_p:
            return {}

        high = [float(b.high) for b in bars]
        low = [float(b.low) for b in bars]

        h_tenkan = highest(high, tenkan_p)
        l_tenkan = lowest(low, tenkan_p)
        tenkan = (h_tenkan[-1] + l_tenkan[-1]) / 2

        h_kijun = highest(high, kijun_p)
        l_kijun = lowest(low, kijun_p)
        kijun = (h_kijun[-1] + l_kijun[-1]) / 2

        h_sb = highest(high, senkou_b)
        l_sb = lowest(low, senkou_b)
        senkou_b_val = (h_sb[-1] + l_sb[-1]) / 2

        return {
            "ichimoku_tenkan": _ds(tenkan),
            "ichimoku_kijun": _ds(kijun),
            "ichimoku_senkou_a": _ds((tenkan + kijun) / 2),
            "ichimoku_senkou_b": _ds(senkou_b_val),
            "ichimoku_chikou": _ds(float(bars[-1].close)),
        }
