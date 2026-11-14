# A股行情数据MCP服务 - 架构文档

> 最后更新：2026-11-14（对应 commit `2ec9a3d`：eltdx 新增字段替代本地自算 + 修复分钟线复权口径）

## 1. 概述

A股行情数据MCP服务是基于 eltdx（通达信数据接口）的 Model Context Protocol 服务，提供 A 股行情取数与加工能力。

### 核心功能

| 功能 | 说明 |
|------|------|
| 1分钟K线数据 | 单只/批量按交易日取数，服务器端前复权，支持自适应抽点压缩上下文 |
| 日K线数据 | 服务器端前复权，含 5/10/20 日均线、涨跌停、服务器昨收、成交量（手/股） |
| 分时走势 | 价格曲线 + 服务器直给均价线 + 每分钟成交量，当日与历史均可 |
| 实时行情 | 快照（现价、昨收、涨跌幅、开高低、成交量额） |
| 复权口径 | 日K与分钟K统一由服务器 `adjust="qfq"` 返回，跨周期口径一致 |

### 技术栈

- **Python**: 3.11+（实际运行 3.12）
- **MCP 框架**: `mcp[cli]`（FastMCP），`src/mcp_servers/base.py` 封装
- **数据源**: eltdx 3.3.0（通达信行情主站 7709）
- **数据处理**: pandas
- **交易日历**: `exchange_calendars` 的 XSHG（经 star_stocks 传递依赖，缺失时降级为周末判断）

## 2. 项目结构

```
src/mcp_servers/
├── __init__.py
├── base.py                       # BaseMCPServer：FastMCP 实例、工具/资源注册、_tool 装饰器
└── stock_market/
    ├── __init__.py
    ├── main.py                   # 启动脚本（stdio 传输）
    ├── service.py                # MCP 服务定义：5 个工具 + 服务信息资源
    ├── data_fetcher.py           # 数据获取核心：EltdxQuotes 适配层 + StockDataFetcher
    ├── server_manager.py         # TdxServerManager：节点缓存/并发探测/故障切换
    ├── trading_calendar.py       # 交易日历（latest_trading_day / resolve_session / trading_days_after）
    └── stock_list.json           # 股票名称→代码映射（5320 条，用于 stock_name 解析）
```

## 3. 核心模块

### 3.1 BaseMCPServer（`base.py`）

MCP 服务器基类，提供 FastMCP 实例管理、`_tool` 注册装饰器（统一 `structured_output=False`）、资源注册与 `run(transport)` 启动。

### 3.2 EltdxQuotes（`data_fetcher.py`）

`TdxClient` 的 mootdx 兼容适配层，抹平列名差异，向上层暴露 DataFrame：

| 方法 | 说明 |
|------|------|
| `factory(server=(host, port), timeout)` | 构造并连接客户端（`probe_hosts=False`，节点由 `TdxServerManager` 决定） |
| `bars(symbol, frequency, offset, start)` | `frequency=9`→日K、`7`→1分钟K；两者均 `adjust="qfq"`；**必须透传 `start`**（按交易日翻页依赖） |
| `quotes(symbol)` | 快照单行 DataFrame（code/price/last_close/open/high/low/vol/amount） |
| `intraday(symbol, trading_date=None)` | 原生分时：有日期走 `minutes.history`，否则 `minutes.today`，返回 `MinuteSeries` |
| `close()` | 关闭连接 |

`bars()` 返回列：`datetime / open / high / low / close / vol(手) / amount / last_close(元) / shares(股)`。

- `last_close` ← `KlineBar.last_close_price_milli / 1000`（窗口首根为 null）
- `shares` ← `KlineBar.volume_wire_value`（= `volume_lots × 100`）

### 3.3 StockDataFetcher（`data_fetcher.py`）

数据获取核心类：

```
StockDataFetcher
├── _get_client()                # 获取/创建 EltdxQuotes（走服务器管理器或固定节点）
├── _execute_with_retry()        # 失败切节点重试（MAX_RETRY_COUNT=3）
├── _get_daily()                 # 日K（qfq，含 last_close/shares），TTL 缓存
├── _get_prev_close()            # 昨收：日K last_close，缺失退回前一根 close
├── _normalize_target_day()      # 交易日解析/校验（未来日期、非交易日直接报错）
├── _resolve_minute_window()     # 按交易日定位 240 根分钟线（start 估算 + 窗口挪动重试）
├── get_minute_data()            # 单只分钟K（含自适应抽点）
├── _fetch_minute_payload()      # 分钟K payload 组装（异常向外抛，供批量区分是否重试）
├── get_minute_data_batch()      # 批量分钟K（多线程 + 独立节点）
├── get_daily_kline()            # 日K + 均线 + 涨跌停 + shares
├── get_intraday_chart()         # 分时（价格 + 均价线 + 每分钟量）
├── _fetch_intraday_payload()    # 分时 payload 组装
├── _fetch_intraday_series()     # latest→today，否则 history
├── get_realtime_quote()         # 实时行情
├── extract_adaptive_kline()     # 自适应抽点（见第 9 节）
├── _finalize_output_fields()    # 输出字段裁剪（datetime→time、删 amount 等）
├── resolve_stock_code()         # code / name 二选一解析
└── _get_limit_ratio() / _calc_limit_up_price() / _is_at_limit_up() / _is_at_limit_down()
```

### 3.4 StockMarketService（`service.py`）

MCP 服务定义类：`register_tools()`（5 个工具）、`register_resources()`（`stock://service/info`）、`run()`。所有工具均 `structured_output=False` + `json.dumps(ensure_ascii=False)` 紧凑单份返回。

### 3.5 TdxServerManager（`server_manager.py` + `trading_calendar.py`）

- 节点来源：优先 star_stocks 的 `tdx_servers.json` 缓存（实测 43 台），缺失时并发探测。
- 探测参数：`probe_symbol=600519`、`probe_count=5`、`connect_timeout=4s`、`total_timeout=10s`、`max_workers=20`。
- 故障语义：`TdxServersUnavailableError` 表示整轮无可用节点；`PROBE_EMPTY_ERROR` 为探测空返回标记。
- 交易日历：`latest_trading_day()`（最近交易日，周末/盘前自动回退）、`resolve_session(d, "previous"|"next")`、`trading_days_after(target)`、`is_trading_day()`、`parse_date()`。

## 4. MCP 工具入口

> 下文 JSON 仅示返回字段结构，个别未实测的字段（如均线、开高低）数值为示意值；已在第 6.3 节标注的字段为真实实测结果。

### 4.1 get_minute_kline

获取单只股票指定交易日的 1 分钟 K 线（服务器前复权），用于观察单日 K 线形状与量能。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `stock_code` | str | "" | 股票代码，与 `stock_name` 二选一 |
| `stock_name` | str | "" | 股票名称 |
| `date` | str | "" | 目标交易日 `YYYY-MM-DD`（容忍 `YYYYMMDD`）；空 = 最近交易日 |
| `adaptive_threshold` | float | 1.0 | 抽点阈值（%）；传 0 保留全部 240 点 |

**按交易日定位（内部实现）**：`k = trading_days_after(目标日)`，`start = max(0, k*240 - 240)`、`offset = 800`（通达信 `bars` 的 `start` 为"从最新往前跳过的根数"，单页上限 800），取回后按日期切片；个股停牌/次新导致"根数 ≠ 交易日数×240"时，按窗口与目标日的先后逐日挪动 `start` 重试（最多 5 次）。空返回时用 `start=0, offset=10` 的探针区分"超历史深度"与"节点异常"。

**默认日回退**：`date` 留空且当日无分钟数据（盘前）时，自动回退上一交易日并在日志中标记。

**返回结构：**

```json
{
    "symbol": "000592",
    "date": "2026-11-13",
    "frequency": "1min",
    "count": 240,
    "prev_close": 7.3,
    "data": [
        {
            "time": "09:31",
            "open": 6.95,
            "high": 6.98,
            "low": 6.93,
            "close": 6.95,
            "volume": 240420,
            "change_pct": -4.79
        }
    ]
}
```

自适应模式（`adaptive_threshold` 生效时）`frequency="adaptive_1min"`，每条额外带 `type`（`open` / `trigger_pct` / `new_high` / `new_low` / `close`），`new_high` / `new_low` 附带 `is_limit_up` / `is_limit_down`。

> **字段裁剪**：`_finalize_output_fields()` 在全部计算完成后把 `datetime` 改名为 `time`（截为 `HH:mm`），并删除 `amount`、`change_pct_from_base`、`base_price`。`prev_close` 为顶层字段（2026-11 起新增）。

### 4.2 get_minute_kline_batch

批量获取多只股票同一交易日的 1 分钟 K 线，5 线程并发、单只失败不影响其余。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `stocks` | list | None | 每项 `{"code": "600602", "name": "云赛智联"}`，单次最多 30 只（超出截断） |
| `date` | str | "" | 目标交易日；整批统一口径，空 = 最近交易日 |
| `adaptive_threshold` | float | 1.0 | 抽点阈值 |

**返回结构：**

```json
{
    "date": "2026-11-13",
    "results": [{"code": "...", "name": "...", "symbol": "...", "date": "...", "frequency": "...", "count": 240, "data": []}],
    "errors": [{"code": "...", "name": "...", "reason": "..."}],
    "meta": {"total": 10, "success": 9, "failed": 1, "workers": 5, "nodes": ["ip:port", "..."]}
}
```

**容错设计**：每个 worker 线程创建独立的 `StockDataFetcher(server=node, use_server_manager=False)`，绑定不同节点；单只失败最多换 3 个节点重试，`NonRetryableError`（停牌/非交易日/超范围）直接记入 `errors` 不再换节点。

### 4.3 get_daily_kline

获取日 K 线数据，含均线、涨跌停价格、服务器昨收、成交量股/手。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `stock_code` | str | "" | 股票代码 |
| `stock_name` | str | "" | 股票名称（用于 ST 识别与代码解析） |
| `count` | int | 120 | K 线条数 |

**返回结构：**

```json
{
    "symbol": "000592",
    "frequency": "daily",
    "count": 120,
    "adjust": "qfq",
    "indicators": {
        "ma": ["ma5", "ma10", "ma20"],
        "pre_close": true,
        "pre_close_source": "server_last_close",
        "volume_unit": {"volume": "手", "shares": "股"},
        "limit": ["limit_up", "limit_down", "is_limit_up", "is_limit_down"]
    },
    "data": [
        {
            "datetime": "2026-11-13 15:00:00+08:00",
            "open": 7.35,
            "high": 7.4,
            "low": 6.68,
            "close": 6.73,
            "volume": 2305703,
            "shares": 230570304,
            "amount": 1595877888.0,
            "ma5": 7.12,
            "ma10": 6.98,
            "ma20": 6.75,
            "pre_close": 7.3,
            "limit_up": 8.03,
            "limit_down": 6.57,
            "is_limit_up": false,
            "is_limit_down": false
        }
    ]
}
```

- `pre_close` 优先取服务器 `last_close`（qfq 同口径），窗口首根缺失时退回前一根 `close`
- `shares` = `volume_wire_value`（股）；`volume` 仍为手（`volume_lots`）
- 第一条日K线因无昨收，`pre_close` 与涨跌停字段为 `null` / `None`

### 4.4 get_stock_quote

获取股票实时行情快照。

| 参数 | 类型 | 默认 |
|------|------|------|
| `stock_code` | str | ""（与 `stock_name` 二选一） |
| `stock_name` | str | "" |

```json
{
    "symbol": "000592",
    "code": "000592",
    "price": 6.73,
    "last_close": 7.3,
    "change_pct": -7.81,
    "open": 7.35,
    "high": 7.4,
    "low": 6.68,
    "volume": 2305703,
    "amount": 1595877888.0
}
```

### 4.5 get_intraday_chart

获取分时走势（价格曲线 + 均价线 + 每分钟成交量），当日与历史均可。与 `get_minute_kline` 的分工：分时给"每分钟价格 + 均价线"（画分时图），分钟K 给 OHLC（画K线）。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `stock_code` | str | "" | 股票代码（与 `stock_name` 二选一） |
| `stock_name` | str | "" | 股票名称 |
| `date` | str | "" | 目标交易日 `YYYY-MM-DD`；空 = 最近交易日 |

```json
{
    "symbol": "000592",
    "date": "2026-11-13",
    "frequency": "intraday",
    "count": 240,
    "prev_close": 7.3,
    "data": [
        {
            "time": "09:31",
            "price": 6.95,
            "avg_price": 7.01,
            "volume": 240420,
            "change_pct": -4.79
        }
    ]
}
```

- `avg_price` 由服务器直给（当日分时），**不再需要本地累计成交额自算**；历史分时协议不带均价，此时返回 `null`
- `volume` 单位 = 手（实测当日合计与日K `volume_lots` 完全一致）
- `prev_close` 优先取 `MinuteSeries.prev_close`（历史分时当日实际昨收）；当日分时为 null 时回退 `_get_prev_close()`（日K 昨收）
- `date` 留空且当日无分时数据时，自动回退上一交易日

## 5. 数据流程

```
┌─────────────┐      ┌──────────────────┐      ┌──────────────────┐
│  MCP客户端  │─────▶│ StockMarket      │─────▶│ StockDataFetcher │
│ (Hermes等)  │      │ Service          │      │                  │
└─────────────┘      └──────────────────┘      └────────┬─────────┘
                                                        │
                                                        ▼
                                               ┌──────────────────┐
                                               │ EltdxQuotes      │
                                               │ (mootdx 兼容层)   │
                                               └────────┬─────────┘
                                                        │
                                                        ▼
                                               ┌──────────────────┐
                                               │ eltdx TdxClient  │
                                               │ 通达信主站 7709   │
                                               └──────────────────┘
                                         节点选择 ▲
                                               ┌──────────────────┐
                                               │ TdxServerManager │
                                               │ 缓存/探测/切换    │
                                               └──────────────────┘
```

## 6. 复权与昨收口径

### 6.1 当前口径（2026-11 起）

| 数据类型 | 复权方式 | 昨收来源 |
|---|---|---|
| 日K | 服务器 `bars.get(adjust="qfq")` | K线自带 `last_close_price_milli` |
| 1分钟K | 服务器 `bars.get(adjust="qfq")` | 同上（日K同口径昨收） |
| 分时 | 服务器原生分时（不复权协议） | `MinuteSeries.prev_close`，缺失回退日K昨收 |

服务器端可用复权模式：`none / qfq / hfq / fixed_qfq / fixed_hfq`；定点模式需配 `anchor_date`，用于跨多个除权日保持同一基准（长周期横向比较场景）。

### 6.2 为什么删掉本地复权

迁移到 eltdx 后 `client.xdxr()` 无数据（eltdx 不存在该接口），原 `_apply_qfq()` 变成 no-op，导致**分钟线实际是不复权价却对外声称"前复权"**，且与服务器已复权的日K跨口径不一致。

修复（commit `2ec9a3d`）：

1. 分钟K也请求 `adjust="qfq"`，由服务器复权；
2. 删除整套本地复权机制：`_apply_qfq` / `_get_adjust_events` / `_build_adjust_events` / `xdxr` 存根 / `bisect` 导入 / `_adjust_events_cache`；
3. 昨收改取 K 线自带 `last_close`，不再用 `minutes.history(...).prev_close`（后者是**当日原始口径**，除权日与复权价不匹配）。

### 6.3 实测口径证据

| 场景 | 数据 | 结论 |
|---|---|---|
| 601398 工行（2026-10-21 除权） | 10-20 分钟末收/昨收 = 0.9976，日K qfq 当日涨跌 = 0.9976 | 分钟线确已前复权，与日K同口径 |
| 000592 平潭发展 11-13 | 分钟末收 6.73 = 日K收盘 6.73；`prev_close` 7.30 = 前一日 close | 跨周期口径一致 |
| 000592 11-13 分时 | 分时量合计 2,305,703 = 日K `volume`；末点均价 6.92 ≈ 成交额/成交量 | 分时量与均价单位正确 |
| 000592 11-13 日K | `shares` 230,570,304 = `volume_lots` 2,305,703.04 × 100 | 股数字段口径正确 |

## 7. 涨跌停计算规则

根据代码前缀和名称自动匹配板块比例：

| 板块 | 代码特征 | 涨跌停比例 |
|------|---------|-----------|
| ST / *ST | 名称含 "ST" | ±5% |
| 科创板 | 688xxx | ±20% |
| 创业板 | 300xxx / 301xxx | ±20% |
| 北交所 | 8xxxxx | ±30% |
| 主板 | 其余 | ±10% |

- 实现于 `_get_limit_ratio()`，ST 检测需调用方传 `stock_name`
- 涨跌停价 = `round(pre_close × (1 ± ratio), 2)`（四舍五入到分，避免涨跌幅 9.98%/9.99% 漏判）
- 封板判定：`close >= limit_up - 0.005` / `close <= limit_down + 0.005`（`LIMIT_PRICE_TOLERANCE`）
- **为何仍自算**：`limits.special`（0x0452 特殊品种表）实测全市场仅 1 条（000010），普通股票不在表内

## 8. 服务器探测与容错

| 机制 | 说明 |
|---|---|
| 节点缓存 | 优先 star_stocks `tdx_servers.json`（含质量排序），缺失时并发探测 |
| 单请求重试 | `_execute_with_retry`：单次操作失败换节点，最多 `MAX_RETRY_COUNT=3` 次 |
| 业务性错误 | `NonRetryableError`（停牌/非交易日/超范围/未来日期）直接返回错误，不浪费重试 |
| 批量并发 | 每 worker 独立连接 + 固定节点，失败最多换 3 个不同节点 |
| 连接复用 | `_client` 常驻，`close()` 时释放；日K 缓存 TTL 60s，避免跨交易日取不到最新一根 |

## 9. 自适应K线提取 (Adaptive K-line Extraction)

为了减少 LLM 上下文占用，系统提供基于 1% 波动阈值 + 全天极值的自适应提取算法。

### 9.1 提取规则

1. **基准初始化**：记录早盘第一条的开盘价作为初始基准，标记 `type: open`；同时预先计算全天最高/最低价（扫描前对全部 240 根求极值）。
2. **规则 B（全天最高）**：当前最高价 == 全天最高价 → `new_high`，仅首次命中记录（防止一字板/全同价重复记录）。
3. **规则 C（全天最低）**：当前最低价 == 全天最低价 → `new_low`，同上。
4. **规则 A（波动突破）**：非极值点的收盘价相对**滚动基准价**涨跌幅绝对值 ≥ 阈值（默认 1%）→ `trigger_pct`。
5. **或关系**：三条规则独立检查，任一命中即记录该根并更新滚动基准（基准 = 该根收盘价）；全部未命中则不记录、不更新基准。
6. **优先级**：同时命中多规则时极值标记优先（如全天最高且波动超阈值 → 记 `new_high`），单根只取一个 `type`。
7. **收盘保护**：最后一条若未被任何规则命中，强制补记 `type: close`。

### 9.2 输出字段

| 字段 | 说明 |
|------|------|
| `time` | 时间 `HH:mm` |
| `open` / `high` / `low` / `close` | 该分钟 OHLC（前复权） |
| `volume` | 成交量（手） |
| `change_pct` | 相对昨收涨跌幅 % |
| `type` | `open` / `trigger_pct` / `new_high` / `new_low` / `close` |
| `is_limit_up` (bool) | 是否触及涨停价（仅 `new_high`） |
| `is_limit_down` (bool) | 是否触及跌停价（仅 `new_low`） |

> 已删除字段：`amount`、`change_pct_from_base`、`base_price`（由 `_finalize_output_fields()` 在处理完成后裁剪）。

### 9.3 上下文占用优化

1. **单份返回**：所有工具声明 `structured_output=False`，FastMCP 不再生成 structuredContent 冗余包装。
2. **compact 序列化**：`json.dumps` 不使用 `indent`，输出单行紧凑 JSON。

**历史实测**（300308 中际旭创单日）：优化前 39 个特征点 / 双份 pretty 约 19.4K 字符 → 优化后 16 个特征点 / 单份 compact 2392 字符，上下文成本降低约 88%。

## 10. 依赖说明

| 依赖 | 版本 | 说明 |
|------|------|------|
| `eltdx` | >=3.3.0 | 通达信数据接口（K线/分时/快照） |
| `pandas` | >=3.0.3 | 数据处理 |
| `mcp[cli]` | >=2.3.0 | MCP 框架 |
| `star-stocks` | editable（`../star_stocks`） | 节点缓存 `tdx_servers.json` 与 `exchange_calendars` 传递依赖；缺失时降级为周末判断 |

> 与 mootdx 时代不同，eltdx 与 `mcp[cli]` 无 httpx 版本冲突，不再需要 `pip install --no-deps` 的绕行安装。

## 11. 测试与验证

| 类型 | 位置 | 内容 |
|---|---|---|
| 离线单测 | `tests/test_eltdx_adapter.py` | 适配层字段映射、`start` 透传、分钟线也请求 `qfq` |
| 分钟线窗口单测 | `tests/test_minute_date_window.py` | 交易日定位、目标日校验、payload 错误语义 |
| 集成测试 | `tests/test_data_fetcher.py` | 直连服务器取数（日K/分钟/实时/涨跌停/批量） |
| 手工验证 | `tests/manual_verify_eltdx_fields.py` | 000592 / 600715 逐项核对 + 601398 复权口径对照，当前 38/38 通过 |

运行：`.venv/bin/python -m pytest tests -q`（当前 62 项通过）；`.venv/bin/python tests/manual_verify_eltdx_fields.py`。

## 12. 变更历史

| 时间 | 变更 |
|---|---|
| 2026-08-09 | 输出字段裁剪（`datetime`→`time`，删 `amount` 等）；自适应提取规则优化；`structured_output=False` + compact JSON |
| 2026-10 | 分钟线支持按交易日取数 + 自适应窗口定位；引入 `TradingCalendar`；涨跌停四舍五入到分 |
| 2026-10-25 | `5fcfba4` 客户端从 mootdx 迁移到 eltdx |
| 2026-11-14 | `2ec9a3d`：日K/分钟K 改服务器前复权，删除本地复权；昨收取 `last_close`；日K 增 `shares`；新增 `get_intraday_chart`（价格+均价线+每分钟量）；修复适配层漏传 `start`；工具数 4→5 |

