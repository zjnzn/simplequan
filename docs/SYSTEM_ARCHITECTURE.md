# Quanquan 量化交易系统架构文档

> 版本: 1.0 | 更新: 2026-07-03

---

## 目录

1. [系统概述](#1-系统概述)
2. [架构总览](#2-架构总览)
3. [核心领域模型](#3-核心领域模型)
4. [端口层 (Ports)](#4-端口层-ports)
5. [适配器层 (Adapters)](#5-适配器层-adapters)
6. [Pipeline & Handler 链](#6-pipeline--handler-链)
7. [EventBus 事件总线](#7-eventbus-事件总线)
8. [交易所层](#8-交易所层)
9. [指标计算系统](#9-指标计算系统)
10. [策略系统](#10-策略系统)
11. [风控系统](#11-风控系统)
12. [监控系统](#12-监控系统)
13. [配置系统](#13-配置系统)
14. [启动流程](#14-启动流程)
15. [完整数据流](#15-完整数据流)
16. [目录结构](#16-目录结构)

---

## 1. 系统概述

Quanquan 是一个基于**六边形架构（Ports & Adapters）** 的加密货币量化交易系统。核心特点：

- **多币对多周期**: 支持多个 symbol@timeframe 独立运行
- **配置驱动**: 策略、指标、风控参数全部 YAML 声明式配置
- **Hot-reload 策略**: 策略/指标以插件形式注册，无需重启即可替换
- **双模式运行**: `simulated` 纯内存模拟 / `hybrid` 真实行情+虚拟撮合
- **实时监控**: 内置 FastAPI HTTP 服务 + 前端面板

### 设计原则

| 原则 | 体现 |
|------|------|
| **SOLID** | 端口隔离、单一职责 Handler、开闭原则策略插件 |
| **KISS** | 策略无状态、指标纯函数、配置扁平化 |
| **DRY** | `_helpers.py` 共享指标辅助函数、注册表模式复用 |
| **YAGNI** | 仅实现当前所需，无过度抽象 |

---

## 2. 架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│                         main.py (启动入口)                        │
│  config → EventBus → ExchangeConnector → Bootstrap → Monitor     │
└──────────────────────────────────────────────────────────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          ▼                       ▼                       ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│   Exchange 层    │   │   Pipeline 链   │   │   Monitor 层    │
│  (数据源/撮合)    │   │  (Handler 管道)  │   │  (HTTP 查询)    │
└─────────────────┘   └─────────────────┘   └─────────────────┘
          │                       │                       │
          └───────────────────────┼───────────────────────┘
                                  ▼
                        ┌─────────────────┐
                        │   EventBus      │
                        │ (发布/订阅总线)   │
                        └─────────────────┘
```

### 六边形架构分层

```
┌─────────────────────────────────────────────────────────────┐
│                     core/domain/  (领域模型)                  │
│  Signal, Bar(隐式), Order, Position, Account, RiskResult     │
├─────────────────────────────────────────────────────────────┤
│                     core/ports/  (端口接口)                   │
│  Pipeline, Handler, Context, ExchangePort, EventBus,         │
│  Strategy, Indicator, RiskMiddleware, Clock                  │
├─────────────────────────────────────────────────────────────┤
│                     app/  (适配器实现)                        │
│  handler/  pipline/  exchange/  strategy/  indicator/        │
│  middleware/  monitor/  channel/  eventbus/  bootstrap/      │
├─────────────────────────────────────────────────────────────┤
│                     conf/  (配置)                             │
│  config.yaml                                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 核心领域模型

所有领域模型位于 [core/domain/](core/domain/)，使用 `@dataclass` 定义。

### 3.1 事件与指令

**[Event](core/domain/event.py)** — 入站事件（交易所 → 应用）

```python
@dataclass(frozen=True)
class Event:
    type: EventType    # KLINE | ORDERBOOK | TRADE | ORDER_CREATED | ORDER_FILLED | ...
    symbol: str        # "BTC/USDT"
    payload: Any       # Bar / OHLCV dict / Order dict
```

**[Command](core/domain/command.py)** — 出站指令（应用 → 交易所）

```python
@dataclass(frozen=True)
class Command:
    type: CommandType  # CREATE_ORDER | CANCEL_ORDER
    symbol: str
    payload: dict      # {"side": "BUY", "amount": 0.01, ...}
```

**[Signal](core/domain/signal.py)** — 交易信号

```python
@dataclass
class Signal:
    value: float    # [-1, +1] 连续置信度，正=做多，负=做空，0=观望
    reason: str     # 信号原因标签

    # 派生属性
    direction: str  # "LONG" | "SHORT" | "HOLD"
    strength: float # abs(value) ∈ [0, 1]
```

### 3.2 账户模型

```
MasterAccount (主账号)
├── balance: Balance          # 总余额 (total/free/used)
├── positions: dict[str, Position]  # 按 symbol 索引
├── leverages: dict[str, LeverageConfig]
└── sub_accounts: tuple[SubAccount, ...]
       └── SubAccount (子账号 = Channel 维度)
           ├── account_id: str       # = channel_id (symbol@timeframe)
           ├── allocated_balance     # 分配的余额
           ├── position: Position    # 独立仓位追踪
           ├── daily_pnl: Decimal    # 日内累计盈亏
           └── leverage_config
```

**[Position](core/domain/account.py:15-21)** — 可变，被 OrderResult 直接修改

```python
@dataclass
class Position:
    side: Literal["BUY", "SELL", ""]
    qty: Decimal
    avg_price: Decimal
    unrealized_pnl: Decimal
```

### 3.3 订单模型

**[Order](core/domain/order.py)** — 不可变 dataclass，通过 `with_update()` 追加更新历史

```python
@dataclass(frozen=True)
class Order:
    order_id: str
    client_order_id: str
    pipeline_id: str          # 渠道标识
    symbol: str
    side: Literal["BUY", "SELL"]
    order_type: Literal["MARKET", "LIMIT"]
    qty: Decimal
    price: Decimal | None
    filled_qty: Decimal
    avg_price: Decimal
    state: OrderState         # SUBMITTED → FILLED / CANCELED / REJECTED
    updates: tuple[OrderUpdate, ...]  # 审计追踪
```

### 3.4 运行时市场状态

**[MarketState](core/domain/market.py)** — 每个 Channel 持有一个实例

```python
@dataclass
class MarketState:
    bars: dict[str, deque]                    # {interval: deque[Bar]}
    indicators: dict[str, dict[str, Decimal]] # {interval: {"rsi_14": 65.2}}
    current_signal: Signal | None             # 最新信号
```

### 3.5 风控结果

**[RiskResult](core/domain/risk.py)**

```python
@dataclass
class RiskResult:
    passed: bool
    reason: str = ""
```

---

## 4. 端口层 (Ports)

所有端口定义为 Protocol 类，位于 [core/ports/](core/ports/)。

| 端口 | 文件 | 职责 |
|------|------|------|
| `Pipeline` | [pipline.py](core/ports/pipline.py) | 双向链表，入站/出站事件传播 |
| `Handler` | [handler.py](core/ports/handler.py) | 管道处理器基类，声明式事件过滤 |
| `Context` | [context.py](core/ports/context.py) | 管道节点，持有 handler + prev/next 引用 |
| `Channel` | [channel.py](core/ports/channel.py) | 通道抽象，read/write/close |
| `ExchangePort` | [exchange.py](core/ports/exchange.py) | 交易所能力接口（行情/订单/账户） |
| `EventBus` | [eventbus.py](core/ports/eventbus.py) | 发布/订阅总线 |
| `Strategy` | [strategy.py](core/ports/strategy.py) | 策略插件接口 |
| `Indicator` | [indicator.py](core/ports/indicator.py) | 指标计算器插件接口 |
| `RiskMiddleware` | [middleware.py](core/ports/middleware.py) | 风控中间件接口 |

### Handler 声明式过滤

```python
class Handler:
    handles: frozenset = frozenset()          # 入站事件类型白名单，空=全部
    handles_commands: frozenset = frozenset()  # 出站指令类型白名单，空=全部
```

`ChannelHandlerContext` 在传播时自动跳过不匹配的 handler，无需显式 if-else。

---

## 5. 适配器层 (Adapters)

### 5.1 ExchangeConnector — EventBus 桥接层

[app/exchange/connector.py](app/exchange/connector.py)

**唯一知道 topic 格式和 EventType 映射的地方。** Channel 只消费不解析。

```
负责:
  1. 监听 request/* → 启动对应的 watch_* 循环
  2. 监听 command/* → 调用 exchange.create_order / cancel_order
  3. 监听 command/fetch_account → 拉取主账号信息
  4. 监听 command/fetch_symbol → 拉取市场信息
  5. 订单回报路由（order_id → channel_id 映射）
```

**Topic 协议:**

```
数据入站:  {market}/{feed}/{symbol}[@{param}]     spot/kline/BTC/USDT@1m
订单回报:  {market}/order/{symbol}/{channel_id}/{event}
错误通知:  {market}/error/{sym_compact}/{source}
订阅请求:  request/{market}/{symbol}/{feed}        request/spot/BTC/USDT/kline-1m
下单指令:  command/{market}/{symbol}/{cmd}/{channel_id}
取消订阅:  unsubscribe/{market}/{symbol}
```

### 5.2 ChannelPipeline — 双向链表实现

[app/pipline/pipline.py](app/pipline/pipline.py)

```
Head ⇄ DataParse ⇄ DataProcess ⇄ Signal ⇄ RiskPre ⇄ PositionCalc
  ⇄ RiskPost ⇄ OrderEncode ⇄ OrderAccepted ⇄ OrderResult ⇄ Tail

入站 (channel_read): Head → Tail 方向
出站 (write):        Tail → Head 方向
```

- **Head** (`_HeadHandler`): 入站入口，出站显式终端（发布到 EventBus）
- **Tail** (`_TailHandler`): 入站终点（丢弃），出站入口

### 5.3 ChannelHandlerContext — 双向链表节点

[app/context/context.py](app/context/context.py)

```python
class ChannelHandlerContext(Context):
    __slots__ = ("name", "handler", "pipeline", "channel", "prev", "next")

    # channel_read: 向 next 传播  (Head → Tail)
    # write:        向 prev 传播  (Tail → Head)
    # 自动跳过 handles/handles_commands 不匹配的 handler
```

### 5.4 SymbolChannel — 运行时通道

[app/channel/channel.py](app/channel/channel.py)

每个 `symbol@timeframe` 对应一个 `SymbolChannel` 实例：

```
SymbolChannel
├── id: str (UUID)
├── config: ChannelConfig
├── symbol: Symbol            # 市场信息（精度/限额/费率）
├── market: MarketState       # 运行时 K 线/指标/信号
├── sub_account: SubAccount   # Channel 维度子账号
├── cache: MemoryCache        # 订单等缓存
└── pipeline: ChannelPipeline # Handler 链
```

---

## 6. Pipeline & Handler 链

### 6.1 Handler 链全景

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  DataParse  │───▶│ DataProcess │───▶│   Signal    │───▶│  RiskPre    │
│  OHLCV→Bar  │    │ 指标计算     │    │ 策略调度     │    │ 信号过滤     │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
                                                                  │
                          ┌───────────────────────────────────────┘
                          ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ OrderResult │◀───│OrderAccepted│◀───│ OrderEncode │◀───│PositionCalc │
│ 成交/回滚    │    │ 乐观更新     │    │ 订单编码     │    │ 仓位计算     │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
                                                                  │
                                                    ┌─────────────┘
                                                    ▼
                                            ┌─────────────┐
                                            │  RiskPost   │
                                            │ 下单检查     │
                                            └─────────────┘
```

### 6.2 各 Handler 详解

#### DataParseHandler — OHLCV → Bar

[app/handler/data_parse.py](app/handler/data_parse.py)

```
入站: Event(KLINE, symbol, {timeframe, ohlcv: [[ts,o,h,l,c,v], ...]})
出站: Event(KLINE, symbol, Bar)

逻辑:
  1. _parse_all() 批量解析 ccxt OHLCV → Bar 列表
  2. 按 timestamp 去重（与 deque 中已有 bar 比较）
  3. 前 N-1 根直接注入 market.bars（绕过 pipeline，历史预热）
  4. 最后一根走完整 handler 链
```

#### DataProcessHandler — 指标计算

[app/handler/data_process.py](app/handler/data_process.py)

```
入站: Event(KLINE, symbol, Bar)
出站: Event(KLINE, symbol, Bar)  # 透传，结果写入 market.indicators

逻辑:
  1. bar 追加到 market.bars[interval]
  2. 遍历 channel.config.strategy.indicators
  3. 从 IndicatorRegistry 获取指标类 → 实例化（缓存）
  4. 调用 indicator.compute(bars, params) → 写入 market.indicators
```

实例缓存策略：按 `name:sorted_params` 作为 cache_key。

#### SignalHandler — 策略调度

[app/handler/signal.py](app/handler/signal.py)

```
入站: Event(KLINE, symbol, Bar)
出站: Event(KLINE, symbol, Signal)

逻辑:
  1. 从缓存获取策略实例（按 channel_id 缓存，保证状态跨 bar 持续）
  2. 调用 strategy.on_bar(bar, ctx, params)
  3. 返回 Signal(value∈[-1,1], reason)
  4. 写入 market.current_signal
```

#### RiskPreCheckHandler — 信号风控

[app/handler/risk_pre.py](app/handler/risk_pre.py)

```
入站: Event(KLINE, symbol, Signal)
出站: Event(KLINE, symbol, Signal)  [通过]  或 丢弃 [拒绝]

逻辑:
  1. HOLD 信号直接透传（不浪费风控检查）
  2. 委托 RiskPipeline.check(signal, ctx)
  3. 任一中间件拒绝 → 短路，不传播
```

默认 Pre 风控链：

```
SignalStrength(min_strength=0.03) → DailyLoss(500) → Drawdown(8%)
```

#### PositionCalcHandler — 仓位计算

[app/handler/position_calc.py](app/handler/position_calc.py)

**单一职责：只做数学计算，不做过滤决策。**

```
入站: Event(KLINE, symbol, Signal)
出站: Command(CREATE_ORDER, symbol, {side, amount, ...})

逻辑:
  1. Signal.value > 0 → 做多目标仓位
  2. Signal.value < 0 → 做空目标仓位
  3. target_qty = allocated_balance × allocation% × strength / price
  4. delta = target - current_position
  5. |delta| < 1e-6 → 无需下单
  6. 出站 CREATE_ORDER 指令
```

#### RiskPostCheckHandler — 下单风控

[app/handler/risk_post.py](app/handler/risk_post.py)

```
出站拦截: Command(CREATE_ORDER, ...) 
逻辑: 委托 RiskPipeline.check(command, ctx)
```

默认 Post 风控链：

```
AmountCheck → MaxLeverage(20) → PerOrderRatio(10%)
```

#### OrderEncodeHandler — 订单编码

[app/handler/order_encode.py](app/handler/order_encode.py)

```
出站: Command → 补充 type(默认MARKET) + client_order_id(UUID)
```

#### OrderAcceptedHandler — 乐观更新

[app/handler/order_accepted.py](app/handler/order_accepted.py)

```
入站: ORDER_CREATED 事件

核心机制：乐观更新 + 最终一致性

开仓:
  立即增加 pos.qty，用占位价加权 avg_price
  记录 pending{kind:"open", qty, placeholder}

平仓:
  立即减少 pos.qty，记录平仓前均价
  记录 pending{kind:"close", qty, avg_at_close, side_at_close}
```

#### OrderResultHandler — 成交修正/回滚

[app/handler/order_result.py](app/handler/order_result.py)

```
入站: ORDER_FILLED | ORDER_CANCELED | ORDER_REJECTED

FILLED:
  - 开仓: 用真实成交均价替换占位价，修正 avg_price
  - 平仓: 用真实成交价计算 PnL = (fill - avg_at_close) × qty × 方向
  - 部分成交: 先回滚未成交差额，再修正已成交部分

CANCELED / REJECTED:
  - 回滚乐观更新的持仓（撤回未成交 qty）
```

---

## 7. EventBus 事件总线

[app/eventbus/eventbus.py](app/eventbus/eventbus.py)

```
ChannelEventBus
├── _exact: dict[str, list[BusHandler]]     # 精确 topic → O(1) 查找
├── _patterns: dict[str, list[BusHandler]]  # 通配符 topic → fnmatch 遍历
├── on(topic_pattern, handler)              # 订阅
├── off(topic_pattern, handler)             # 取消订阅
└── emit(topic, payload)                    # 发布
```

**通配符支持**: `*` 匹配任意段，`?` 匹配单字符（fnmatch 风格）

**路由规则**:
- 精确 topic 走 `_exact` 索引 (O(1))
- 通配符 topic 走 `_patterns` fnmatch 遍历

---

## 8. 交易所层

### 8.1 ExchangePort 接口

[core/ports/exchange.py](core/ports/exchange.py)

定义交易所全部能力：行情订阅 (`watch_*`)、订单管理 (`create/cancel`)、账户查询 (`fetch_*`)。

### 8.2 SimulatedExchange — 模拟模式

[app/exchange/simulated.py](app/exchange/simulated.py)

- **纯内存**，不连网
- K 线逐根生成（close 每次 +0.5% 模拟上行趋势）
- 可配置 `fail_rate`（拒单概率）和 `partial_rate`（部分成交概率）
- 支持 `RealtimeClock`（真实间隔）和 `BacktestClock`（瞬时回放）

### 8.3 HybridExchange — 混合模式

[app/exchange/hybrid.py](app/exchange/hybrid.py)

```
HybridExchange
├── MarketSource       # 真实行情 (ccxt REST 轮询)
└── MatchingEngine     # 虚拟撮合 (内存)
```

**行情**: MarketSource REST 轮询（避免 WS 代理问题）
**订单/账户**: MatchingEngine 纯内存虚拟化

### 8.4 MarketSource — 真实行情

[app/exchange/market_source.py](app/exchange/market_source.py)

- 使用同步 `ccxt` 走 REST 轮询（避开 `ccxt.pro` 的 WS 代理不稳定问题）
- 首次拉取 `limit=500` 做历史预热，后续 `limit=2` 增量轮询
- 轮询间隔：K 线周期的 1/4，最低 2 秒
- 代理支持：通过 `ExchangeConfig.proxy` 配置

### 8.5 MatchingEngine — 虚拟撮合

[app/exchange/matching_engine.py](app/exchange/matching_engine.py)

- 市价单：即时以 `MarketSource.last_price` 成交
- 限价单：挂单等待行情触发（`check_limits` 由 `HybridExchange.watch_*` 驱动）
- 持仓/余额用加权平均法计算

---

## 9. 指标计算系统

### 9.1 架构

```
conf/config.yaml          IndicatorRegistry        IndicatorLoader
indicators:               name → class              importlib 加载
  ma: MaCalculator  ───▶  {"ma": MaCalculator}
  rsi: RsiCalculator      {"rsi": RsiCalculator}
  ...
```

**无状态模板模式**: 注册表缓存类对象（不实例化），handler 调用时注入 params。

### 9.2 计算器接口

[core/ports/indicator.py](core/ports/indicator.py)

```python
class Indicator(Protocol):
    name: str
    version: str

    def compute(self, bars: deque, params: dict) -> dict[str, Decimal]:
        """输入 bar 序列 + 参数，返回 {指标key: Decimal值}"""
```

### 9.3 通用辅助函数

[app/indicator/_helpers.py](app/indicator/_helpers.py)

| 函数 | 算法 | 对齐 |
|------|------|------|
| `sma(values, period)` | 滑动窗口简单平均 | pandas `rolling(min_periods=period)` |
| `ema(values, period)` | alpha=2/(period+1) | pandas `ewm(span=period, adjust=False)` |
| `rma(values, period)` | alpha=1/period (Wilder) | pandas `ewm(alpha=1/period, adjust=False)` |
| `highest(values, period)` | 滚动窗口最大值 | pandas `rolling(max)` |
| `lowest(values, period)` | 滚动窗口最小值 | pandas `rolling(min)` |
| `stdev(values, period)` | ddof=0 滚动标准差 | pandas `rolling(std, ddof=0)` |

NaN 处理：RMA/EMA 从第一个有效值初始化（不人工注入 NaN），SMA 窗口含 NaN 时输出 NaN 但出窗口后自动恢复。

### 9.4 已注册指标 (20个)

| 指标 | 类 | 文件 |
|------|-----|------|
| MA | `MaCalculator` | [app/indicator/ma.py](app/indicator/ma.py) |
| EMA | `EmaCalculator` | [app/indicator/ema.py](app/indicator/ema.py) |
| RSI | `RsiCalculator` | [app/indicator/rsi.py](app/indicator/rsi.py) |
| MACD | `MacdCalculator` | [app/indicator/macd.py](app/indicator/macd.py) |
| ADX | `AdxCalculator` | [app/indicator/adx.py](app/indicator/adx.py) |
| ATR | `AtrCalculator` | [app/indicator/atr.py](app/indicator/atr.py) |
| Bollinger | `BbCalculator` | [app/indicator/bb.py](app/indicator/bb.py) |
| CCI | `CciCalculator` | [app/indicator/cci.py](app/indicator/cci.py) |
| CMF | `CmfCalculator` | [app/indicator/cmf.py](app/indicator/cmf.py) |
| Donchian | `DcCalculator` | [app/indicator/dc.py](app/indicator/dc.py) |
| Ichimoku | `IchimokuCalculator` | [app/indicator/ichimoku.py](app/indicator/ichimoku.py) |
| Keltner | `KcCalculator` | [app/indicator/kc.py](app/indicator/kc.py) |
| OBV | `ObvCalculator` | [app/indicator/obv.py](app/indicator/obv.py) |
| PSAR | `PsarCalculator` | [app/indicator/psar.py](app/indicator/psar.py) |
| ROC | `RocCalculator` | [app/indicator/roc.py](app/indicator/roc.py) |
| Stochastic | `StochCalculator` | [app/indicator/stoch.py](app/indicator/stoch.py) |
| SuperTrend | `SupertrendCalculator` | [app/indicator/supertrend.py](app/indicator/supertrend.py) |
| VPT | `VptCalculator` | [app/indicator/vpt.py](app/indicator/vpt.py) |
| VWAP | `VwapCalculator` | [app/indicator/vwap.py](app/indicator/vwap.py) |
| Williams %R | `WilliamsRCalculator` | [app/indicator/williams.py](app/indicator/williams.py) |

---

## 10. 策略系统

### 10.1 策略接口

[core/ports/strategy.py](core/ports/strategy.py)

```python
class Strategy(Protocol):
    name: str
    version: str

    async def on_bar(self, bar, ctx, params: dict) -> Signal | None:
        """每根 bar 调用，返回连续置信度 Signal"""
```

### 10.2 信号模型 v3 — 连续置信度

所有策略输出 `Signal(value∈[-1,1], reason)`：

```
+1.0  = 极度看多
 0.0  = 完全观望
-1.0  = 极度看空

value > 0  → direction="LONG",  strength=|value|
value < 0  → direction="SHORT", strength=|value|
value = 0  → direction="HOLD",   strength=0
```

### 10.3 已注册策略 (7个)

| 策略 | 类 | 核心公式 | 版本 |
|------|-----|----------|------|
| MA Cross | `MaCrossStrategy` | `clamp((fast-slow)/(price×sensitivity), -1, 1)` | 3.0.0 |
| RSI+MACD | `RsiMacdStrategy` | `clamp(-(RSI-50)/50, -1, 1)` | 3.0.0 |
| Bollinger | `BollingerStrategy` | `clamp(-(close-mid)/(upper-mid), -1, 1)` | 3.0.0 |
| MACD Cross | `MacdCrossStrategy` | `clamp(histogram/(price×sensitivity), -1, 1)` | 2.0.0 |
| ADX Trend | `AdxTrendStrategy` | `sign×clamp(ADX/50)×clamp(|DI_diff|/50)` | 2.0.0 |
| Stochastic | `StochStrategy` | `clamp(-(K-50)/50, -1, 1)` | 2.0.0 |
| SuperTrend | `SupertrendStrategy` | `dir×clamp(|price-ST|/(price×sensitivity), -1, 1)` | 2.0.0 |

所有策略**完全无状态** — 不存储 `_prev_*` 变量，从第一根 bar 即可输出信号。

### 10.4 策略与指标的关系

策略通过 `ctx.channel.market.indicators[interval]` 读取已计算好的指标值。DataProcessHandler 先于 SignalHandler 执行，保证指标数据就绪。

---

## 11. 风控系统

### 11.1 RiskPipeline — 责任链

[app/pipline/risk.py](app/pipline/risk.py)

```python
class RiskPipeline:
    async def check(payload, ctx) -> RiskResult:
        for mw in middlewares:
            result = await mw.check(payload, ctx)
            if not result.passed:  # 短路
                return result
        return RiskResult.approve()
```

**异常放行策略**: 中间件抛异常时记录日志并继续（容错优先）。

### 11.2 Pre 风控链（信号阶段）

在 [main.py](main.py:34-40) 组装：

```
SignalStrengthMiddleware(min_strength=0.03)
  → |signal.value| < 0.03 → 拒绝，不计算仓位

DailyLossMiddleware(daily_loss_limit=500)
  → sub.daily_pnl ≤ -500 → 拒绝

DrawdownMiddleware(max_drawdown=0.08)
  → 回撤超 8% → 拒绝
```

### 11.3 Post 风控链（下单阶段）

在 [main.py](main.py:43-49) 组装：

```
AmountCheckMiddleware()
  → 数量低于最小交易量 → 拒绝

MaxLeverageMiddleware(max_leverage=20)
  → 杠杆超限 → 拒绝

PerOrderRatioMiddleware(max_per_order_ratio=0.1)
  → 单笔超 10% 余额 → 拒绝
```

### 11.4 中间件接口

[core/ports/middleware.py](core/ports/middleware.py)

```python
class RiskMiddleware(Protocol):
    name: str
    async def check(self, payload, ctx) -> RiskResult: ...
```

---

## 12. 监控系统

### 12.1 架构

```
Monitor
├── Collector           # 订阅 bus 被动采集
│   ├── _on_kline()    # K线→全量同步 bars + 快照指标/信号
│   ├── _on_order()    # 订单回报→存储历史
│   └── _on_master()   # 主账号更新
├── Server (FastAPI)    # HTTP API
│   ├── GET /          # 总览 JSON
│   ├── GET /ui        # 前端监控面板
│   ├── GET /channels  # Channel 列表
│   ├── GET /channels/{cid}         # 单 Channel 详情
│   ├── GET /channels/{cid}/klines  # K线历史
│   ├── GET /channels/{cid}/indicators  # 指标历史
│   ├── GET /channels/{cid}/signals     # 信号历史
│   ├── GET /channels/{cid}/orders      # 订单历史
│   └── GET /master    # 主账号详情
└── ChannelRecord       # 有界 deque(maxlen=500) × 4 序列
```

默认监听端口: **8080**

---

## 13. 配置系统

### 13.1 配置结构

[conf/config.yaml](conf/config.yaml)

```yaml
# 策略/指标注册表（类级别）
strategies:
  ma_cross_over:
    module: app.strategy.ma_cross.MaCrossStrategy

indicators:
  ma:
    module: app.indicator.ma.MaCalculator

# 交易所连接
exchange:
  mode: hybrid            # simulated | hybrid
  name: binance
  proxy: "http://127.0.0.1:7897"

# 通道配置
channel:
  BTC/USDT:
    market: futures
    allocation: 0.3       # 30% 资金分配
    intervals:
      1m:
        strategy:
          name: ma_cross_over
          params: { fast: 5, slow: 20 }
          indicators:
            - name: ma
              params: { periods: [5, 20] }
        risk_pre:  { daily_loss_limit: 500, max_drawdown: 0.08 }
        risk_post: { max_per_order_ratio: 0.1, max_leverage: 20 }
```

### 13.2 当前通道配置

| Symbol | 周期 | 策略 | 分配 | 风控 |
|--------|------|------|------|------|
| BTC/USDT | 1m | MA Cross (5,20) | 30% | 日亏500/回撤8% |
| BTC/USDT | 5m | MACD Cross (12,26,9) | 30% | 日亏500/回撤8% |
| BTC/USDT | 1h | ADX Trend (14) | 30% | 日亏800/回撤10% |
| ETH/USDT | 5m | RSI+MACD (14) | 30% | 日亏500/回撤8% |
| ETH/USDT | 15m | Stochastic (14,3) | 30% | 日亏300/回撤5% |
| BNB/USDT | 5m | Bollinger (20,2) | 20% | 日亏500/回撤8% |
| BNB/USDT | 1h | SuperTrend (10,3) | 20% | 日亏400/回撤6% |

---

## 14. 启动流程

[main.py](main.py:76-133)

```
Phase 1: 初始化
  ├── load_config()                    # YAML → AppConfig
  ├── ChannelEventBus()                # 创建总线
  ├── HybridExchange / SimulatedExchange
  ├── ExchangeConnector(exchange, bus) # 桥接层
  └── 加载策略/指标到注册表

Phase 2: 拉取账户 & 市场信息
  ├── bus.emit("command/fetch_account")  → MasterAccount
  ├── bus.emit("command/fetch_symbol") × N → Symbol
  │   └── Bootstrap._on_symbol()
  │       └── on_accept(Symbol, ChannelConfig)
  │           ├── 创建 SubAccount（分配余额）
  │           ├── 创建 SymbolChannel
  │           ├── 创建 ChannelPipeline
  │           ├── ChannelInitializer.init_channel()
  │           │   → DataParse → DataProcess → Signal → RiskPre
  │           │   → PositionCalc → RiskPost → OrderEncode
  │           │   → OrderAccepted → OrderResult
  │           └── ch.read("kline", interval)  ← 触发 connector 开始拉数据

Phase 3: 监控 & 事件循环
  ├── Monitor.start()                  # HTTP 服务 + 采集订阅
  └── asyncio.Event().wait()           # 永久运行
```

**Bootstrap 三步构造**（解决 pipeline 循环依赖）：

1. 先建 `SymbolChannel(pipeline=None)` — 占位
2. 再建 `ChannelPipeline(channel)` — 绑定 channel
3. 回填 `ch.pipeline = pipeline`

---

## 15. 完整数据流

```
┌──────────────────────────────────────────────────────────────────────┐
│                          交易所 (ccxt / 模拟)                         │
│                    watch_ohlcv() → [[ts,o,h,l,c,v], ...]             │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ OHLCV 数据
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  ExchangeConnector._kline_loop()                                     │
│  包装为 Event(KLINE, symbol, {timeframe, ohlcv})                     │
│  发布到 bus topic: {market}/kline/{symbol}@{interval}               │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ EventBus.emit()
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  SymbolChannel listener                                              │
│  接收 Event → pipeline.fire_channel_read(event)                      │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ Head → Tail
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  [1] DataParseHandler                                                │
│  ccxt OHLCV → Bar dataclass                                         │
│  历史 bar 直接注入 market.bars（绕过 pipeline）                        │
│  最新 bar → fire_channel_read                                        │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  [2] DataProcessHandler                                              │
│  bar → market.bars[interval].append(bar)                             │
│  遍历 strategy.indicators → IndicatorRegistry.get() → compute()     │
│  结果写入 market.indicators[interval]                                │
│  透传 bar 到下一个 handler                                            │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  [3] SignalHandler                                                   │
│  从 market.indicators 读指标值                                        │
│  调用 strategy.on_bar(bar, ctx, params)                              │
│  返回 Signal(value∈[-1,1], reason)                                   │
│  写入 market.current_signal                                          │
│  fire_channel_read(Event(KLINE, symbol, signal))                     │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  [4] RiskPreCheckHandler                                             │
│  HOLD → 透传                                                         │
│  LONG/SHORT → RiskPipeline.check(signal, ctx)                       │
│    ├── SignalStrengthMiddleware: |value| < 0.03 → REJECT            │
│    ├── DailyLossMiddleware: daily_pnl ≤ -500 → REJECT               │
│    └── DrawdownMiddleware: 回撤超限 → REJECT                         │
│  拒绝: 丢弃事件（短路）                                               │
│  通过: fire_channel_read 继续                                        │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  [5] PositionCalcHandler                                             │
│  纯计算:                                                             │
│    target = allocated × allocation% × |signal| / price               │
│    delta = target - current_position                                 │
│    |delta| < 1e-6 → 跳过                                             │
│  出站: Command(CREATE_ORDER, symbol, {side, amount, ...})            │
│  通过 pipeline.write(command) 出站                                    │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ Tail → Head (出站)
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  [6] RiskPostCheckHandler                                            │
│  RiskPipeline.check(command, ctx)                                    │
│    ├── AmountCheckMiddleware                                         │
│    ├── MaxLeverageMiddleware                                         │
│    └── PerOrderRatioMiddleware                                       │
│  拒绝: 丢弃指令                                                       │
│  通过: ctx.write(command) 继续                                        │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  [7] OrderEncodeHandler                                              │
│  补充 type(MARKET) + client_order_id(UUID)                           │
│  ctx.write(new_cmd)                                                  │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Head Handler (终端)                                                 │
│  调用 channel.write(command)                                         │
│  → bus.emit("command/{market}/{symbol}/create_order/{channel_id}")  │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  ExchangeConnector._on_command()                                     │
│  → exchange.create_order(symbol, type, side, amount)                │
│  → ORDER_CREATED 回报                                               │
│  → bus.emit(".../{channel_id}/created", event)                      │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
        ┌──────────────────┐      ┌──────────────────┐
        │ [8] OrderAccepted │      │ [9] OrderResult   │
        │ 乐观更新持仓       │      │ FILLED: 均价修正   │
        │ 记录 pending      │      │         PnL 计算  │
        │                   │      │ CANCELED: 回滚    │
        └──────────────────┘      └──────────────────┘
```

---

## 16. 目录结构

```
quanquan/
├── main.py                          # 启动入口
├── conf/
│   └── config.yaml                  # 策略/通道/风控配置
├── core/
│   ├── domain/                      # 领域模型
│   │   ├── account.py               # MasterAccount, SubAccount, Position
│   │   ├── command.py               # Command, CommandType
│   │   ├── config.py                # AppConfig, ChannelConfig (YAML→dataclass)
│   │   ├── event.py                 # Event, EventType
│   │   ├── market.py                # MarketState (运行时状态)
│   │   ├── order.py                 # Order, OrderState, OrderUpdate
│   │   ├── risk.py                  # RiskResult
│   │   ├── signal.py                # Signal [-1,+1]
│   │   └── symbol.py                # Symbol (市场信息)
│   └── ports/                       # 端口接口 (Protocol)
│       ├── channel.py               # Channel 抽象
│       ├── clock.py                 # Clock 接口
│       ├── context.py               # Context 节点
│       ├── eventbus.py              # EventBus 接口
│       ├── exchange.py              # ExchangePort 接口
│       ├── handler.py               # Handler 基类
│       ├── indicator.py             # Indicator 插件接口
│       ├── middleware.py            # RiskMiddleware 接口
│       ├── pipline.py               # Pipeline 接口
│       └── strategy.py              # Strategy 插件接口
├── app/
│   ├── bootstrap.py                 # 启动器 (Netty 风格)
│   ├── cache/
│   │   └── memory.py                # MemoryCache (TTL 支持)
│   ├── channel/
│   │   └── channel.py               # SymbolChannel 实现
│   ├── clock/
│   │   └── realtime.py              # RealtimeClock
│   ├── context/
│   │   └── context.py               # ChannelHandlerContext (双向链表节点)
│   ├── eventbus/
│   │   └── eventbus.py              # ChannelEventBus (通配符支持)
│   ├── exchange/
│   │   ├── connector.py             # ExchangeConnector (Bus 桥接)
│   │   ├── hybrid.py                # HybridExchange (真实行情+虚拟撮合)
│   │   ├── market_source.py         # MarketSource (ccxt REST 轮询)
│   │   ├── matching_engine.py       # MatchingEngine (虚拟撮合)
│   │   └── simulated.py             # SimulatedExchange (纯内存)
│   ├── handler/
│   │   ├── data_parse.py            # [1] OHLCV → Bar
│   │   ├── data_process.py          # [2] 指标计算
│   │   ├── signal.py                # [3] 策略调度
│   │   ├── risk_pre.py              # [4] Pre 风控
│   │   ├── position_calc.py         # [5] 仓位计算（纯）
│   │   ├── risk_post.py             # [6] Post 风控
│   │   ├── order_encode.py          # [7] 订单编码
│   │   ├── order_accepted.py        # [8] 乐观更新
│   │   └── order_result.py          # [9] 成交修正/回滚
│   ├── indicator/
│   │   ├── _helpers.py              # 纯函数: sma, ema, rma, stdev, highest, lowest
│   │   ├── registry.py              # IndicatorRegistry + IndicatorLoader
│   │   ├── adx.py, atr.py, bb.py, cci.py, cmf.py, dc.py
│   │   ├── ema.py, ichimoku.py, kc.py, ma.py, macd.py
│   │   ├── obv.py, psar.py, roc.py, rsi.py, stoch.py
│   │   ├── supertrend.py, vpt.py, vwap.py, williams.py
│   ├── middleware/
│   │   ├── signal_strength.py       # 弱信号过滤 (|signal| < 0.03)
│   │   ├── daily_loss.py            # 日亏损限额
│   │   ├── drawdown.py              # 最大回撤
│   │   ├── amount_check.py          # 最小数量检查
│   │   ├── max_leverage.py          # 最大杠杆
│   │   └── per_order_ratio.py       # 单笔比例限制
│   ├── monitor/
│   │   ├── __init__.py
│   │   ├── collector.py             # 被动采集器
│   │   ├── monitor.py               # Monitor 主体
│   │   ├── server.py                # FastAPI HTTP 服务
│   │   ├── store.py                 # ChannelRecord (有界 deque)
│   │   └── templates/
│   │       └── index.html           # 前端监控面板
│   ├── pipline/
│   │   ├── pipline.py               # ChannelPipeline (双向链表)
│   │   └── risk.py                  # RiskPipeline (责任链)
│   └── strategy/
│       ├── registry.py              # StrategyRegistry + StrategyLoader
│       ├── adx_trend.py             # ADX 趋势策略
│       ├── bollinger.py             # 布林带策略
│       ├── ma_cross.py              # 均线交叉策略
│       ├── macd_cross.py            # MACD 策略
│       ├── rsi_macd.py              # RSI 策略
│       ├── stoch.py                 # 随机指标策略
│       └── supertrend.py            # 超级趋势策略
└── docs/
    └── SYSTEM_ARCHITECTURE.md       # 本文档
```

---

## 附录: 关键设计决策

### A. 为什么策略输出连续值而不是离散信号？

离散事件（BUY/SELL/NEUTRAL）在阈值边界处容易频繁翻转。连续置信度 `[-1,1]` 自然表达"看多/看空程度"，仓位计算按 `position_pct × |signal|` 平滑映射，弱信号自然对应小仓位或零仓位。

### B. 为什么 PositionCalc 不做过滤？

单一职责原则。仓位计算只做数学：`signal_value → target_qty → delta → order`。所有"是否应该交易"的决策交给 Risk 层。这样职责清晰、可测试、可组合。

### C. 为什么订单采用乐观更新？

交易系统要求低延迟。下单即更新持仓（乐观），成交回报时修正均价/算PnL（最终一致）。失败时回滚。避免"等成交回报再更新"造成的状态滞后。

### D. 为什么用 REST 轮询而非 WebSocket？

HTTP 代理对 WS CONNECT 转发不稳定。REST 轮询通路稳定，首次 `limit=500` 预热 + 后续 `limit=2` 增量的策略在实际使用中延迟可接受。

### E. 为什么 indicator/strategy 类不在构造时注入参数？

参数由 channel 配置决定，同一个策略类可能在不同 channel 以不同参数运行。类对象全局共享（无状态模板），handler 调用时注入 params。默认值由 `params.get(k, 默认)` 兜底。
