"""指标计算通用辅助函数（纯函数、无状态）。"""
from __future__ import annotations

from decimal import Decimal
from typing import Sequence


def _to_floats(values: Sequence[Decimal]) -> list[float]:
    """Decimal 序列 → float 列表。"""
    return [float(v) for v in values]


def sma(values: Sequence[float], period: int) -> list[float]:
    """简单移动平均。对齐 project_refactored rolling(min_periods=period) 行为。

    窗口包含 NaN 时返回 NaN，但 NaN 离开窗口后能正常恢复。
    """
    result: list[float] = []
    window: list[float] = []
    for v in values:
        window.append(v)
        if len(window) > period:
            window.pop(0)
        if len(window) == period:
            # 仅当窗口内全部值有效时才计算均值
            if all(x == x for x in window):
                result.append(sum(window) / period)
            else:
                result.append(float("nan"))
        else:
            result.append(float("nan"))
    return result


def ema(values: Sequence[float], period: int) -> list[float]:
    """指数移动平均 (alpha=2/(period+1))。对齐 pandas ewm(span=period, adjust=False)。"""
    result: list[float] = []
    alpha = 2.0 / (period + 1)
    prev = float("nan")
    for v in values:
        if prev != prev:  # NaN → 初始化为当前值
            prev = v
        elif v == v:  # v 非 NaN 时才更新，NaN 值保持 prev
            prev = alpha * v + (1 - alpha) * prev
        result.append(prev)
    return result


def rma(values: Sequence[float], period: int) -> list[float]:
    """Wilder 平滑均线 (alpha=1/period)。对齐 pandas ewm(alpha=1/period, adjust=False)。"""
    result: list[float] = []
    alpha = 1.0 / period
    prev = float("nan")
    for v in values:
        if prev != prev:  # NaN → 初始化为当前值
            prev = v
        elif v == v:  # v 非 NaN 时才更新，NaN 值保持 prev
            prev = alpha * v + (1 - alpha) * prev
        result.append(prev)
    return result


def highest(values: Sequence[float], period: int) -> list[float]:
    """滚动周期最大值。"""
    result: list[float] = []
    window: list[float] = []
    for v in values:
        window.append(v)
        if len(window) > period:
            window.pop(0)
        result.append(max(window) if len(window) == period else float("nan"))
    return result


def lowest(values: Sequence[float], period: int) -> list[float]:
    """滚动周期最小值。"""
    result: list[float] = []
    window: list[float] = []
    for v in values:
        window.append(v)
        if len(window) > period:
            window.pop(0)
        result.append(min(window) if len(window) == period else float("nan"))
    return result


def stdev(values: Sequence[float], period: int) -> list[float]:
    """滚动标准差 (ddof=0)。"""
    result: list[float] = []
    window: list[float] = []
    for v in values:
        window.append(v)
        if len(window) > period:
            window.pop(0)
        if len(window) == period:
            mean = sum(window) / period
            variance = sum((x - mean) ** 2 for x in window) / period
            result.append(variance ** 0.5)
        else:
            result.append(float("nan"))
    return result


def last_valid(sequence: list[float], default: float = 0.0) -> float:
    """取最后一个非 NaN 值。"""
    for v in reversed(sequence):
        if v == v:  # not NaN
            return v
    return default


def _d(val: float | None) -> Decimal | None:
    """float → Decimal，NaN → None。"""
    if val is None or val != val:
        return None
    return Decimal(str(val))


def _ds(val: float) -> Decimal:
    """float → Decimal，NaN → Decimal('NaN')。"""
    if val != val:
        return Decimal("NaN")
    return Decimal(str(val))
