"""cl 指标库 — 包装 cl common/indicators.py 纯函数为 Indicator 协议类。

每个 compute 对整列向量化计算，只返回最新一行值。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _add_dmi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_di = 100.0 * pd.Series(plus_dm, index=df.index).ewm(alpha=1.0 / period, adjust=False).mean() / (atr + 1e-10)
    minus_di = 100.0 * pd.Series(minus_dm, index=df.index).ewm(alpha=1.0 / period, adjust=False).mean() / (atr + 1e-10)
    diff = plus_di - minus_di
    dx = 100.0 * abs(diff) / (plus_di + minus_di + 1e-10)
    adx = dx.ewm(alpha=1.0 / period, adjust=False).mean()
    df = df.copy()
    df["dmi_dir"] = np.clip(diff / 100.0, -1.0, 1.0)
    df["dmi_trend"] = np.clip(adx / 100.0, 0.0, 1.0)
    return df


def _add_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_di = 100.0 * pd.Series(plus_dm, index=df.index).ewm(alpha=1.0 / period, adjust=False).mean() / (atr + 1e-10)
    minus_di = 100.0 * pd.Series(minus_dm, index=df.index).ewm(alpha=1.0 / period, adjust=False).mean() / (atr + 1e-10)
    dx = 100.0 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
    adx = dx.ewm(alpha=1.0 / period, adjust=False).mean()
    df = df.copy()
    df["adx"] = np.clip(adx / 100.0, 0.0, 1.0)
    return df


def _add_pm(df: pd.DataFrame, short: int = 3, mid: int = 10, long: int = 30) -> pd.DataFrame:
    close = df["close"]
    raw = close.pct_change(short) * 0.5 + close.pct_change(mid) * 0.3 + close.pct_change(long) * 0.2
    df = df.copy()
    df["pm_momentum"] = np.clip(raw.fillna(0) * 50, -1.0, 1.0)
    return df


def _add_kdj(df: pd.DataFrame, n: int = 9, k: int = 3, d: int = 3) -> pd.DataFrame:
    low_n = df["low"].rolling(window=n).min()
    high_n = df["high"].rolling(window=n).max()
    rsv = 100.0 * (df["close"] - low_n) / (high_n - low_n + 1e-10)
    k_arr = rsv.ewm(alpha=1.0 / k, adjust=False).mean().fillna(50.0)
    d_arr = k_arr.ewm(alpha=1.0 / d, adjust=False).mean()
    j_arr = 3.0 * k_arr - 2.0 * d_arr
    df = df.copy()
    j = j_arr
    momentum = np.where(j > 90, -(np.minimum((j - 90) / 25, 1.0)),
               np.where(j < 10, np.minimum((10 - j) / 25, 1.0),
               (j - 50) / 60))
    df["kdj_momentum"] = np.clip(momentum, -1.0, 1.0)
    df["kdj_reversal"] = np.where(abs(j - 50) > 30, np.clip(abs(j - 50) / 50, 0.0, 1.0), 0.0)
    return df


def _add_dc(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    upper = df["high"].rolling(window=period).max()
    lower = df["low"].rolling(window=period).min()
    mid = (upper + lower) / 2.0
    df = df.copy()
    df["dc_breakout"] = np.clip((df["close"] - mid) / (upper - lower + 1e-10) * 2.0, -1.0, 1.0).fillna(0)
    return df


def _add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    df = df.copy()
    df["atr_vol"] = atr / (close + 1e-10)
    return df


def _add_autocorr(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    ret = df["close"].pct_change()
    ret_prev = ret.shift(1)
    m1 = ret.rolling(period).mean()
    m2 = ret_prev.rolling(period).mean()
    cov = (ret * ret_prev).rolling(period).mean() - m1 * m2
    s1 = ret.rolling(period).std()
    s2 = ret_prev.rolling(period).std()
    ac = cov / (s1 * s2 + 1e-10)
    df = df.copy()
    df["autocorr"] = ac.fillna(0).clip(-1.0, 1.0)
    df["ac_smooth"] = df["autocorr"].ewm(span=8, adjust=False).mean().values
    return df


def _add_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, sig: int = 9) -> pd.DataFrame:
    close = df["close"]
    ema_f = close.ewm(span=fast, adjust=False).mean()
    ema_s = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_f - ema_s
    sig_line = macd_line.ewm(span=sig, adjust=False).mean()
    histogram = macd_line - sig_line
    hist_norm = histogram / (close + 1e-10)
    df = df.copy()
    df["macd_momentum"] = np.clip(hist_norm * 50, -1.0, 1.0)
    hist_prev = histogram.shift(1)
    expanding = abs(histogram) > abs(hist_prev)
    df["macd_trend"] = np.clip(np.where(expanding, abs(hist_norm) * 100, abs(hist_norm) * 50), 0.0, 1.0)
    return df


def _add_bollinger(df: pd.DataFrame, period: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    close = df["close"]
    mid = close.rolling(window=period).mean()
    std_band = close.rolling(window=period).std()
    upper = mid + std_band * num_std
    lower = mid - std_band * num_std
    df = df.copy()
    df["bb_pct_b"] = (close - lower) / (upper - lower + 1e-10)
    return df


def _add_mfi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    high, low, close, volume = df["high"], df["low"], df["close"], df["volume"]
    tp = (high + low + close) / 3.0
    raw_mf = tp * volume
    mf_pos = np.where(tp > tp.shift(1), raw_mf, 0.0)
    mf_neg = np.where(tp < tp.shift(1), raw_mf, 0.0)
    mf_pos_sum = pd.Series(mf_pos, index=df.index).rolling(window=period).sum()
    mf_neg_sum = pd.Series(mf_neg, index=df.index).rolling(window=period).sum()
    mf_ratio = mf_pos_sum / (mf_neg_sum + 1e-10)
    mfi = 100.0 - 100.0 / (1.0 + mf_ratio)
    df = df.copy()
    df["mfi"] = mfi.fillna(50.0)
    df["mfi_momentum"] = np.clip((50.0 - mfi) / 40.0, -1.0, 1.0)
    return df


def _add_obv(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"]
    volume = df["volume"]
    direction = np.where(close > close.shift(1), 1.0, np.where(close < close.shift(1), -1.0, 0.0))
    obv = (direction * volume).cumsum()
    obv_sma = pd.Series(obv, index=df.index).rolling(window=20).mean()
    obv_slope = pd.Series(obv, index=df.index).diff(5) / (pd.Series(obv, index=df.index).rolling(window=5).std() + 1e-10)
    obv_slope = obv_slope.fillna(0).clip(-3, 3)
    df = df.copy()
    df["obv"] = obv
    df["obv_sma"] = obv_sma
    df["obv_signal"] = np.clip(obv_slope.values / 3.0, -1.0, 1.0)
    return df


def _add_keltner(df: pd.DataFrame, period: int = 20, atr_period: int = 10,
                 multiplier: float = 1.5) -> pd.DataFrame:
    close, high, low = df["close"], df["high"], df["low"]
    prev_close = close.shift(1)
    mid = close.ewm(span=period, adjust=False).mean()
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=atr_period, adjust=False).mean()
    upper = mid + atr * multiplier
    lower = mid - atr * multiplier
    df = df.copy()
    df["kc_pct_b"] = (close - lower) / (upper - lower + 1e-10)
    if "bb_pct_b" in df.columns:
        df["bb_kc_ratio"] = (df["bb_pct_b"] - df["kc_pct_b"]).fillna(0)
    return df


def _add_vol_ratio(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    volume = df["volume"]
    vol_sma = volume.rolling(window=period).mean()
    df = df.copy()
    df["vol_ratio"] = (volume / (vol_sma + 1e-10)).fillna(1.0)
    return df


def _add_span(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    close = df["close"]
    ret = close.pct_change()
    rolling_median = ret.rolling(window=period).median()
    rolling_mad = (ret - rolling_median).abs().rolling(window=period).median()
    span = (ret - rolling_median) / (rolling_mad * 1.4826 + 1e-10)
    span_smooth = span.ewm(span=period // 2, adjust=False).mean()
    df = df.copy()
    df["span"] = np.clip(span_smooth.fillna(0) / 3.0, -1.0, 1.0)
    return df


# ── Indicator 协议类 ──


class DmiCalculator:
    name = "dmi"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["dmi_dir", "dmi_trend"]

    def compute(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        period = params.get("period", 14)
        if len(df) < period + 1:
            return {}
        result = _add_dmi(df, period)
        df["dmi_dir"] = result["dmi_dir"].values
        df["dmi_trend"] = result["dmi_trend"].values
        last = result.iloc[-1]
        return {"dmi_dir": float(last["dmi_dir"]), "dmi_trend": float(last["dmi_trend"])}


class AdxCalculator:
    name = "adx"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["adx"]

    def compute(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        period = params.get("period", 14)
        if len(df) < period + 1:
            return {}
        result = _add_adx(df, period)
        df["adx"] = result["adx"].values
        return {"adx": float(result["adx"].iloc[-1])}


class PmCalculator:
    name = "pm"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["pm_momentum"]

    def compute(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        short = params.get("short", 3)
        mid = params.get("mid", 10)
        long = params.get("long", 30)
        result = _add_pm(df, short, mid, long)
        df["pm_momentum"] = result["pm_momentum"].values
        return {"pm_momentum": float(result["pm_momentum"].iloc[-1])}


class KdjCalculator:
    name = "kdj"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["kdj_momentum", "kdj_reversal"]

    def compute(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        n = params.get("n", 9)
        k = params.get("k", 3)
        d = params.get("d", 3)
        if len(df) < n + 1:
            return {}
        result = _add_kdj(df, n, k, d)
        df["kdj_momentum"] = result["kdj_momentum"].values
        df["kdj_reversal"] = result["kdj_reversal"].values
        last = result.iloc[-1]
        return {"kdj_momentum": float(last["kdj_momentum"]), "kdj_reversal": float(last["kdj_reversal"])}


class DcCalculator:
    name = "dc"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["dc_breakout"]

    def compute(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        period = params.get("period", 20)
        if len(df) < period + 1:
            return {}
        result = _add_dc(df, period)
        df["dc_breakout"] = result["dc_breakout"].values
        return {"dc_breakout": float(result["dc_breakout"].iloc[-1])}


class AtrCalculator:
    name = "atr"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["atr_vol"]

    def compute(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        period = params.get("period", 14)
        if len(df) < period + 1:
            return {}
        result = _add_atr(df, period)
        df["atr_vol"] = result["atr_vol"].values
        return {"atr_vol": float(result["atr_vol"].iloc[-1])}


class AutocorrCalculator:
    name = "autocorr"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["autocorr", "ac_smooth"]

    def compute(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        period = params.get("period", 20)
        if len(df) < period + 1:
            return {}
        result = _add_autocorr(df, period)
        df["autocorr"] = result["autocorr"].values
        df["ac_smooth"] = result["ac_smooth"].values
        last = result.iloc[-1]
        return {"autocorr": float(last["autocorr"]), "ac_smooth": float(last["ac_smooth"])}


class MacdCalculator:
    name = "macd"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["macd_momentum", "macd_trend"]

    def compute(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        fast = params.get("fast", 12)
        slow = params.get("slow", 26)
        sig = params.get("sig", 9)
        if len(df) < slow + 1:
            return {}
        result = _add_macd(df, fast, slow, sig)
        df["macd_momentum"] = result["macd_momentum"].values
        df["macd_trend"] = result["macd_trend"].values
        last = result.iloc[-1]
        return {"macd_momentum": float(last["macd_momentum"]), "macd_trend": float(last["macd_trend"])}


class BollingerCalculator:
    name = "bollinger"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["bb_pct_b"]

    def compute(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        period = params.get("period", 20)
        num_std = params.get("num_std", 2.0)
        if len(df) < period + 1:
            return {}
        result = _add_bollinger(df, period, num_std)
        df["bb_pct_b"] = result["bb_pct_b"].values
        return {"bb_pct_b": float(result["bb_pct_b"].iloc[-1])}


class MfiCalculator:
    name = "mfi"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["mfi", "mfi_momentum"]

    def compute(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        period = params.get("period", 14)
        if len(df) < period + 1:
            return {}
        result = _add_mfi(df, period)
        df["mfi"] = result["mfi"].values
        df["mfi_momentum"] = result["mfi_momentum"].values
        last = result.iloc[-1]
        return {"mfi": float(last["mfi"]), "mfi_momentum": float(last["mfi_momentum"])}


class ObvCalculator:
    name = "obv"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["obv", "obv_signal"]

    def compute(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        if len(df) < 30:
            return {}
        result = _add_obv(df)
        df["obv"] = result["obv"].values
        df["obv_sma"] = result["obv_sma"].values
        df["obv_signal"] = result["obv_signal"].values
        last = result.iloc[-1]
        return {"obv": float(last["obv"]), "obv_signal": float(last["obv_signal"])}


class KeltnerCalculator:
    name = "keltner"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        keys = ["kc_pct_b"]
        if params.get("with_bb_kc_ratio", False):
            keys.append("bb_kc_ratio")
        return keys

    def compute(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        period = params.get("period", 20)
        atr_period = params.get("atr_period", 10)
        multiplier = params.get("multiplier", 1.5)
        if len(df) < max(period, atr_period) + 1:
            return {}
        result = _add_keltner(df, period, atr_period, multiplier)
        df["kc_pct_b"] = result["kc_pct_b"].values
        if "bb_kc_ratio" in result.columns:
            df["bb_kc_ratio"] = result["bb_kc_ratio"].values
        last = result.iloc[-1]
        out = {"kc_pct_b": float(last["kc_pct_b"])}
        if "bb_kc_ratio" in result.columns:
            out["bb_kc_ratio"] = float(last["bb_kc_ratio"])
        return out


class VolRatioCalculator:
    name = "vol_ratio"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["vol_ratio"]

    def compute(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        period = params.get("period", 20)
        if len(df) < period + 1:
            return {}
        result = _add_vol_ratio(df, period)
        df["vol_ratio"] = result["vol_ratio"].values
        return {"vol_ratio": float(result["vol_ratio"].iloc[-1])}


class SpanCalculator:
    name = "span"
    version = "1.0.0"

    def output_keys(self, params: dict) -> list[str]:
        return ["span"]

    def compute(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        period = params.get("period", 20)
        if len(df) < period + 1:
            return {}
        result = _add_span(df, period)
        df["span"] = result["span"].values
        return {"span": float(result["span"].iloc[-1])}
