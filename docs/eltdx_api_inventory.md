# eltdx 3.3.0 接口清单与项目使用情况

> 本文梳理通达信新客户端 eltdx（commit `5fcfba4` 起替代 mootdx 0.11.7）对外提供的全部接口与工具，并标注本项目 `stock-market-service` 的实际使用情况，作为后续扩展取数能力的目录。
>
> 版本基线：`eltdx 3.3.0`，源码位于 `.venv/lib/python3.12/site-packages/eltdx/`。

## 1. 客户端形态

一个 `TdxClient` 连接对象下挂 16 个业务域，按 `client.<域>.<方法名>` 调用；另有 F10（7615 端口）、扩展行情（7727 端口）、财报文件、离线数据四块独立能力。

```python
from eltdx import TdxClient

client = TdxClient(host="110.41.147.114:7709", probe_hosts=False, timeout=8)
client.connect()
client.bars.get("600519", period="day", count=250, adjust="qfq")
client.minutes.today("000592")
client.close()
```

| 客户端参数 | 说明 |
|---|---|
| `host` / `hosts` | 单节点或多节点；`hosts` 走连接池与故障转移 |
| `probe_hosts` | 是否自动探测服务器（本项目显式关闭，改用自带 `TdxServerManager`） |
| `timeout` | 单次请求超时（秒） |
| `pool_size` / `server_count` / `connections_per_server` | 连接池规模与并发调度 |
| `connect()` / `close()` / `ping()` / `clear_cache()` | 生命周期方法 |

异常类型集中在 `eltdx.exceptions`，常见 `ResponseTimeoutError`（节点偶发超时，需多节点重试）。

## 2. 行情主站域（7709）

### 2.1 `client.bars` — K线/周期线

```python
get(code, *, period="day", start=0, count=800, adjust=None, anchor_date=None,
    kind=None, include_raw=False, all_pages=False, page_size=800,
    max_pages=200, batch_size=None, bar_time="start")
```

- **周期**：常用 `1m / 5m / 15m / 30m / 60m`、`day / week / month / quarter / year`，也支持 `13m` 这类任意分钟周期。
- **复权**：`none / qfq / hfq / fixed_qfq / fixed_hfq`；定点复权需配 `anchor_date`（跨多个除权日保持同一基准）。
- **`start`** 语义：从最新一根往前跳过的根数（按交易日取历史分钟线时靠它翻页）；单页上限 800 根。
- **`bar_time`**：`start`（通达信原始开始时间）或 `end`（右端点，与 Tushare/同花顺对齐），仅对分钟级周期生效。
- **批量**：`code` 传列表则按连接池并发，返回 `{标准代码: KlineSeries}`。
- **返回** `KlineSeries`：`period_name`、`adjust_mode`、`bars`（`KlineBar`）。

`KlineBar` 关键字段：

| 字段 | 含义 |
|---|---|
| `time` | K线时间 |
| `open/high/low/close` | 价格（元，随 `adjust` 复权） |
| `open_price_milli` 等 | 价格的千分整数表示 |
| `last_close_price_milli` | **该根对应的昨收**（qm 口径，窗口首根为 null） |
| `volume_lots` | 成交量（手） |
| `volume_wire_value` | **成交量（股）** = 手 × 100 |
| `volume_raw` / `amount` / `amount_raw` | 原始量、成交额（元）、原始成交额 |
| `up_count` / `down_count` | 上涨/下跌家数（指数类有效） |

### 2.2 `client.minutes` — 原生分时

| 方法 | 能力 |
|---|---|
| `today(code)` | 当日（或最近交易时段）分时，240 点 |
| `history(code, trading_date)` | 指定交易日历史分时（可回溯 ≥3 个月） |
| `recent(code, trading_date=None)` | 近期历史分时 |
| `aux(code, kind)` | 分时副图：`buy_sell_strength`（每分钟买卖委托数）、`volume_comparison`（昨量/今量/累计量） |
| `buy_sell_strength(code)` / `volume_comparison(code)` | 上述两种副图的独立入口 |
| `sparkline(code, selector=1, window=20)` | 小走势图 |

`MinutePoint` 字段：`time`、`price`、`volume`（单位 = **手**，与日K `volume_lots` 同口径）、`avg_price`（**当日分时服务器直给均价线**）。
`MinuteSeries` 额外带 `prev_close`（历史分时为当日实际昨收，当日分时为 null）。

### 2.3 `client.trades` — 逐笔成交

| 方法 | 能力 |
|---|---|
| `today` / `history` | 当日/历史成交明细（单页，`start`/`count` 分页，单页 1800 笔） |
| `all_today` / `all_history` | 自动翻页拉全量 |
| `today_batch` / `history_batch` / `all_*_batch` | 返回批量数组字段（`TradeBatch`），不构造逐笔对象，大吞吐场景用这个 |
| `opening_match_today` / `opening_match_history` | 09:25 正式撮合成交 |

### 2.4 `client.quotes` — 快照与盘口

| 方法 | 能力 |
|---|---|
| `get_snapshots(codes)` | 批量快照（现价、昨收、开高低、成交量额、内外盘、现手、开盘金额、五档） |
| `get_depth(codes)` | 五档盘口（0x0547） |
| `refresh(codes)` | 单次最多 100 只的增量刷新 |
| `list_by_category(category, sort_by, start, count)` | 分类行情（沪深A股/概念/行业等排序） |
| `legacy(codes)` | 旧版批量行情（0x053E） |
| `poll_push` / `drain_pushes` | **增量推送订阅**：长连接边推边取，避免轮询快照 |

`QuoteSnapshot` 字段（比本项目适配层映射的 7 个多得多）：`last_price`、`pre_close_price`、`open_price`、`high_price`、`low_price`、`total_hand`、`current_hand`、`amount`、`inside_dish`（内盘）、`outer_disc`（外盘）、`open_amount_yuan`、`buy_levels` / `sell_levels`（五档），以及属性 `change`、`change_pct`、`sum_buy_vol`、`sum_sell_vol`。

### 2.5 其他主站域

| 域 | 关键方法 | 能力 |
|---|---|---|
| `client.auctions` | `series(code, date)` | 集合竞价全过程快照序列（0x056a），当日/历史 |
| `client.codes` | `latest_stock_list` / `latest_st` / `latest_suspended` / `all_stocks` / `all_etfs` / `all_indices` / `count` / `list` | 代码表、ST 名单、**停牌名单**、ETF/指数清单 |
| `client.limits` | `special` / `scan_special` | 特殊品种涨跌停表（0x0452）。**实测全市场仅 1 条**，普通股票不在表内 |
| `client.corporate` | `capital_changes` / `adjustment_factors` / `finance_batch` | 股本变迁（权息/送转全量业务记录）、复权仿射系数（`scale + offset`）、财务基础批次 |
| `client.company_info` | `category` / `content` | 公司信息文本文件目录与正文（GBK 解码，0x02CF/0x02D0） |
| `client.resources` | `read` / `read_stats` / `block_meta` / `download_file` | 服务器文件读取、`zhb.zip` 统计文件解析（股本/短线指标的数据底座） |
| `client.session` | `handshake` / `heartbeat` / `ping` | 连接层握手与心跳 |
| `client.workdays` | `is_workday` / `range` / `next_workday` / `previous_workday` / `today` / `refresh` | **服务器交易日历** |
| `client.delisted_bars` | `get(...)` | 退市股日线（仅日线、仅不复权） |
| `client.money_flow` | `daily(code)` | 资金流向日数据（走独立连接池）：主力净额/占比、超大/大/中/小单买卖净额 |

### 2.6 `client.helpers` — 现成聚合报表

面向"直接出表"的一层，20+ 方法：

| 分类 | 方法 |
|---|---|
| 盘口/行情 | `full_quotes`（快照 + 五档合并）、`realtime_rank`（实时排行）、`market_stat`（全市场涨跌统计概览） |
| 板块/题材 | `board_quotes`、`board_member_quotes`、`stock_topics`、`topic_stocks`、`theme_strength_rank`、`stock_theme_strength_rank` |
| 涨停 | `limit_ladder`、`limit_up_down_list`、`limit_board_ladder` |
| 股本/指标 | `daily_share_capital`（每日总股本/流通/自由流通）、`shortline_indicators`（21 个短线指标）、`daily_price_limits`（按规则算指定日涨跌停） |
| 聚合 | `stock_profile_table`（行情+代码表+财务合一）、`auction_data`（竞价过程+撮合+快照）、`today_fund_flow`、`latest_stock_list` / `latest_st` / `latest_suspended` |

## 3. 非主站能力

| 模块 | 入口 | 能力 |
|---|---|---|
| F10（7615） | `client.f10` | 25+ 方法：公告/新闻/路演、公司概况、财务报表（资产负债/利润/现金流）、主营构成、分红融资、财务诊断、盈利预测、股东增减持、沪深股通持股、估值表、题材（`topic_ids` / `hot_topics` / `topic_compare`）、个股总评评分、市场/行业排名、增发获配明细、涨跌停名单，以及 `call(entry)` 直调 TQLEX |
| 扩展行情（7727） | `eltdx.ex.ExTdxClient` | 期货、港股、外股等扩展品种 |
| 财报文件 | `eltdx.financial` | 连接通达信"计算服务器"，按 `0x06B9` 下载并解析 `tdxfin` 财报包 |
| 离线数据 | `eltdx.offline` | 直接读本机通达信安装目录：日线/分钟线/扩展日线/板块/行业/`gbbq` 复权因子/历史财务，无需联网 |
| 本地复权 | `eltdx.equity` | 仅由股本变迁推导的本地复权系数 |

## 4. 客户端自带工具层

| 形态 | 入口 | 说明 |
|---|---|---|
| 内置 MCP Server | `eltdx.mcp`（`python -m eltdx`） | 24 个工具，统一 `eltdx_` 前缀 |
| HTTP 网关 | `eltdx.http_server` | JSON-RPC 风格 `call(method)` + WebSocket 订阅推送 |
| CLI | `eltdx.cli` | 命令行直接取数 |
| 协议文档 | `eltdx/docs/methods/` | 20+ 篇按 0x 指令（如 `7709-当日分时.md`、`7709-股本变迁GBBQ.md`）的字段说明 |

内置 24 个 MCP 工具：

```
eltdx_quote              eltdx_quote_depth       eltdx_kline             eltdx_capital_changes
eltdx_adjustment_factors eltdx_money_flow        eltdx_daily_price_limits eltdx_minute
eltdx_trades             eltdx_call_auction      eltdx_opening_match_today eltdx_opening_match_history
eltdx_auction_data       eltdx_stock_profile     eltdx_shortline_indicators eltdx_stock_topics
eltdx_topic_stocks       eltdx_limit_up_down_list eltdx_limit_board_ladder eltdx_company_profile
eltdx_hot_topics         eltdx_finance_report    eltdx_company_news       eltdx_docs_index
```

> 与本项目自建的 `stock-market-service` 功能重叠。本项目的增量价值在加工层：按交易日窗口翻页定位、自适应抽点、涨跌停判定与封板状态、均线、多节点探测重试与批量并发。

## 5. 相比 mootdx 0.11.7 的新增能力

mootdx 是对 pytdx 少数接口的薄封装（`bars` / `quotes` / `xdxr` / 财务），`to_data` 证明其 bars 列仅为 pytdx 原生 OHLCV，**没有昨收字段**。eltdx 新增：

1. **K线自带昨收与股数**：`last_close_price_milli`、`volume_wire_value`。
2. **服务器端复权四种模式**，含定点复权 `fixed_qfq` + `anchor_date`；本地不再需要除权乘数计算。
3. **原生分时三件套**（`today` / `history` / `recent`）+ 分时副图（买卖力道、量比）+ 小走势图——mootdx 完全没有。
4. **逐笔成交**（含 09:25 正式撮合）。
5. **五档盘口与增量推送订阅**。
6. **资金流向日数据**（主力/超大/大/中/小单净额与占比）。
7. **交易日历**（`workdays`）。
8. **退市股日线、代码表状态（ST/停牌）、公司信息文本**。
9. **F10 全家桶**（公告/财报/主营/分红/股东/估值/题材）。
10. **离线数据与财报包**（本地通达信落地文件，可脱离网络回测）。

## 6. 本项目当前使用情况

`stock-market-service` 只用到 3 个方法：`bars.get`、`quotes.get_snapshots`、`minutes.today` / `minutes.history`。

| 能力 | 状态 |
|---|---|
| 日K / 1分钟K（服务器前复权） | ✅ 已用 `bars.get(adjust="qfq")` |
| 昨收（`last_close_price_milli`） | ✅ 日K `pre_close` 与分钟线 `prev_close` |
| 股数（`volume_wire_value`） | ✅ 日K `shares` 字段 |
| 原生分时（价格 + 均价线 + 每分钟量） | ✅ `get_intraday_chart` 工具 |
| 快照 | ⚠️ 仅映射 7 个字段，未用五档/内外盘/现手 |
| 分时副图、逐笔成交、资金流、F10、helpers、workdays、codes 状态、五档盘口、定点复权 | ❌ 未使用 |

## 7. 后续可扩展项（按价值排序）

1. `quotes.get_depth` + `poll_push` → 给 `get_stock_quote` 加五档与封单强度（盯盘最实用）。
2. `money_flow.daily` → 新增 `get_money_flow` 工具（复盘涨跌归因）。
3. `helpers.limit_ladder` / `helpers.market_stat` → 新增盘面工具（涨停天梯、全市场涨跌统计）。
4. `workdays` → 替换自维护的 `trading_calendar`（减少节假日表维护成本）。
5. `trades.history` / `all_history_batch` → 新增分笔工具（主动买卖占比、大单净流入）。

## 8. 实测注意事项

- `limits.special` 不能当涨跌停来源：全市场仅 1 条（000010），普通股票必须自算。
- 均线 MA5/10/20 服务器始终不提供，必须自算。
- `minutes.history(...).prev_close` 是**当日原始口径**（如 601398 除权日给 8.60），与 `bars.get(adjust="qfq")` 的复权价不匹配（当天复权价 8.45/8.46）；昨收要取 K 线自带 `last_close`。
- `corporate.adjustment_factors()` 的本地仿射系数与服务端复权价存在约 `0.01~0.02` 元差异，官方文档亦明确说明，需要一致性时直接用服务端 `adjust`。
- 连接偶发 `ResponseTimeoutError`，需多节点轮询重试（可用节点：`110.41.147.114:7709`、`47.113.94.204:7709`、`124.70.176.52:7709`、`121.36.54.217:7709`、`119.147.212.81:7709`）。
