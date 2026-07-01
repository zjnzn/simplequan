import logging

from core.domain.command import Command, CommandType
from core.domain.event import Event, EventType
from core.ports.context import Context
from core.ports.handler import Handler

logger = logging.getLogger(__name__)


class RiskPostCheckHandler(Handler):
    """出站：下单前风控检查。通过 RiskPipeline 委托中间件链。"""

    handles_commands = frozenset({CommandType.CREATE_ORDER})

    def __init__(self, pipeline: RiskPipeline | None = None) -> None:
        self._pipeline = pipeline or RiskPipeline([])

    async def write(self, ctx: Context, command: Command) -> None:
        result = await self._pipeline.check(command, ctx)
        if result.passed:
            logger.debug("Post风控通过: %s", command.symbol)
            await ctx.write(command)
        else:
            logger.warning("Post风控拒绝: %s", result.reason)
