"""Monitor 主体 —— 统一采集查询所有 channel 数据。

被动订阅 bus + 主动读 channel 运行时状态，对外暴露查询 API。
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from app.monitor.collector import Collector

logger = logging.getLogger(__name__)

OHLCV_COLUMNS = {"timestamp", "open", "high", "low", "close", "volume", "interval"}


class Monitor:
    """统一监控器。"""

    def __init__(self, bootstrap, bus, host: str = "0.0.0.0", port: int = 8080) -> None:
        self._bootstrap = bootstrap
        self._bus = bus
        self._host = host
        self._port = port
        self._collector = Collector(bootstrap, bus)
        self._server_task = None

    def start(self) -> None:
        """启动 collector 订阅 + http server（异步）。"""
        self._collector.bind()
        from app.monitor.server import build_app, serve
        app = build_app(self)
        self._server_task = asyncio_create_task(serve(app, self._host, self._port))
        logger.info("监控器已启动: http://%s:%s", self._host, self._port)

    # ============================================================
    # 查询 API
    # ============================================================

    def snapshot(self) -> dict[str, Any]:
        """总览：master + 各 channel 一行汇总。"""
        master = self.master_detail()
        channels = self.channel_summary()
        total_pnl = sum(c["daily_pnl"] for c in channels)
        return {
            "master": {k: master[k] for k in ("account_id", "balance_total", "subs_count")},
            "channels_count": len(channels),
            "total_daily_pnl": total_pnl,
            "channels": channels,
        }

    def channel_summary(self) -> list[dict[str, Any]]:
        """channel 列表汇总。"""
        result = []
        for ch in self._bootstrap._channels.values():
            sub = ch.sub_account
            pos = sub.position if sub else None
            sym = ch.symbol
            result.append({
                "channel_id": ch.config.channel_id,
                "instance_id": ch.id[:8],
                "symbol": sym.symbol,
                "interval": ch.config.interval,
                "market_type": ch.market_type,
                "market_info": self._symbol_info(sym),
                "sub_account_id": sub.account_id if sub else None,
                "leverage": sub.leverage_config.leverage if sub else 0,
                "allocated_balance": float(sub.allocated_balance) if sub else 0.0,
                "margin_used": float(sub.margin_used) if sub else 0.0,
                "daily_pnl": float(sub.daily_pnl) if sub else 0.0,
                "position": {
                    "side": pos.side,
                    "qty": str(pos.qty),
                    "avg_price": str(pos.avg_price),
                    "unrealized_pnl": str(pos.unrealized_pnl),
                } if pos else None,
            })
        return result

    @staticmethod
    def _symbol_info(sym) -> dict[str, Any]:
        """Symbol 市场信息（精度/限额/费率/合约）。"""
        return {
            "market": sym.market,
            "amount_precision": sym.amount_precision,
            "price_precision": sym.price_precision,
            "min_amount": float(sym.min_amount),
            "max_amount": float(sym.max_amount),
            "min_cost": float(sym.min_cost),
            "min_price": float(sym.min_price),
            "maker_fee": float(sym.maker_fee),
            "taker_fee": float(sym.taker_fee),
            "contract_size": float(sym.contract_size),
            "settle": sym.settle,
            "is_linear": sym.is_linear,
        }

    def channel_detail(self, cid: str) -> dict[str, Any] | None:
        """单 channel 详情 + 最近历史。"""
        ch = self._find_channel(cid)
        if ch is None:
            return None
        sub = ch.sub_account
        rec = self._collector.records.get(ch.config.channel_id)

        # 从 DataFrame 提取当前指标
        current_indicators = {}
        for iv, df in ch.market.bars.items():
            if len(df) > 0:
                last_row = df.iloc[-1]
                inds = {}
                for col in df.columns:
                    if col not in OHLCV_COLUMNS and col not in ("signal_value", "signal_strength", "signal_reason"):
                        val = last_row[col]
                        if pd.notna(val):
                            inds[col] = str(val)
                current_indicators[iv] = inds

        return {
            "channel_id": ch.config.channel_id,
            "instance_id": ch.id,
            "symbol": ch.symbol.symbol,
            "interval": ch.config.interval,
            "market_type": ch.market_type,
            "market_info": self._symbol_info(ch.symbol),
            "sub_account": {
                "account_id": sub.account_id,
                "allocated_balance": float(sub.allocated_balance),
                "daily_pnl": float(sub.daily_pnl),
                "margin_used": float(sub.margin_used),
                "leverage": sub.leverage_config.leverage,
                "position": {
                    "side": sub.position.side,
                    "qty": str(sub.position.qty),
                    "avg_price": str(sub.position.avg_price),
                    "unrealized_pnl": str(sub.position.unrealized_pnl),
                },
            } if sub else None,
            "current_signal": self._signal_dict(ch.market.current_signal),
            "current_indicators": current_indicators,
            "bars_count": {iv: len(df) for iv, df in ch.market.bars.items()},
            "history": {
                "klines": len(rec.klines) if rec else 0,
                "indicators": len(rec.indicators) if rec else 0,
                "signals": len(rec.signals) if rec else 0,
                "orders": len(rec.orders) if rec else 0,
            },
        }

    def master_detail(self) -> dict[str, Any]:
        """主账号详情。"""
        m = self._bootstrap._master
        if m is None:
            return {"account_id": None, "balance_total": 0.0, "subs_count": 0}
        return {
            "account_id": m.account_id,
            "balance": {
                "total": float(m.balance.total),
                "free": float(m.balance.free),
                "used": float(m.balance.used),
                "currency": m.balance.currency,
            },
            "balance_total": float(m.balance.total),
            "positions": {
                sym: {"side": p.side, "qty": str(p.qty), "avg_price": str(p.avg_price)}
                for sym, p in m.positions.items()
            },
            "leverages": {
                sym: {"leverage": l.leverage, "margin_mode": l.margin_mode}
                for sym, l in m.leverages.items()
            },
            "subs_count": len(m.sub_accounts),
            "daily_pnl": float(m.daily_pnl),
            "sub_accounts": [
                {
                    "account_id": s.account_id,
                    "symbol": s.symbol,
                    "allocated_balance": float(s.allocated_balance),
                    "daily_pnl": float(s.daily_pnl),
                    "margin_used": float(s.margin_used),
                    "leverage_config": {
                        "leverage": s.leverage_config.leverage,
                        "margin_mode": s.leverage_config.margin_mode,
                    },
                    "position": {
                        "side": s.position.side,
                        "qty": str(s.position.qty),
                        "avg_price": str(s.position.avg_price),
                    },
                }
                for s in m.sub_accounts
            ],
        }

    def history(self, cid: str, kind: str, limit: int = 20) -> list | None:
        """查 channel 历史：klines/indicators/signals/orders。"""
        ch = self._find_channel(cid)
        if ch is None:
            return None
        rec = self._collector.records.get(ch.config.channel_id)
        if rec is None:
            return []
        seq = getattr(rec, kind, None)
        if seq is None:
            return None
        items = list(seq)[-limit:] if limit > 0 else list(seq)
        return [self._serialize(item) for item in items]

    # ============================================================
    # 辅助
    # ============================================================

    def _find_channel(self, cid: str):
        for ch in self._bootstrap._channels.values():
            if ch.config.channel_id == cid:
                return ch
        for ch in self._bootstrap._channels.values():
            if ch.id.startswith(cid) or ch.id[:8] == cid:
                return ch
        return None

    def _signal_dict(self, sig) -> dict | None:
        if sig is None:
            return None
        return {
            "direction": sig.direction,
            "strength": sig.strength,
            "value": sig.value,
            "reason": sig.reason,
        }

    def _serialize(self, item: Any) -> Any:
        """序列化历史项为 JSON 可序列化结构。"""
        if isinstance(item, dict):
            return item
        if isinstance(item, pd.Series):
            return self._sanitize(item.to_dict())
        return str(item)

    def _sanitize(self, d: dict) -> dict:
        """清理 dict 中的非 JSON 值。"""
        result = {}
        for k, v in d.items():
            if isinstance(v, float):
                if pd.isna(v):
                    result[k] = None
                else:
                    result[k] = v
            elif isinstance(v, pd.Timestamp):
                result[k] = int(v.timestamp())
            else:
                result[k] = str(v) if v is not None else None
        return result


def asyncio_create_task(coro):
    import asyncio
    return asyncio.create_task(coro)
