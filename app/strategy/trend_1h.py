"""趋势策略 1h — ADX≥0.5入场过滤 + 4指标投票 + Fixed SL=2% + Trail=0.8 + DMI反转."""
from __future__ import annotations

import numpy as np


def _vote(df, idx: np.ndarray, thresholds: tuple, min_votes: int, invert_dmi: bool) -> np.ndarray:
    dmi_th, kdj_th, pm_th, dc_th = thresholds
    d = df["dmi_dir"].values[idx]
    k = df["kdj_momentum"].values[idx]
    p = df["pm_momentum"].values[idx]
    b = df["dc_breakout"].values[idx]

    n = len(idx)
    votes = np.zeros((n, 4), dtype=int)

    if invert_dmi:
        votes[:, 0] = np.where(d < -dmi_th, 1, np.where(d > dmi_th, -1, 0))
    else:
        votes[:, 0] = np.where(d > dmi_th, 1, np.where(d < -dmi_th, -1, 0))

    votes[:, 1] = np.where(k > kdj_th, 1, np.where(k < -kdj_th, -1, 0))
    votes[:, 2] = np.where(p > pm_th, 1, np.where(p < -pm_th, -1, 0))
    votes[:, 3] = np.where(b > dc_th, 1, np.where(b < -dc_th, -1, 0))

    total = votes.sum(axis=1)
    signal = np.zeros(n)
    signal[total >= min_votes] = 1
    signal[total <= -min_votes] = -1
    return signal


class Trend1hStrategy:
    """趋势策略 — 1h K线, 按 market_state 分派子策略."""

    name = "trend_1h"
    version = "1.0.0"

    tf = "1h"
    FIXED_SL = 0.02
    TRAIL_MULT = 0.8
    ADX_FLOOR = 0.5
    MIN_HOLD = 3

    def __init__(self, ac_floor: float = 0.03):
        self._sub_strategies = {
            "strong_trend":   ((0.02, 0.03, 0.02, 0.05), 3, False),
            "moderate_trend": ((0.03, 0.05, 0.03, 0.08), 3, False),
            "range":          ((0.04, 0.05, 0.04, 0.08), 3, True),
        }
        self.ac_floor = ac_floor

    def required_indicators(self, params: dict) -> list[str]:
        return [
            "market_state", "adx", "dmi_dir", "kdj_momentum",
            "pm_momentum", "dc_breakout", "ac_smooth", "atr_vol",
        ]

    def route(self, df, params: dict | None = None, gate_data: dict | None = None) -> "np.ndarray":
        """全量向量化信号 — 按 market_state 分派子策略投票 + ADX/autocorr 过滤."""
        state = df["market_state"].values
        signal = np.zeros(len(df), dtype=float)

        for st_key, (th, mv, invert) in self._sub_strategies.items():
            mask = state == st_key
            if mask.sum() == 0:
                continue
            idx = np.where(mask)[0]
            signal[idx] = _vote(df, idx, th, mv, invert)

        if self.ac_floor > 0 and "ac_smooth" in df.columns:
            ac = df["ac_smooth"].values
            signal[np.abs(ac) < self.ac_floor] = 0

        if "adx" in df.columns:
            signal[df["adx"].values < self.ADX_FLOOR] = 0

        return signal

    async def check_exit(self, row: dict, pos: dict, ctx, params: dict) -> str | None:
        c = float(row.get("close", 0))
        v = max(float(row.get("atr_vol", 0.005)), 0.005)
        d = float(row.get("dmi_dir", 0))
        ep = float(pos.get("entry_price", 0))
        bars_held = pos.get("bars_held", 0)
        s = int(pos.get("side", 0))
        bp = float(pos.get("best_price", ep))

        trail = (bp - c) / ep if s > 0 else (c - bp) / ep
        pnl = (c - ep) / ep if s > 0 else (ep - c) / ep

        if pnl <= -self.FIXED_SL:
            return "fixed_sl"

        if bars_held >= self.MIN_HOLD:
            if trail > v * self.TRAIL_MULT:
                return "stop"
            elif (s > 0 and d < -0.03) or (s < 0 and d > 0.03):
                return "reverse"

        return None
