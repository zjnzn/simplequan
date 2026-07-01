from dataclasses import dataclass, field
from enum import Enum

class CommandType(str, Enum):
    CREATE_ORDER = "create_order"
    CANCEL_ORDER = "cancel_order"


@dataclass(frozen=True)
class Command:
    """出站指令：应用 -> 交易所方向流动的指令。容器不可变，payload dict 仍可 mutate（Step 3 后将改为创建新对象）。"""
    type: CommandType
    symbol: str
    payload: dict = field(default_factory=dict, hash=False)
