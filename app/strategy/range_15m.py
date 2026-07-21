"""震荡策略 15m — span+bb+vol_ratio 3指标投票 + 跨TF趋势门控 + PartTP=0.3%.

指标研究驱动:
  span: 自适应波动标准化, zero-lag, 跨时间稳定
  bb_pct_b: 布林带位置, 均值回归锚点
  vol_ratio: 成交量比率, 放量确认

Vote设计 (跨类别: 波动率+波动率+成交量):
  Vote1 — span 自适应偏离: |span|>th → 极端偏离→反转
  Vote2 — bb_pct_b 均值回归: bb<low→long, bb>high→short
  Vote3 — vol_ratio 放量确认: vol>th + span同向→确认
  min_votes=2

跨TF门控 (gate_data):
  h1 strong_trend/moderate_trend + |dmi_dir| > GATE_DMI_TH → 仅允许顺势信号
  h1 range/weak_trend → 无方向限制（原始震荡逻辑）
"""
import numpy as np


def _vote_range_span(df, idx: np.ndarray, span_th: float, bb_low: float,
                     bb_high: float, vol_th: float, min_votes: int) -> np.ndarray:
    sp = df["span"].values[idx]
    bb = df["bb_pct_b"].values[idx]
    vr = df["vol_ratio"].values[idx]

    n = len(idx)
    votes = np.zeros((n, 3), dtype=int)

    votes[:, 0] = np.where(sp < -span_th, 1, np.where(sp > span_th, -1, 0))
    votes[:, 1] = np.where(bb < bb_low, 1, np.where(bb > bb_high, -1, 0))
    votes[:, 2] = np.where(vr > vol_th,
        np.where(sp < -span_th, 1, np.where(sp > span_th, -1, 0)), 0)

    total = votes.sum(axis=1)
    signal = np.zeros(n)
    signal[total >= min_votes] = 1
    signal[total <= -min_votes] = -1
    return signal


class Range15mStrategy:
    """震荡策略 — 15m K线, span+bb+vol_ratio 投票 + DMI方向过滤."""

    name = "range_15m"
    version = "2.0.0"

    tf = "15m"
    FIXED_SL = 0.02
    PARTIAL_TP = 0.003
    MAX_HOLD = 24
    MIN_HOLD = 1
    TP_BB_LOW = 0.3
    TP_BB_HIGH = 0.6

    SPAN_TH = 0.30
    BB_LOW = 0.10
    BB_HIGH = 0.75
    VOL_TH = 0.20
    MIN_VOTES = 2
    DMI_THRESHOLD = 0.08

    # 跨TF门控参数
    GATE_DMI_TH = 0.05          # h1 |dmi_dir| 超过此值才视为有明确趋势方向
    GATE_STATES = {"strong_trend", "moderate_trend"}

    def __init__(self):
        self._partial_done = False

    def required_indicators(self, params: dict) -> list[str]:
        return ["dmi_dir", "span", "bb_pct_b", "vol_ratio", "atr_vol"]

    def _apply_trend_gate(self, signal: np.ndarray, gate_data: dict) -> np.ndarray:
        """根据高TF趋势方向过滤反向信号（向量化，但实际只影响最后一bar）。"""
        state = gate_data.get("market_state", "range")
        if state not in self.GATE_STATES:
            return signal
        dmi = gate_data.get("dmi_dir", 0.0)
        if abs(dmi) < self.GATE_DMI_TH:
            return signal
        n = len(signal)
        gated = signal.copy()
        gated[(gated > 0) & (np.full(n, dmi < 0))] = 0
        gated[(gated < 0) & (np.full(n, dmi > 0))] = 0
        return gated

    def route(self, df, params: dict | None = None, gate_data: dict | None = None) -> "np.ndarray":
        n = len(df)
        signal = np.zeros(n, dtype=float)

        dmi_ok = np.abs(df["dmi_dir"].values) < self.DMI_THRESHOLD
        valid = dmi_ok & (
            df["span"].notna().values &
            df["bb_pct_b"].notna().values &
            df["vol_ratio"].notna().values
        )
        idx = np.where(valid)[0]
        if len(idx) == 0:
            return signal

        signal[idx] = _vote_range_span(
            df, idx,
            span_th=self.SPAN_TH,
            bb_low=self.BB_LOW,
            bb_high=self.BB_HIGH,
            vol_th=self.VOL_TH,
            min_votes=self.MIN_VOTES,
        )

        if gate_data:
            signal = self._apply_trend_gate(signal, gate_data)

        return signal

    async def check_exit(self, row: dict, pos: dict, ctx, params: dict) -> str | None:
        c = float(row.get("close", 0))
        b_val = float(row.get("bb_pct_b", 0.5))
        ep = float(pos.get("entry_price", 0))
        bars_held = pos.get("bars_held", 0)
        s = int(pos.get("side", 0))

        pnl = (c - ep) / ep if s > 0 else (ep - c) / ep

        if pnl <= -self.FIXED_SL:
            self._partial_done = False
            return "fixed_sl"

        if pnl >= self.PARTIAL_TP and not self._partial_done:
            self._partial_done = True
            return "partial_tp"

        if bars_held >= self.MIN_HOLD:
            if self.TP_BB_LOW <= b_val <= self.TP_BB_HIGH:
                self._partial_done = False
                return "tp_bb"

        if bars_held >= self.MAX_HOLD:
            self._partial_done = False
            return "timeout"

        return None
