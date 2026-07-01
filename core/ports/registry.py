"""Registry —— 注册表端口。

管理插件的注册、检索和生命周期。
"""
from __future__ import annotations

from typing import Any, Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class Registry(Protocol[T]):
    """注册表端口。"""

    def register(self, plugin: T) -> None:
        """注册插件。"""
        ...

    def get(self, name: str) -> T:
        """获取插件，不存在时抛出 KeyError。"""
        ...

    def all(self) -> list[T]:
        """获取所有已注册插件。"""
        ...

    def has(self, name: str) -> bool:
        """检查插件是否已注册。"""
        ...

    def __len__(self) -> int:
        """返回已注册插件数量。"""
        ...
