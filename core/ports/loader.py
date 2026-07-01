"""Loader —— 加载器端口。

从模块路径或文件路径动态加载插件。
"""
from __future__ import annotations

from typing import Any, Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class Loader(Protocol[T]):
    """加载器端口。"""

    def load_module(self, dotted_path: str, params: dict[str, Any] | None = None) -> T:
        """从 Python 模块路径加载并实例化插件。

        dotted_path: "app.indicators.ma.MaCalculator"
        params: 传给构造函数的关键字参数
        """
        ...

    def load_file(self, spec: str, params: dict[str, Any] | None = None) -> T:
        """从文件路径加载插件。

        spec: "/path/to/plugin.py::ClassName"
        """
        ...

    def load_all(self, configs: list[dict[str, Any]]) -> None:
        """从配置列表批量加载插件。"""
        ...
