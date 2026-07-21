from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import numpy as np
import pandas as pd


@runtime_checkable
class Strategy(Protocol):
    """策略插件接口（无状态模板）。参数在调用时注入，不进构造函数。"""
    name: str
    version: str

    def required_indicators(self, params: dict) -> list[str]:
        """根据 params 返回该策略依赖的指标 key 列表。"""
        ...

    def route(self, df: pd.DataFrame, params: dict, gate_data: dict[str, Any] | None = None) -> np.ndarray:
        """输入完整 df，输出全量信号向量 (1=long, -1=short, 0=flat)。

        gate_data: 跨TF门控数据，由框架根据 ChannelConfig.gate 注入高TF最新状态。
        策略忽略未知 kwargs 即可保证向后兼容。
        """
        ...

    async def check_exit(self, row: dict[str, Any], pos: dict[str, Any],
                         ctx, params: dict) -> str | None:
        """持仓时每 bar 检查离场条件。返回离场原因或 None。
        pos: {"side": 1|-1, "entry_price": float, "best_price": float,
              "entry_bar": int, "bars_held": int, "partial_done": bool}
        """
        return None
