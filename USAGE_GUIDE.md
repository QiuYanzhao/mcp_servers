# 使用说明

## 环境准备

### 系统要求

- Python 3.11+
- 包管理器 uv

### 安装依赖

```bash
# 激活虚拟环境
source .venv/bin/activate

# 安装项目依赖（含开发依赖）
uv pip install -e ".[dev]"

# 单独安装 mootdx（与 mcp 存在 httpx 版本冲突，需跳过依赖解析）
uv pip install mootdx --no-deps
uv pip install pandas
```

### star_stocks 数据库配置

star_stocks 服务依赖外部数据库，在 `src/mcp_servers/star_stocks/` 同级目录（即 `../star_stocks/`）下需存在 `.env` 文件，包含 `DB_PASSWORD` 等数据库连接配置。

## 快速开始

启动任意一个服务即可验证环境是否就绪：

```bash
# 启动 A 股行情数据服务
python start_stock_market_service.py

# 启动开盘红平台行情数据服务
python start_kph_market_data_service.py

# 启动题材个股管理服务
python start_star_stocks_service.py
```

服务启动后通过 stdio 传输监听 MCP 客户端请求，保持终端前台运行即可。

## MCP 配置指南

将服务接入 MCP 客户端（Claude Desktop、Trae 等），需在客户端配置文件中添加以下内容：

```json
{
  "mcpServers": {
    "stock-market-service": {
      "command": "python",
      "args": ["start_stock_market_service.py"],
      "cwd": "<项目绝对路径>",
      "env": {}
    },
    "kph-market-data": {
      "command": "python",
      "args": ["start_kph_market_data_service.py"],
      "cwd": "<项目绝对路径>",
      "env": {}
    },
    "star-stocks": {
      "command": "python",
      "args": ["start_star_stocks_service.py"],
      "cwd": "<项目绝对路径>",
      "env": {}
    }
  }
}
```

将 `<项目绝对路径>` 替换为本项目实际路径，如 `/Users/a58/IdeaProjects/private/mcpServers`。可根据需要只配置部分服务。

项目根目录下 [mcp_config.json](mcp_config.json) 为参考配置文件。

## 脚本使用

### 启动脚本

| 脚本 | 对应服务 |
|------|----------|
| `start_stock_market_service.py` | A股行情数据服务 |
| `start_kph_market_data_service.py` | 开盘红平台行情数据服务 |
| `start_star_stocks_service.py` | 题材个股管理服务 |

每个启动脚本负责将项目根目录加入 Python 路径，并调用对应服务模块的 `main()` 函数。

### 示例脚本

位于 `examples/` 目录：

| 脚本 | 说明 |
|------|------|
| `stock_market_example.py` | 展示如何实例化 A 股行情服务并查看已注册的工具和资源 |
| `kph_market_data_example.py` | 展示如何实例化开盘红服务并查看已注册的工具和资源 |
| `kph_market_data_client_example.py` | 通过 MCP 客户端协议连接开盘红服务并调用工具 |

运行示例：

```bash
python examples/stock_market_example.py
python examples/kph_market_data_example.py
python examples/kph_market_data_client_example.py
```

### 测试脚本

位于 `tests/` 目录：

| 脚本 | 测试范围 |
|------|----------|
| `test_stock_market.py` | A 股行情服务工具 |
| `test_data_fetcher.py` | 数据获取层（mootdx 封装、前复权、均线计算） |
| `test_kph_market_data.py` | 开盘红平台服务工具 |
| `test_star_stocks_mcp.py` | 题材个股管理服务工具 |

运行全部测试：

```bash
pytest tests/ -v
```

## 维护须知

### 添加新的 MCP 服务

1. 在 `src/mcp_servers/` 下创建新目录
2. 实现 `service.py`，继承 `BaseMCPServer`，实现 `register_tools()` 和 `register_resources()`
3. 实现 `main.py` 提供 `main()` 启动入口
4. 在项目根目录创建 `start_xxx_service.py` 启动脚本
5. 在 `tests/` 下编写对应测试
6. 在 `examples/` 下编写使用示例（可选）

### 代码质量检查

```bash
black src tests examples          # 格式化
flake8 src tests examples         # 代码检查
mypy src                          # 类型检查
```

### 依赖更新

```bash
# 添加依赖
uv add <package>

# 添加开发依赖
uv add --dev <package>

# 同步锁文件
uv lock
```

### 日志排查

各服务的日志输出至 stderr，格式为 `时间 - 模块名 - 级别 - 消息`。如需调整日志级别，修改 `src/mcp_servers/base.py` 中的 `logging.basicConfig` 配置。
