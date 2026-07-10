"""Config —— 配置数据模型与加载器。

每个 symbol@timeframe 对应一个 ChannelConfig 实例。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ── 子配置 ──────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class IndicatorDef:
    """指标注册表条目：name → 模块路径。默认参数由指标类内 params.get(k, 默认) 兜底。"""
    name: str
    module: str


@dataclass(frozen=True, slots=True)
class IndicatorConfig:
    """channel 内指标引用：name 指向注册表条目，params 为调用时注入参数。"""
    name: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StrategyDef:
    """策略注册表条目：name → 模块路径。默认参数由策略类内 params.get(k, 默认) 兜底。"""
    name: str
    module: str


@dataclass(frozen=True, slots=True)
class StrategyConfig:
    """策略配置（含策略参数与所需指标）。"""
    name: str
    params: dict[str, Any] = field(default_factory=dict)
    indicators: list[IndicatorConfig] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RiskConfig:
    """风控参数。None=未配置（中间件使用自身默认值），0=显式禁用检查。"""
    daily_loss_limit: float | None = None
    max_drawdown: float | None = None
    max_per_order_ratio: float | None = None
    max_leverage: float | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> RiskConfig:
        if not d:
            return cls()
        return cls(
            daily_loss_limit=d.get("daily_loss_limit"),
            max_drawdown=d.get("max_drawdown"),
            max_per_order_ratio=d.get("max_per_order_ratio"),
            max_leverage=d.get("max_leverage"),
        )


# ── 核心配置 ─────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class ChannelConfig:
    """单个 symbol@timeframe 的完整配置。"""
    symbol: str
    market: str
    interval: str
    allocation: float
    strategy: StrategyConfig
    risk_pre: RiskConfig = field(default_factory=RiskConfig)
    risk_post: RiskConfig = field(default_factory=RiskConfig)

    @property
    def channel_id(self) -> str:
        """唯一标识: symbol@timeframe，如 BTC/USDT@1m。"""
        return f"{self.symbol}@{self.interval}"


@dataclass(frozen=True, slots=True)
class ExchangeConfig:
    """交易所连接配置。

    mode: ccxt=ccxt.pro（spot testnet / 实盘）。
    name: ccxt.pro 交易所 id（如 binance）。
    proxy: 本地代理地址（如 http://127.0.0.1:7897），空表示直连。
    sandbox: True=使用 testnet，False=实盘。
    """
    api_key: str = ""
    api_secret: str = ""
    mode: str = "ccxt"
    name: str = "binance"
    proxy: str = ""
    sandbox: bool = True


@dataclass(slots=True)
class AppConfig:
    """应用顶层配置。"""
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    channels: list[ChannelConfig] = field(default_factory=list)
    strategies: dict[str, StrategyDef] = field(default_factory=dict)
    indicators: dict[str, IndicatorDef] = field(default_factory=dict)

    def by_channel_id(self) -> dict[str, ChannelConfig]:
        """按 channel_id 索引。"""
        return {c.channel_id: c for c in self.channels}

    def by_symbol(self, symbol: str) -> list[ChannelConfig]:
        """按币对过滤。"""
        return [c for c in self.channels if c.symbol == symbol]



# ── YAML 解析 ─────────────────────────────────────────────

def _parse_indicator(raw: dict[str, Any]) -> IndicatorConfig:
    return IndicatorConfig(
        name=raw["name"],
        params=raw.get("params", {}),
    )


def _parse_strategy(raw: dict[str, Any]) -> StrategyConfig:
    return StrategyConfig(
        name=raw["name"],
        params=raw.get("params", {}),
        indicators=[_parse_indicator(i) for i in raw.get("indicators", [])],
    )


def _parse_channel(symbol: str, market: str, allocation: float,
                    interval: str, raw: dict[str, Any]) -> ChannelConfig:
    return ChannelConfig(
        symbol=symbol,
        market=market,
        interval=interval,
        allocation=allocation,
        strategy=_parse_strategy(raw["strategy"]),
        risk_pre=RiskConfig.from_dict(raw.get("risk_pre")),
        risk_post=RiskConfig.from_dict(raw.get("risk_post")),
    )


def _parse_strategies(raw: dict[str, Any] | None) -> dict[str, StrategyDef]:
    if not raw:
        return {}
    return {
        name: StrategyDef(name=name, module=item["module"])
        for name, item in raw.items()
    }


def _parse_indicators(raw: dict[str, Any] | None) -> dict[str, IndicatorDef]:
    if not raw:
        return {}
    return {
        name: IndicatorDef(name=name, module=item["module"])
        for name, item in raw.items()
    }


def load_config(path: str | Path = "conf/config.yaml") -> AppConfig:
    """从 YAML 文件加载配置，返回 AppConfig。"""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    ex_data = data.get("exchange", {})
    exchange = ExchangeConfig(
        api_key=ex_data.get("api_key", ""),
        api_secret=ex_data.get("api_secret", ""),
        mode=ex_data.get("mode", "ccxt"),
        name=ex_data.get("name", "binance"),
        proxy=ex_data.get("proxy", ""),
        sandbox=ex_data.get("sandbox", True),
    )

    strategies = _parse_strategies(data.get("strategies"))
    indicators = _parse_indicators(data.get("indicators"))

    channels: list[ChannelConfig] = []
    for symbol, sym_cfg in data.get("channel", {}).items():
        market = sym_cfg.get("market", "spot")
        allocation = sym_cfg.get("allocation", 0.0)
        for interval, int_cfg in sym_cfg.get("intervals", {}).items():
            channels.append(
                _parse_channel(symbol, market, allocation, interval, int_cfg)
            )

    return AppConfig(exchange=exchange, channels=channels,
                     strategies=strategies, indicators=indicators)
