from typing import Any, Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class Indicator(Protocol):
    """指标计算器插件接口（无状态模板）。

    实现示例：
        class MaCalculator:
            name = "ma"
            version = "1.0.0"

            def output_keys(self, params: dict) -> list[str]:
                return [f"ma_{p}" for p in params.get("periods", [5, 20])]

            def compute(self, df: pd.DataFrame, params: dict) -> dict[str, Any]:
                return {"ma_5": float(df["close"].rolling(5).mean().iloc[-1])}
    """
    name: str
    version: str

    def output_keys(self, params: dict) -> list[str]:
        """根据 params 返回产出的指标 key 列表。"""
        ...

    def compute(self, df: pd.DataFrame, params: dict) -> dict[str, Any]:
        """输入 DataFrame（列: timestamp/open/high/low/close/volume），返回 {指标key: 值}。"""
        ...
