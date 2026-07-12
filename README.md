# MCP Servers

MCP（Model Context Protocol）服务器集合，提供 A 股行情数据、开盘红平台行情数据、题材个股管理三大数据服务，可直接接入 Claude Desktop、Trae 等支持 MCP 协议的 AI 客户端。

## 功能模块

### A股行情数据服务（stock-market-service）

基于 mootdx（通达信数据接口）提供 A 股市场数据：

| 工具 | 说明 |
|------|------|
| `get_minute_kline` | 1 分钟 K 线数据，适用于观察单日分时走势与量能 |
| `get_daily_kline` | 日 K 线数据，含 5/10/20 日均线、涨跌停价格、流通市值 |
| `get_stock_quote` | 股票实时行情快照 |

支持通过股票代码或名称查询，自动识别板块涨跌停比例（主板 ±10%、科创/创业板 ±20%、北交所 ±30%、ST ±5%），数据均做前复权处理。

### 开盘红平台行情数据服务（kph-market-data）

对接开盘红平台，提供盘面数据的实时与历史查询：

| 工具 | 说明 |
|------|------|
| `get_live_content` | 当日大盘直播内容（概念点、盘面解读、关联个股） |
| `get_limit_up_ladder` | 当日涨停天梯（题材排名、连板个股、涨停时间） |
| `get_market_highlights` | 当日盘面亮点（时间节点、标签类型、关联题材） |
| `get_historical_live_content` | 历史大盘直播内容 |
| `get_historical_limit_up_ladder` | 历史涨停天梯 |
| `get_historical_market_highlights` | 历史盘面亮点 |

### 题材个股管理服务（star-stocks）

基于数据库的题材与个股 CRUD 服务，用于维护炒作方向、细分方向及关联个股的结构化数据：

| 工具 | 说明 |
|------|------|
| `list_themes_with_sub_directions` | 查询所有题材及细分方向 |
| `list_main_rotation_trees` | 查询主线与轮动题材完整树 |
| `get_theme_tree` | 查询指定题材的完整树 |
| `create_theme` / `update_theme` / `delete_theme` | 题材的增删改 |
| `create_sub_direction` / `delete_sub_direction` | 细分方向的新增与删除（**不可**通过 MCP 设置/更新评分） |
| `create_theme_stock` / `update_theme_stock` / `delete_theme_stock` | 个股条目的增删改（**不可**通过 MCP 设置/更新评分） |

## 代码架构

```
src/mcp_servers/
├── base.py                    # BaseMCPServer 基类，封装 FastMCP 初始化、工具/资源注册、运行入口
├── stock_market/              # A股行情数据服务
│   ├── data_fetcher.py        #   数据获取层（mootdx 封装、前复权、均线计算）
│   ├── service.py             #   服务层（MCP 工具注册）
│   └── main.py                #   启动入口
├── kph_market_data/           # 开盘红平台行情数据服务
│   ├── client.py              #   HTTP 客户端（封装开盘红 API 请求）
│   ├── models.py              #   数据模型（请求/响应 Pydantic 模型）
│   ├── stock_tags.py          #   个股标签查询
│   ├── config.py              #   配置管理
│   ├── logger.py              #   日志配置
│   ├── service.py             #   服务层（MCP 工具注册、数据格式化）
│   └── main.py                #   启动入口
└── star_stocks/               # 题材个股管理服务（仅 MCP 工具注册）
    ├── helpers.py             #   通用工具函数
    ├── service.py             #   MCP 工具注册
    └── main.py                #   启动入口
```

所有服务继承自 `BaseMCPServer`，统一使用 FastMCP 框架，通过 stdio 传输与 MCP 客户端通信。

## 目录结构

```
mcpServers/
├── src/mcp_servers/           # 服务源码
├── tests/                     # 测试文件
│   ├── test_stock_market.py
│   ├── test_kph_market_data.py
│   ├── test_star_stocks_mcp.py
│   └── test_data_fetcher.py
├── examples/                  # 使用示例
│   ├── stock_market_example.py
│   ├── kph_market_data_example.py
│   └── kph_market_data_client_example.py
├── docs/                      # 架构文档
├── start_stock_market_service.py      # A股行情服务启动脚本
├── start_kph_market_data_service.py   # 开盘红服务启动脚本
├── start_star_stocks_service.py       # 题材个股服务启动脚本
├── mcp_config.json            # MCP 客户端配置参考
├── pyproject.toml             # 项目元数据与依赖
└── uv.lock                    # 依赖锁文件
```

## 技术栈

| 项目 | 选型 |
|------|------|
| 语言 | Python 3.11+ |
| 包管理 | uv |
| MCP 框架 | FastMCP（mcp[cli]） |
| 行情数据 | mootdx（通达信接口） |
| HTTP 客户端 | requests |
| 数据模型 | Pydantic（star_stocks 依赖） |
| 测试 | pytest |
| 代码质量 | black / flake8 / mypy |

## 开发指南

### 添加新服务

1. 在 `src/mcp_servers/` 下创建新目录
2. 实现 `service.py`，继承 `BaseMCPServer`，实现 `register_tools()` 和 `register_resources()`
3. 实现 `main.py` 提供启动入口
4. 在项目根目录创建 `start_xxx_service.py` 启动脚本
5. 编写对应测试文件至 `tests/`

### 代码规范

```bash
# 格式化
black src tests examples

# 代码检查
flake8 src tests examples

# 类型检查
mypy src
```

### 运行测试

```bash
pytest tests/ -v
```

## 许可证

MIT License
