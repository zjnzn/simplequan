"""震荡策略 15m — 3指标投票 + PartTP=0.3% + Fixed SL=2% + %B归中 + 超时强平."""
from __future__ import annotations

import numpy as np


def _vote_range(df, idx: np.ndarray, thresholds: dict) -> np.ndarray:
    k = df["kdj_reversal"].values[idx]
    b = df["bb_pct_b"].values[idx]
    d = df["dc_breakout"].values[idx]

    n = len(idx)
    votes = np.zeros((n, 3), dtype=int)

    th = thresholds["kdj_rev"]
    votes[:, 0] = np.where(k > th,
        np.where(b < 0.3, 1, np.where(b > 0.7, -1, 0)),
        0)

    votes[:, 1] = np.where(b < thresholds["bb_low"], 1,
                  np.where(b > thresholds["bb_high"], -1, 0))

    dc = thresholds["dc_edge"]
    votes[:, 2] = np.where(d < -dc, 1, np.where(d > dc, -1, 0))

    total = votes.sum(axis=1)
    signal = np.zeros(n)
    mv = thresholds.get("min_votes", 2)
    signal[total >= mv] = 1
    signal[total <= -mv] = -1
    return signal


class Range15mStrategy:
    """震荡策略 — 15m K线, 3指标投票 + DMI方向过滤."""

    name = "range_15m"
    version = "1.0.0"

    tf = "15m"
    FIXED_SL = 0.02
    PARTIAL_TP = 0.003
    MAX_HOLD = 24
    MIN_HOLD = 1
    TP_BB_LOW = 0.3
    TP_BB_HIGH = 0.6

    def __init__(self, dmi_threshold: float = 0.10, min_votes: int = 2):
        self.dmi_threshold = dmi_threshold
        self._thresholds = {
            "kdj_rev": 0.5,
            "bb_low": 0.15, "bb_high": 0.95,
            "dc_edge": 0.8,
            "min_votes": min_votes,
        }

    def required_indicators(self, params: dict) -> list[str]:
        return [
            "dmi_dir", "kdj_reversal", "bb_pct_b", "dc_breakout", "atr_vol",
        ]

    def route(self, df, params: dict | None = None) -> "np.ndarray":
        """全量向量化信号 — DMI方向过滤 + 3指标投票."""
        n = len(df)
        signal = np.zeros(n, dtype=float)

        dmi_ok = np.abs(df["dmi_dir"].values) < self.dmi_threshold
        valid = dmi_ok & (
            df["kdj_reversal"].notna().values &
            df["bb_pct_b"].notna().values &
            df["dc_breakout"].notna().values
        )
        idx = np.where(valid)[0]
        if len(idx) == 0:
            return signal

        signal[idx] = _vote_range(df, idx, self._thresholds)
        return signal

    async def check_exit(self, row: dict, pos: dict, ctx, params: dict) -> str | None:
        c = float(row.get("close", 0))
        b_val = float(row.get("bb_pct_b", 0.5))
        ep = float(pos.get("entry_price", 0))
        bars_held = pos.get("bars_held", 0)
        s = int(pos.get("side", 0))
        partial_done = pos.get("partial_done", False)

        pnl = (c - ep) / ep if s > 0 else (ep - c) / ep

        if pnl <= -self.FIXED_SL:
            return "fixed_sl"

        if pnl >= self.PARTIAL_TP and not partial_done:
            return "partial_tp"

        if bars_held >= self.MIN_HOLD:
            if self.TP_BB_LOW <= b_val <= self.TP_BB_HIGH:
                return "tp_bb"

        if bars_held >= self.MAX_HOLD:
            return "timeout"

        return None
