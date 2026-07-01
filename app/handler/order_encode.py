import logging
import uuid

from core.domain.event import Event, EventType
from core.ports.context import Context
from core.ports.handler import Handler
from core.domain.command import Command, CommandType
from core.ports.context import Context


logger = logging.getLogger(__name__)


class OrderEncodeHandler(Handler):
    """出站：将 CREATE_ORDER 指令编码为交易所可识别的格式。"""

    handles_commands = frozenset({CommandType.CREATE_ORDER})

    def __init__(self, order_type: str = "MARKET"):
        self._order_type = order_type

    async def write(self, ctx: Context, command: Command) -> None:
        # 创建新 payload dict（不 mutation 原对象）
        new_payload = {**command.payload, "type": self._order_type}
        new_payload.setdefault("client_order_id", str(uuid.uuid4()))
        new_cmd = Command(command.type, command.symbol, new_payload)
        logger.info("订单编码: %s 类型=%s 数量=%.6f 方向=%s", command.symbol, self._order_type, new_payload.get("amount", 0), new_payload.get("side", ""))
        await ctx.write(new_cmd)
