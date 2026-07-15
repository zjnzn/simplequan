"""指标计算通用辅助函数（已废弃）。

这些函数已被 pandas 向量化操作替代：
  sma  → df["close"].rolling(period).mean()
  ema  → df["close"].ewm(span=period, adjust=False).mean()
  rma  → df["close"].ewm(alpha=1/period, adjust=False).mean()
  highest → df["close"].rolling(period).max()
  lowest  → df["close"].rolling(period).min()
  stdev   → df["close"].rolling(period).std()

保留仅供向后兼容，新代码请直接使用 pd 向量化操作。
"""
from __future__ import annotations

import warnings
from decimal import Decimal
from typing import Sequence

import pandas as pd


def _to_floats(values: Sequence[Decimal]) -> list[float]:
    return [float(v) for v in values]


def sma(values: Sequence[float], period: int) -> list[float]:
    warnings.warn("sma is deprecated, use pd.Series.rolling().mean()", DeprecationWarning, stacklevel=2)
    s = pd.Series(values)
    return s.rolling(period, min_periods=period).mean().tolist()


def ema(values: Sequence[float], period: int) -> list[float]:
    warnings.warn("ema is deprecated, use pd.Series.ewm().mean()", DeprecationWarning, stacklevel=2)
    s = pd.Series(values)
    return s.ewm(span=period, adjust=False).mean().tolist()


def rma(values: Sequence[float], period: int) -> list[float]:
    warnings.warn("rma is deprecated, use pd.Series.ewm().mean()", DeprecationWarning, stacklevel=2)
    s = pd.Series(values)
    return s.ewm(alpha=1.0 / period, adjust=False).mean().tolist()


def highest(values: Sequence[float], period: int) -> list[float]:
    warnings.warn("highest is deprecated, use pd.Series.rolling().max()", DeprecationWarning, stacklevel=2)
    s = pd.Series(values)
    return s.rolling(period, min_periods=period).max().tolist()


def lowest(values: Sequence[float], period: int) -> list[float]:
    warnings.warn("lowest is deprecated, use pd.Series.rolling().min()", DeprecationWarning, stacklevel=2)
    s = pd.Series(values)
    return s.rolling(period, min_periods=period).min().tolist()


def stdev(values: Sequence[float], period: int) -> list[float]:
    warnings.warn("stdev is deprecated, use pd.Series.rolling().std()", DeprecationWarning, stacklevel=2)
    s = pd.Series(values)
    return s.rolling(period, min_periods=period).std().tolist()


def last_valid(sequence: list[float], default: float = 0.0) -> float:
    for v in reversed(sequence):
        if v == v:
            return v
    return default


def _d(val: float | None) -> Decimal | None:
    if val is None or val != val:
        return None
    return Decimal(str(val))


def _ds(val: float) -> Decimal:
    if val != val:
        return Decimal("NaN")
    return Decimal(str(val))
