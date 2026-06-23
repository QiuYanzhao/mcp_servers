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
└── get_realtime_quote()   # 获取实时行情
```

**关键方法说明：**

| 方法 | 参数 | 返回值 |
|------|------|--------|
| `get_minute_data(symbol, count)` | 股票代码, 数据条数 | 1分钟K线数据字典 |
| `get_daily_kline(symbol, count)` | 股票代码, 数据条数 | 日K线数据字典（含均线） |
| `_apply_qfq(client, symbol, df)` | 客户端, 股票代码, 原始数据 | 前复权后的DataFrame |

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

获取1分钟K线数据，用于分析单日K线形状和量能。

**参数：**
- `stock_code` (str): 股票代码，如 "600519"
- `count` (int): 数据条数，默认240

**返回字段：**
```json
{
    "symbol": "600519",
    "frequency": "1min",
    "count": 240,
    "data": [
        {
            "datetime": "2026-06-03 09:30:00",
            "open": 1800.0,
            "high": 1805.0,
            "low": 1798.0,
            "close": 1802.0,
            "volume": 1500,
            "amount": 2700000.0
        }
    ]
}
```

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

此外，每根日K线还会输出以下涨停状态字段：
- `is_limit_up`：收盘价是否达到涨停价（`close >= limit_up - 0.001`）
- `is_limit_down`：收盘价是否达到跌停价（`close <= limit_down + 0.001`）

第一条日K线因无 `pre_close`，以上字段均为 `None`。

## 7. 前复权处理

前复权（qfq）以最新价格为基准，向前调整历史价格，保证K线图的连续性。

```python
# 前复权处理流程
1. 获取原始K线数据
2. 获取除权除息数据（xdxr）
3. 使用mootdx.utils.adjust.to_qfq()计算前复权价格
4. 返回前复权后的数据
```

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
