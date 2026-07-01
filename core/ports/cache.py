from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Cache(Protocol):
    async def get(self, key: str) -> Any | None:
        """获取缓存值，不存在则返回 None。"""
        ...

    async def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """设置缓存键值，ttl 为过期秒数，None 表示永不过期。"""
        ...

    async def delete(self, key: str) -> None:
        """删除指定缓存键。"""
        ...

    async def exists(self, key: str) -> bool:
        """判断缓存键是否存在。"""
        ...

    async def clear(self) -> None:
        """清空所有缓存。"""
        ...
