from collections import deque
from decimal import Decimal
from typing import Protocol, runtime_checkable

@runtime_checkable
class Indicator(Protocol):
    """指标计算器插件接口。

    实现示例：
        class MaCalculator:
            name = "ma"
            version = "1.0.0"
            output_keys = ["ma_5", "ma_20"]

            def compute(self, bars: deque) -> dict[str, Decimal]:
                ...
    """
    name: str
    version: str
    output_keys: list[str]

    def compute(self, bars: deque) -> dict[str, Decimal]:
        """输入 bar 序列，返回 {指标key: 值}。"""
        ...
