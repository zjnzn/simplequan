"""5m 市场状态策略 — 1h市场上下文驱动 5m 信号过滤.

市场上下文 (来自1h market_state, 由 SignalHandler _resolve_gate 注入):
  - 1h strong_trend:   仅同向信号 (趋势方向不该被5m震荡信号逆着做)
  - 1h moderate_trend: 全量信号 (中等趋势+低波动, 5m震荡最有效的环境)
  - 1h range:          全量信号 (区间振荡是5m天然猎场)
  - 1h weak_trend:     空仓 (无方向无波动)

df 需包含 market_state_1h 列 (SignalHandler gate 负责注入).
"""
import numpy as np


class Market5mStrategy:
    """5m 市场上下文策略 — span+pm+dc_breakout 投票 + 1h gate."""

    name = "market_5m"
    version = "1.0.0"
    tf = "5m"

    FIXED_SL = 0.02
    PARTIAL_TP = 0.003
    MAX_HOLD = 72
    MIN_HOLD = 2
    TP_BB_LOW = 0.3
    TP_BB_HIGH = 0.6

    TH1 = 0.31   # span reversal
    TH2 = 0.12   # pm standard
    TH3 = 0.30   # dc standard
    MIN_V = 2
    DMI_TH = 0.08

    def __init__(self):
        self._pd = False

    def required_indicators(self, params: dict) -> list[str]:
        return ['dmi_dir', 'span', 'pm_momentum', 'dc_breakout', 'bb_pct_b', 'atr_vol']

    def route(self, df, params: dict | None = None) -> np.ndarray:
        n = len(df)
        sig = np.zeros(n)

        sp = df['span'].values
        pm = df['pm_momentum'].values
        dc = df['dc_breakout'].values
        dmi = df['dmi_dir'].values

        has_ctx = 'market_state_1h' in df.columns
        state_1h = df['market_state_1h'].values if has_ctx else None

        base_mask = (np.abs(dmi) < self.DMI_TH) & \
                    np.isfinite(sp) & np.isfinite(pm) & np.isfinite(dc)
        if has_ctx:
            base_mask &= (state_1h != 'weak_trend')
        idx = np.where(base_mask)[0]
        if len(idx) == 0:
            return sig

        n_idx = len(idx)
        votes = np.zeros((n_idx, 3), dtype=int)
        votes[:, 0] = np.where(sp[idx] < -self.TH1, 1, np.where(sp[idx] > self.TH1, -1, 0))
        votes[:, 1] = np.where(pm[idx] > self.TH2, 1, np.where(pm[idx] < -self.TH2, -1, 0))
        votes[:, 2] = np.where(dc[idx] > self.TH3, 1, np.where(dc[idx] < -self.TH3, -1, 0))

        total = votes.sum(axis=1)
        raw = np.zeros(n_idx)
        raw[total >= self.MIN_V] = 1
        raw[total <= -self.MIN_V] = -1

        if has_ctx:
            st_mask = state_1h[idx] == 'strong_trend'
            if st_mask.any():
                dmi_sign = np.sign(dmi[idx[st_mask]])
                keep = (raw[st_mask] == dmi_sign) | (raw[st_mask] == 0)
                raw[np.where(st_mask)[0][~keep]] = 0

        sig[idx] = raw
        return sig

    async def check_exit(self, row: dict, pos: dict, ctx, params: dict) -> str | None:
        c = float(row.get("close", 0))
        bv = float(row.get("bb_pct_b", 0.5))
        ep = float(pos.get("entry_price", 0))
        bh = pos.get("bars_held", 0)
        sd = int(pos.get("side", 0))

        pnl = (c - ep) / ep if sd > 0 else (ep - c) / ep

        if pnl <= -self.FIXED_SL:
            self._pd = False
            return 'fixed_sl'
        if pnl >= self.PARTIAL_TP and not self._pd:
            self._pd = True
            return 'partial_tp'
        if bh >= self.MIN_HOLD and self.TP_BB_LOW <= bv <= self.TP_BB_HIGH:
            self._pd = False
            return 'tp_bb'
        if bh >= self.MAX_HOLD:
            self._pd = False
            return 'timeout'
        return None
