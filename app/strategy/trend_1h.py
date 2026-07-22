"""趋势策略 1h — dmi方向锚定投票 + Fixed SL=1.5% + Trail=0.3.

核心设计:
  - dmi_dir 是趋势锚点 (主导方向), kdj/pm 是确认信号, dc 已移除 (加密市场永远偏向非空)
  - 趋势状态 (strong/moderate): dmi锚定方向, kdj+pm 2票同向确认, min_confirms=2
  - 震荡状态 (range): dmi反转 (趋势弱→反向交易), 标准4指标投票, min_votes=3

V2 变更 (48天新数据研究):
  - dc_breakout 与 dmi 同向率 0% (crypto bull bias), 从趋势投票中彻底移除
  - 方案A: dmi+kdj+pm 2确认票, 阈值收紧 → SR +1.94→+2.48, CV 0.52→0.40
  - 风控收紧: SL 2%→1.5%, Trail 0.5→0.3, MH 5→3, CD 2→1
"""
import numpy as np


def _vote_anchored(df, idx, thresholds, min_votes):
    """dmi方向锚定投票: dmi决定方向, kdj+pm 2票确认 (dc已移除).

    dmi本身不算票, 需要 min_votes 个确认票与anchor同向.
    """
    dmi_th, kdj_th, pm_th, _dc_th = thresholds[0]
    d = df['dmi_dir'].values[idx]
    k = df['kdj_momentum'].values[idx]
    p = df['pm_momentum'].values[idx]
    n = len(idx)

    anchor = np.sign(np.where(np.abs(d) >= dmi_th, d, 0))

    votes = np.zeros((n, 2), dtype=int)
    votes[:, 0] = np.where(k > kdj_th, 1, np.where(k < -kdj_th, -1, 0))
    votes[:, 1] = np.where(p > pm_th, 1, np.where(p < -pm_th, -1, 0))

    aligned = (votes * anchor[:, None] > 0).sum(axis=1)
    signal = np.zeros(n)
    has_anchor = anchor != 0
    signal[has_anchor & (aligned >= min_votes)] = anchor[has_anchor & (aligned >= min_votes)]
    return signal


def _vote_range(df, idx, thresholds, min_votes):
    """震荡投票: dmi反转 + 标准4指标投票.

    range状态专用. dmi趋势弱 → 反向交易 (fade the weak trend).
    """
    dmi_th, kdj_th, pm_th, dc_th = thresholds[0]
    d = df['dmi_dir'].values[idx]
    k = df['kdj_momentum'].values[idx]
    p = df['pm_momentum'].values[idx]
    b = df['dc_breakout'].values[idx]
    n = len(idx)

    votes = np.zeros((n, 4), dtype=int)
    votes[:, 0] = np.where(d < -dmi_th, 1, np.where(d > dmi_th, -1, 0))
    votes[:, 1] = np.where(k > kdj_th, 1, np.where(k < -kdj_th, -1, 0))
    votes[:, 2] = np.where(p > pm_th, 1, np.where(p < -pm_th, -1, 0))
    votes[:, 3] = np.where(b > dc_th, 1, np.where(b < -dc_th, -1, 0))

    total = votes.sum(axis=1)
    signal = np.zeros(n)
    signal[total >= min_votes] = 1
    signal[total <= -min_votes] = -1
    return signal


class Trend1hStrategy:
    """趋势策略 — 1h K线, dmi锚定投票 + 按 market_state 分派阈值."""

    name = "trend_1h"
    version = "2.0.0"
    tf = "1h"

    FIXED_SL = 0.015
    TRAIL_MULT = 0.3
    ADX_FLOOR = 0.10
    MIN_HOLD = 3
    COOLDOWN = 1
    ADX_WARNING = 0.0

    def __init__(self, ac_floor: float = 0.0, **kwargs):
        self._trend_config = {
            'strong_trend':   ((0.03, 0.06, 0.07, 0.08), 2),
            'moderate_trend': ((0.03, 0.06, 0.07, 0.08), 2),
        }
        self._range_config = ((0.04, 0.05, 0.04, 0.08), 3)
        self.ac_floor = ac_floor
        for k, v in kwargs.items():
            setattr(self, k, v)

    def required_indicators(self, params: dict) -> list[str]:
        return [
            'market_state', 'adx', 'dmi_dir', 'kdj_momentum', 'pm_momentum',
            'dc_breakout', 'ac_smooth', 'atr_vol',
        ]

    def route(self, df, params: dict | None = None) -> np.ndarray:
        params = params or {}
        adx_floor = params.get("ADX_FLOOR", self.ADX_FLOOR)
        cooldown = params.get("COOLDOWN", self.COOLDOWN)
        ac_floor = params.get("ac_floor", self.ac_floor)
        adx_warning = params.get("ADX_WARNING", self.ADX_WARNING)

        state = df['market_state'].values
        signal = np.zeros(len(df), dtype=float)

        for st_key, (th, mc) in self._trend_config.items():
            mask = state == st_key
            if mask.sum() == 0:
                continue
            idx = np.where(mask)[0]
            signal[idx] = _vote_anchored(df, idx, [th], mc)

        mask_r = state == 'range'
        if mask_r.sum():
            idx_r = np.where(mask_r)[0]
            th_r, mv_r = self._range_config
            signal[idx_r] = _vote_range(df, idx_r, [th_r], mv_r)

        if ac_floor > 0 and 'ac_smooth' in df.columns:
            ac = df['ac_smooth'].values
            signal[np.abs(ac) < ac_floor] = 0

        if 'adx' in df.columns:
            signal[df['adx'].values < adx_floor] = 0

        if cooldown > 0:
            last = -999
            for i in range(len(signal)):
                if signal[i] != 0:
                    if i - last < cooldown:
                        signal[i] = 0
                    else:
                        last = i

        if adx_warning > 0 and 'adx' in df.columns:
            adx_vals = df['adx'].values
            prev_adx = np.roll(adx_vals, 1)
            prev_adx[0] = adx_vals[0]
            adx_drop = prev_adx - adx_vals
            signal[adx_drop > adx_warning] = 0

        return signal

    async def check_exit(self, row: dict, pos: dict, ctx, params: dict) -> str | None:
        params = params or {}
        fixed_sl = params.get("FIXED_SL", self.FIXED_SL)
        trail_mult = params.get("TRAIL_MULT", self.TRAIL_MULT)
        min_hold = params.get("MIN_HOLD", self.MIN_HOLD)

        c = float(row.get("close", 0))
        h = float(row.get("high", 0))
        l = float(row.get("low", 0))
        v = max(float(row.get("atr_vol", 0.005)), 0.005)
        ep = float(pos.get("entry_price", 0))
        bars_held = pos.get("bars_held", 0)
        s = int(pos.get("side", 0))
        bp = float(pos.get("best_price", ep))

        trail = (bp - c) / ep if s > 0 else (c - bp) / ep
        pnl = (c - ep) / ep if s > 0 else (ep - c) / ep

        if pnl <= -fixed_sl:
            return "fixed_sl"

        if bars_held >= min_hold:
            if trail > v * trail_mult:
                return "stop"

        return None
