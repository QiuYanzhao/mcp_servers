# MCP服务使用指导

## 快速开始

### 1. 安装依赖

```bash
# 激活虚拟环境
source .venv/bin/activate

# 安装mcp依赖
uv pip install -e ".[dev]"

# 单独安装mootdx（因为与mcp有httpx版本冲突）
uv pip install mootdx --no-deps
uv pip install pandas
```

### 2. 启动服务

#### A股行情数据服务

```bash
# 方式1：直接运行启动脚本
python start_stock_market_service.py

# 方式2：使用模块方式运行
python -m src.mcp_servers.stock_market.main
```

#### 开盘红平台行情数据服务

```bash
# 方式1：直接运行启动脚本
python start_kph_market_data_service.py

# 方式2：使用模块方式运行
python -m src.mcp_servers.kph_market_data.main
```

#### star_stocks 题材数据服务

```bash
# 方式1：直接运行启动脚本
python start_star_stocks_service.py

# 方式2：使用模块方式运行
python -m src.mcp_servers.star_stocks.main
```

**前置条件：** 同级目录 `star_stocks` 已配置 `.env`（含 `DB_PASSWORD`）。

### 3. MCP客户端配置

将以下配置添加到MCP客户端（如Claude Desktop）：

```json
{
  "mcpServers": {
    "stock-market-service": {
      "command": "uv",
      "args": ["run", "python", "start_stock_market_service.py"],
      "cwd": "/Users/qyz/TraeProjects/mcp_servers",
      "env": {}
    },
    "kph-market-data": {
      "command": "uv",
      "args": ["run", "python", "start_kph_market_data_service.py"],
      "cwd": "/Users/qyz/TraeProjects/mcp_servers",
      "env": {}
    },
    "star-stocks": {
      "command": "uv",
      "args": ["run", "python", "start_star_stocks_service.py"],
      "cwd": "/Users/qyz/TraeProjects/mcp_servers",
      "env": {}
    }
  }
}
```



