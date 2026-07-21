"""入站：策略调度器 — 入场/离场分岔 + 跨TF门控注入。

无持仓 → strat.route(df, params, gate_data) → entry signal
有持仓 → strat.check_exit() → exit signal

跨TF门控通过 ctx.channel.bootstrap 查询高TF channel，无需额外依赖注入。
"""
from __future__ import annotations

import logging
from typing import Any

from app.strategy.registry import StrategyRegistry
from core.domain.event import Event, EventType
from core.domain.signal import Signal
from core.ports.context import Context
from core.ports.handler import Handler

__all__ = ["Signal", "SignalHandler"]

logger = logging.getLogger(__name__)


class SignalHandler(Handler):
    handles = frozenset({EventType.KLINE})

    def __init__(self, registry: StrategyRegistry | None = None) -> None:
        self._registry = registry or StrategyRegistry()
        self._strat_cache: dict[str, object] = {}
        self._pos_cache: dict[str, dict] = {}

    def _resolve_gate(self, ctx: Context, symbol: str, gate_cfg) -> dict[str, Any] | None:
        """从高TF channel 提取最新市场状态列。"""
        bootstrap = getattr(ctx.channel, "bootstrap", None)
        if bootstrap is None:
            return None
        htf_ch = bootstrap.get_channel_by_symbol_interval(symbol, gate_cfg.interval)
        if htf_ch is None:
            return None
        htf_df = htf_ch.market.bars.get(gate_cfg.interval)
        if htf_df is None or len(htf_df) == 0:
            return None
        latest = htf_df.iloc[-1]
        gate_data = {}
        for col in gate_cfg.columns:
            if col in latest:
                val = latest[col]
                if hasattr(val, "item"):
                    val = val.item()
                gate_data[col] = val
        return gate_data

    async def channel_read(self, ctx: Context, event: Event) -> None:
        row = event.payload
        if not isinstance(row, dict):
            await ctx.fire_channel_read(event)
            return

        strat_cfg = ctx.channel.config.strategy
        channel_id = ctx.channel.config.channel_id

        strat = self._strat_cache.get(channel_id)
        if strat is None:
            try:
                strat_cls = self._registry.get(strat_cfg.name)
                strat = strat_cls()
                self._strat_cache[channel_id] = strat
            except KeyError:
                logger.warning("策略 '%s' 未注册", strat_cfg.name)
                await ctx.fire_channel_read(event)
                return
            except Exception:
                logger.warning("策略 %s 实例化异常", strat_cfg.name, exc_info=True)
                await ctx.fire_channel_read(event)
                return

        # ── 从 sub_account.position 判断是否持仓 ──
        acc = ctx.channel.sub_account
        has_position = (
            acc is not None
            and acc.position.side != ""
            and acc.position.qty > 0
        )

        signal = None
        try:
            if has_position:
                # ── 持仓中 → check_exit ──
                side = 1 if acc.position.side == "BUY" else -1
                pos = self._pos_cache.get(channel_id)
                if pos is None:
                    pos = {
                        "side": side,
                        "entry_price": float(acc.position.avg_price),
                        "best_price": float(acc.position.avg_price),
                        "entry_bar": 0,
                        "bars_held": 0,
                        "partial_done": False,
                    }
                    self._pos_cache[channel_id] = pos

                bars_held = pos.get("bars_held", 0) + 1
                pos["bars_held"] = bars_held
                c_val = float(row.get("close", 0))
                h = float(row.get("high", 0))
                l = float(row.get("low", 0))
                s = pos["side"]
                bp = pos.get("best_price", pos.get("entry_price", c_val))
                pos["best_price"] = max(bp, h) if s > 0 else min(bp, l)

                reason = await strat.check_exit(row, pos, ctx, strat_cfg.params)
                if reason:
                    exit_val = float(-s)
                    signal = Signal(exit_val, reason, "exit")
                    if reason == "partial_tp":
                        pos["partial_done"] = True
                    else:
                        self._pos_cache.pop(channel_id, None)
            else:
                # ── 空仓 → route(df) 取最后信号 ──
                self._pos_cache.pop(channel_id, None)
                interval = row.get("interval", "")
                df = ctx.channel.market.bars.get(interval)
                if df is not None and len(df) >= 50:
                    gate_data = None
                    gate_cfg = getattr(strat_cfg, "gate", None)
                    if gate_cfg is not None:
                        gate_data = self._resolve_gate(ctx, event.symbol, gate_cfg)
                    sig_arr = strat.route(df, strat_cfg.params, gate_data=gate_data)
                    val = float(sig_arr[-1])
                    if val != 0:
                        signal = Signal(val, strat.name.upper(), "entry")
        except Exception:
            logger.warning("策略 %s 异常", strat_cfg.name, exc_info=True)

        if signal is None:
            signal = Signal(0.0, "NO_SIGNAL")

        ctx.channel.market.current_signal = signal

        # 回写信号列到 DataFrame
        interval = row.get("interval", "")
        df = ctx.channel.market.bars.get(interval)
        if df is not None and len(df) > 0:
            idx = df.index[-1]
            df.loc[idx, "signal_value"] = signal.value
            df.loc[idx, "signal_strength"] = signal.strength
            df.loc[idx, "signal_reason"] = signal.reason

        enriched = {
            **row,
            "signal_value": signal.value,
            "signal_strength": signal.strength,
            "signal_reason": signal.reason,
            "signal_type": signal.signal_type,
        }
        # 部分止盈只平 50%
        if signal.signal_type == "exit" and signal.reason == "partial_tp":
            enriched["exit_fraction"] = 0.5
        logger.debug("信号: %s type=%s 值=%.4f 原因=%s",
                     signal.direction, signal.signal_type, signal.value, signal.reason)
        await ctx.fire_channel_read(Event(EventType.KLINE, event.symbol, enriched))
