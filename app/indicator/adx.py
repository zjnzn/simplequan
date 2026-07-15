"""ADX 平均趋向指数（pd 向量化）。"""
from __future__ import annotations

import pandas as pd


class AdxCalculator:
    """ADX 平均趋向指数计算器。

    params:
        period: 周期，默认 14
    """

    name = "adx"
    version = "2.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["adx", "plus_di", "minus_di"]

    def compute(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        period = params.get("period", 14)
        n = len(df)
        if n < period + 1:
            return {}

        high, low, close = df["high"], df["low"], df["close"]

        # True Range
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)

        # Directional Movement
        up = high.diff()
        down = -low.diff()
        plus_dm = up.where((up > down) & (up > 0), 0.0)
        minus_dm = down.where((down > up) & (down > 0), 0.0)

        # Wilder smoothed (ewm alpha=1/period)
        alpha = 1.0 / period
        atr_rma = tr.ewm(alpha=alpha, adjust=False).mean()
        plus_di = 100.0 * plus_dm.ewm(alpha=alpha, adjust=False).mean() / atr_rma.replace(0, float("nan"))
        minus_di = 100.0 * minus_dm.ewm(alpha=alpha, adjust=False).mean() / atr_rma.replace(0, float("nan"))

        # DX
        denom = plus_di + minus_di
        dx = 100.0 * (plus_di - minus_di).abs() / denom.replace(0, float("nan"))

        # ADX = Wilder smoothed DX
        adx = dx.ewm(alpha=alpha, adjust=False).mean()

        return {
            "adx": float(adx.iloc[-1]) if pd.notna(adx.iloc[-1]) else float("nan"),
            "plus_di": float(plus_di.iloc[-1]) if pd.notna(plus_di.iloc[-1]) else float("nan"),
            "minus_di": float(minus_di.iloc[-1]) if pd.notna(minus_di.iloc[-1]) else float("nan"),
        }
