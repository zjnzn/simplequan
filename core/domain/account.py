"""Account —— 账号信息领域模型。

分为主账号和子账号：
  - MasterAccount: 交易所主账号，持有总余额和子账号列表
  - SubAccount: 子账号（策略/Channel），持有分配的余额和仓位信息
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Literal


@dataclass
class Position:
    """仓位信息（可变，OrderResult 直接修改）。"""
    side: Literal["BUY", "SELL", ""] = ""
    qty: Decimal = Decimal("0")
    avg_price: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")

    def update_unrealized_pnl(self, current_price: Decimal) -> None:
        """根据当前价格更新未实现盈亏。无仓位或价格无效时归零。"""
        if self.qty <= 0 or self.side == "" or current_price <= 0:
            self.unrealized_pnl = Decimal("0")
            return
        if self.side == "BUY":
            self.unrealized_pnl = (current_price - self.avg_price) * self.qty
        else:
            self.unrealized_pnl = (self.avg_price - current_price) * self.qty


@dataclass(frozen=True)
class Balance:
    """余额信息。"""
    total: Decimal = Decimal("0")
    free: Decimal = Decimal("0")
    used: Decimal = Decimal("0")
    currency: str = "USDT"


@dataclass(frozen=True)
class LeverageConfig:
    """杠杆配置。"""
    leverage: int = 1
    margin_mode: Literal["cross", "isolated"] = "cross"


@dataclass
class SubAccount:
    """子账号（Channel 维度，可变运行时状态）。

    每个 Channel 绑定一个子账号，持有分配的余额和独立的仓位追踪。
    OrderResult 成交后直接修改 position/daily_pnl。
    """
    account_id: str
    master_id: str
    symbol: str

    # 分配的余额
    allocated_balance: Decimal = Decimal("0")

    # 仓位追踪（可变）
    position: Position = field(default_factory=Position)

    # 日内盈亏
    daily_pnl: Decimal = Decimal("0")

    # 杠杆配置
    leverage_config: LeverageConfig = field(default_factory=LeverageConfig)

    # 占用保证金（开仓时增加，平仓时减少；用于防止超额开仓与强平判定）
    margin_used: Decimal = Decimal("0")

    # 上次 PnL 归零日期（ISO 格式，跨日自动归零）
    last_pnl_date: str = ""

    def maybe_reset_daily_pnl(self) -> None:
        """跨日自动归零 daily_pnl。由风控中间件在检查前调用。"""
        from datetime import date
        today = date.today().isoformat()
        if self.last_pnl_date and self.last_pnl_date != today:
            self.daily_pnl = Decimal("0")
        self.last_pnl_date = today

    def with_position(
        self,
        side: Literal["BUY", "SELL", ""] | None = None,
        qty: Decimal | None = None,
        avg_price: Decimal | None = None,
    ) -> SubAccount:
        """更新仓位（in-place 修改 position，返回 self 便于链式）。"""
        if side is not None:
            self.position.side = side
        if qty is not None:
            self.position.qty = qty
        if avg_price is not None:
            self.position.avg_price = avg_price
        return self

    def with_pnl(self, pnl: Decimal) -> SubAccount:
        """累加日内盈亏（in-place）。"""
        self.daily_pnl += pnl
        return self

    def with_leverage(self, leverage: int, margin_mode: str = "cross") -> SubAccount:
        """更新杠杆配置（in-place）。"""
        self.leverage_config = LeverageConfig(
            leverage=leverage,
            margin_mode=margin_mode,
        )
        return self


@dataclass(frozen=True)
class MasterAccount:
    """主账号（交易所账号）。

    持有总余额、按 symbol 索引的持仓与杠杆快照、以及 Channel 维度的子账号列表。
    """
    account_id: str

    # 余额
    balance: Balance = field(default_factory=Balance)

    # 按 symbol 索引的持仓（账号整体持仓快照）
    positions: dict[str, Position] = field(default_factory=dict)

    # 按 symbol 索引的杠杆配置
    leverages: dict[str, LeverageConfig] = field(default_factory=dict)

    # 子账号列表（Channel 维度，symbol@timeframe 一个，由 Bootstrap 创建时 add）
    sub_accounts: tuple[SubAccount, ...] = ()

    # 日内总盈亏（汇总所有子账号）
    daily_pnl: Decimal = Decimal("0")

    def get_position(self, symbol: str) -> Position:
        """获取某 symbol 的持仓，无则返回空 Position。"""
        return self.positions.get(symbol, Position())

    def get_leverage(self, symbol: str) -> LeverageConfig:
        """获取某 symbol 的杠杆配置，无则返回默认。"""
        return self.leverages.get(symbol, LeverageConfig())

    def get_sub_account(self, account_id: str) -> SubAccount | None:
        """获取子账号。"""
        for sub in self.sub_accounts:
            if sub.account_id == account_id:
                return sub
        return None

    def add_sub_account(self, sub: SubAccount) -> MasterAccount:
        """添加子账号。"""
        if self.get_sub_account(sub.account_id):
            return self
        return replace(self, sub_accounts=self.sub_accounts + (sub,))

    def remove_sub_account(self, account_id: str) -> MasterAccount:
        """移除子账号。"""
        return replace(self, sub_accounts=tuple(
            s for s in self.sub_accounts if s.account_id != account_id
        ))

    def with_balance(self, balance: Balance) -> MasterAccount:
        """更新余额。"""
        return replace(self, balance=balance)

    def with_positions(self, positions: dict[str, Position]) -> MasterAccount:
        """更新持仓快照。"""
        return replace(self, positions=positions)

    def with_leverages(self, leverages: dict[str, LeverageConfig]) -> MasterAccount:
        """更新杠杆配置。"""
        return replace(self, leverages=leverages)

    def with_daily_pnl(self, pnl: Decimal) -> MasterAccount:
        """更新日内总盈亏。"""
        return replace(self, daily_pnl=pnl)

    def update_sub_account(self, account_id: str, sub: SubAccount) -> MasterAccount:
        """更新子账号。"""
        return replace(self, sub_accounts=tuple(
            sub if s.account_id == account_id else s
            for s in self.sub_accounts
        ))
