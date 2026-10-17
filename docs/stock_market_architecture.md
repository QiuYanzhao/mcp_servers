# A股行情数据MCP服务 - 架构文档

## 1. 概述

A股行情数据MCP服务是一个基于mootdx的Model Context Protocol服务，提供A股市场数据获取功能。

### 核心功能

| 功能 | 说明 |
|------|------|
| 1分钟K线数据 | 获取单日K线形状和量能 |
| 日K线数据 | 含5/10/20日均线、涨跌停、昨日收盘价 |
| 前复权处理 | 所有K线数据自动前复权 |

### 技术栈

- **Python**: 3.12+
- **MCP框架**: FastMCP
- **数据源**: mootdx（通达信数据接口）
- **数据处理**: pandas

## 2. 项目结构

```
src/mcp_servers/
├── __init__.py
├── base.py                    # MCP服务器基类
└── stock_market/
    ├── __init__.py
    ├── main.py                # 启动脚本
    ├── service.py             # MCP服务定义（工具注册）
    └── data_fetcher.py        # 数据获取核心逻辑
```

## 3. 核心模块

### 3.1 BaseMCPServer（base.py）

MCP服务器基类，提供：
- FastMCP实例管理
- 工具/资源注册接口
- 服务器启动方法

### 3.2 StockDataFetcher（data_fetcher.py）

数据获取核心类，封装mootdx操作：

```
StockDataFetcher
├── _get_client()          # 获取/创建mootdx客户端
├── _apply_qfq()           # 前复权处理
├── get_minute_data()      # 获取1分钟K线数据
├── get_daily_kline()      # 获取日K线数据
├── get_realtime_quote()   # 获取实时行情
└── _finalize_output_fields()  # 输出字段裁剪（datetime→time、删 amount 等）
```

**关键方法说明：**

| 方法 | 参数 | 返回值 |
|------|------|--------|
| `get_minute_data(symbol, date)` | 股票代码, 交易日(YYYY-MM-DD，空=最近交易日) | 该交易日1分钟K线数据字典 |
| `get_daily_kline(symbol, count)` | 股票代码, 数据条数 | 日K线数据字典（含均线） |
| `_apply_qfq(client, symbol, df)` | 客户端, 股票代码, 原始数据 | 前复权后的DataFrame |
| `_finalize_output_fields(data_list)` | 特征点列表 | 裁剪后的列表（仅输出层，不影响计算） |

### 3.3 StockMarketService（service.py）

MCP服务定义类，注册MCP工具：

```
StockMarketService
├── register_tools()       # 注册MCP工具
├── register_resources()   # 注册MCP资源
└── run()                  # 启动服务
```

## 4. MCP工具入口

### 4.1 get_minute_kline

获取指定交易日的1分钟K线数据，用于分析单日K线形状和量能（只返回目标日当天，不跨日）。支持自适应抽点以减少数据量。

**参数：**
- `stock_code` (str): 股票代码，如 "600519"
- `stock_name` (str): 股票名称（可选）
- `date` (str): 目标交易日 `YYYY-MM-DD`（容忍 `YYYYMMDD`），默认空=最近交易日；盘前当日无数据时自动回退上一交易日
- `adaptive_threshold` (float): 抽点阈值，默认 1.0 (即 1%)；传 0 保留全部点，传 None 会被参数校验拒绝

**按交易日定位（内部实现）**：交易日历取 exchange_calendars 的 XSHG（与 star_stocks 一致），`k` = 目标日之后的交易日数，`start = max(0, k*240 - 240)`、`offset = 800`（通达信 `bars` 的 `start` 为"从最新往前跳过的根数"，单次上限 800），取回后按日期切片；个股停牌/次新导致根数不足时按窗口先后挪动 `start` 重试。

**返回字段（当前版本）：**
```json
{
    "symbol": "600519",
    "date": "2026-10-16",
    "frequency": "1min",
    "count": 240,
    "data": [
        {
            "time": "09:31",
            "open": 1800.0,
            "high": 1805.0,
            "low": 1798.0,
            "close": 1802.0,
            "volume": 1500,
            "change_pct": 0.1
        }
    ]
}
```

**自适应模式返回字段（当设置 adaptive_threshold 时）：**
```json
{
    "symbol": "600519",
    "date": "2026-10-16",
    "frequency": "adaptive_1min",
    "count": 15,
    "data": [
        {
            "time": "09:31",
            "open": 1800.0,
            "high": 1800.0,
            "low": 1800.0,
            "close": 1800.0,
            "volume": 500,
            "change_pct": 0.0,
            "type": "open"
        },
        {
            "time": "09:35",
            "open": 1810.0,
            "high": 1818.0,
            "low": 1810.0,
            "close": 1818.0,
            "volume": 2000,
            "change_pct": 1.0,
            "type": "trigger_pct"
        },
        {
            "time": "10:40",
            "open": 1820.0,
            "high": 1830.0,
            "low": 1819.0,
            "close": 1828.0,
            "volume": 3000,
            "change_pct": 1.56,
            "type": "new_high",
            "is_limit_up": false
        }
    ]
}
```

> **输出字段裁剪（2026-08-09 优化）**：`datetime` 已改名为 `time`（内容由 `yyyy-MM-dd HH:mm` 截取为 `HH:mm`）；`amount`、`change_pct_from_base`、`base_price` 三个字段已删除。字段裁剪由 `_finalize_output_fields()` 在全部处理计算完成后执行，不影响处理过程。

### 4.2 get_daily_kline

获取日K线数据，包含均线和涨跌停信息。

**参数：**
- `stock_code` (str): 股票代码，如 "600519"
- `count` (int): 数据条数，默认120

**返回字段：**
```json
{
    "symbol": "600519",
    "frequency": "daily",
    "count": 120,
    "adjust": "qfq",
    "indicators": {
        "ma": ["ma5", "ma10", "ma20"],
        "pre_close": true,
        "limit": ["limit_up", "limit_down"]
    },
    "data": [
        {
            "datetime": "2026-06-03",
            "open": 1800.0,
            "high": 1820.0,
            "low": 1795.0,
            "close": 1815.0,
            "volume": 25000,
            "amount": 45000000.0,
            "ma5": 1805.0,
            "ma10": 1798.0,
            "ma20": 1785.0,
            "pre_close": 1800.0,
            "limit_up": 1980.0,
            "limit_down": 1620.0
        }
    ]
}
```

### 4.3 get_stock_quote

获取股票实时行情。

**参数：**
- `stock_code` (str): 股票代码

**返回字段：**
```json
{
    "symbol": "600519",
    "open": 1800.0,
    "high": 1820.0,
    "low": 1795.0,
    "close": 1815.0,
    "volume": 25000,
    "amount": 45000000.0
}
```

## 5. 数据流程

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   MCP客户端     │────▶│  StockMarket    │────▶│  StockData      │
│                 │     │  Service        │     │  Fetcher        │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                       │
                                                       ▼
                                                ┌─────────────────┐
                                                │  mootdx         │
                                                │  (通达信服务器)  │
                                                └─────────────────┘
```

## 6. 涨跌停计算规则

根据股票代码前缀和名称自动匹配板块比例如下：

| 板块 | 代码特征 | 涨跌停比例 |
|------|---------|-----------|
| 主板 | 60xxxx, 00xxxx 等 | ±10%（默认） |
| 科创板 | 688xxx | ±20% |
| 创业板 | 300xxx, 301xxx | ±20% |
| 北交所 | 8xxxxx | ±30% |
| ST股票 | 名称含"ST" | ±5% |

实现位于 `_get_limit_ratio()` 方法中。ST 检测需要调用方传入 `stock_name` 参数。

涨跌停价按交易所规则对 `pre_close × (1 ± ratio)` **四舍五入到分**（`round(..., 2)`），避免涨跌幅显示为 9.98%、9.99% 等时的漏判。

此外，每根日K线还会输出以下涨停状态字段：
- `is_limit_up`：收盘价是否达到涨停价（`close >= limit_up - 0.005`）
- `is_limit_down`：收盘价是否达到跌停价（`close <= limit_down + 0.005`）

第一条日K线因无 `pre_close`，以上字段均为 `None`。

## 7. 前复权处理

前复权（qfq）以最新价格为基准，向前调整历史价格，保证K线图的连续性。

```python
# 前复权处理流程（2026-10 修复：mootdx 已无 to_qfq，改为本地计算）
1. 获取原始K线数据
2. 获取除权除息数据（xdxr，category==1）
3. 用 xdxr + 原始日K（250 根）算出每个事件的乘数：
   ratio = ((前一日收盘*10 - 每10股派息 + 每10股配股数*配股价)
            / (10 + 每10股配股数 + 每10股送转股数)) / 前一日收盘
4. 事件日之前的价格 × ratio（乘数序列以最新交易日为基准，与传入窗口无关），仅调整 OHLC，不调整 volume
```

> 乘数按股票缓存；分钟线只取历史某一天时，复权口径与日K接口一致（同以最新交易日为基准）。

## 8. 依赖说明

| 依赖 | 版本 | 说明 |
|------|------|------|
| mootdx | >=0.11.0 | 通达信数据接口 |
| pandas | >=1.5.0 | 数据处理 |
| mcp[cli] | >=1.0.0 | MCP框架 |

**注意：** mootdx与mcp[cli]存在httpx版本冲突，需要单独安装mootdx：
```bash
pip install mootdx --no-deps
```

## 9. 自适应K线提取 (Adaptive K-line Extraction)

为了减少 LLM 上下文占用，系统提供了一种基于 1% 波动阈值 + 全天极值的自适应提取算法。

### 9.1 提取规则（2026-08-09 更新）

1.  **基准初始化**：记录早盘第一条数据的开盘价作为初始基准，标记 `type: open`；同时**预先计算全天最高价/全天最低价**（逐根扫描前对全部 240 根求极值）。
2.  **规则 B（全天最高）**：当前最高价 == 全天最高价 → 标记 `new_high`。仅首次命中记录（开盘即全天最高视为已记录，防止一字板/全同价场景重复记录全部 K 线）。
3.  **规则 C（全天最低）**：当前最低价 == 全天最低价 → 标记 `new_low`。规则同上。
4.  **规则 A（波动突破）**：非极值点的收盘价相对**滚动基准价**涨跌幅绝对值 ≥ 阈值（默认 1%）→ 标记 `trigger_pct`。
5.  **或关系**：三条规则独立检查，**任一命中即记录该根 K 线并更新滚动基准**（基准 = 该根收盘价，供后续规则 A 使用）；全部未命中则不记录、不更新基准。
6.  **优先级**：同时命中多规则时，极值标记优先于波动标记（如同时是全天最高且波动超阈值 → 记为 `new_high` 而非 `trigger_pct`），单根只取一个 `type`。
7.  **收盘保护**：最后一条（收盘价）若未被任何规则命中，强制补记，标记 `type: close`。

### 9.2 输出字段说明

自适应模式下每条数据的字段（**2026-08-09 起已裁剪**）：

| 字段 | 说明 |
|------|------|
| `time` | 时间 `HH:mm`（原 `datetime`，已去掉日期部分） |
| `open` / `high` / `low` / `close` | 该分钟 OHLC |
| `volume` | 成交量 |
| `change_pct` | 相对昨收涨跌幅 %（与基础模式一致） |
| `type` | 触发类型：`open` / `trigger_pct` / `new_high` / `new_low` / `close` |
| `is_limit_up` (bool) | 是否触及涨停价（仅 `new_high` 类型） |
| `is_limit_down` (bool) | 是否触及跌停价（仅 `new_low` 类型） |

> **已删除字段**：`amount`、`change_pct_from_base`、`base_price`（2026-08-09 起不再返回，由 `_finalize_output_fields()` 在全部计算完成后裁剪）。

### 9.3 上下文占用优化（2026-08-09）

除自适应提取外，接口层还有两处优化，显著降低 LLM 上下文成本：

1.  **单份返回**：三个工具（`get_minute_kline` / `get_daily_kline` / `get_stock_quote`）均声明 `structured_output=False`，FastMCP 不再生成 `{"result": ...}` 的 structuredContent 冗余包装，Hermes 客户端只收到单份 `{"result": ...}`——返回量减半。
2.  **compact 序列化**：`json.dumps` 不使用 `indent`，输出为单行紧凑 JSON——字符量再降约 19%。

**实测效果**（300308 中际旭创单日）：优化前 39 个特征点 / 双份 pretty 约 19.4K 字符 → 优化后 16 个特征点 / 单份 compact 2392 字符，**上下文成本降低约 88%**。
