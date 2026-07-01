import yaml
from dataclasses import dataclass, field


@dataclass
class IntervalConfig:
    """三级：per-interval 配置。

    每个 timeframe 可以有独立的策略和风控参数。
    缺省时使用 Handler 的 _DEFAULTS。
    """
    strategy: str = "ma_cross_over"
    risk_pre: dict = field(default_factory=dict)
    risk_post: dict = field(default_factory=dict)


@dataclass
class SymbolConfig:
    """一级 + 二级：symbol 级配置 + interval 映射。

    symbol 作为字典 key（YAML 中的顶级键），不需要 id 字段。
    allocation 是 symbol 级别总资金比例，按 interval 数量均分。
    """
    market: str = "spot"
    allocation: float = 0.3
    intervals: dict[str, IntervalConfig] = field(default_factory=dict)


@dataclass
class MasterConfig:
    global_daily_loss_limit: float = 2500.0
    api_key: str = ""
    api_secret: str = ""
    listen_key: str = ""
    num_loops: int = 1


@dataclass
class Config:
    master: MasterConfig = field(default_factory=MasterConfig)
    pipelines: dict[str, SymbolConfig] = field(default_factory=dict)
    strategies: list[dict] = field(default_factory=list)
    indicators: list[dict] = field(default_factory=list)
    risk_pre: list[dict] = field(default_factory=list)
    risk_post: list[dict] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        with open(path) as f:
            data = yaml.safe_load(f)
        master = MasterConfig(**data.get("master", {}))
        pipelines = {}
        for symbol, sym_data in data.get("pipelines", {}).items():
            intervals = {}
            for iv_name, iv_data in sym_data.get("intervals", {}).items():
                intervals[iv_name] = IntervalConfig(**iv_data)
            pipelines[symbol] = SymbolConfig(
                market=sym_data.get("market", "spot"),
                allocation=sym_data.get("allocation", 0.3),
                intervals=intervals,
            )
        strategies = data.get("strategies", [])
        indicators = data.get("indicators", [])
        risk_pre = data.get("risk_pre", [])
        risk_post = data.get("risk_post", [])
        return cls(master=master, pipelines=pipelines,
                   strategies=strategies, indicators=indicators,
                   risk_pre=risk_pre, risk_post=risk_post)
