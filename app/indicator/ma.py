from __future__ import annotations

import pandas as pd


class MaCalculator:
    """移动平均线指标计算器（无状态模板）。

    params:
        periods: MA 周期列表，默认 [5, 20]
    """

    name = "ma"
    version = "2.0.0"

    def output_keys(self, params: dict) -> list[str]:
        periods = params.get("periods", [5, 20])
        return [f"ma_{p}" for p in periods]

    def compute(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        periods = params.get("periods", [5, 20])
        result = {}
        closes = df["close"]
        for p in periods:
            if len(closes) >= p:
                result[f"ma_{p}"] = float(closes.rolling(p).mean().iloc[-1])
        return result
