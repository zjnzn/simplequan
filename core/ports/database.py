
from typing import Protocol, runtime_checkable

@runtime_checkable
class Database(Protocol):
    async def connect(self, db_path: str) -> None:
        """建立数据库连接。"""
        ...

    async def disconnect(self) -> None:
        """断开数据库连接。"""
        ...

    async def insert(self, table: str, data: dict) -> int:
        """插入一条记录，返回新行 ID。"""
        ...

    async def update(self, table: str, data: dict, where: str, params: tuple | None = None) -> int:
        """更新表中满足条件的记录，返回受影响行数。"""
        ...

    async def delete(self, table: str, where: str, params: tuple | None = None) -> int:
        """删除表中满足条件的记录，返回受影响行数。"""
        ...

    async def query(self, sql: str, params: tuple | None = None) -> list[dict]:
        """执行参数化查询，返回结果行列表。"""
        ...
