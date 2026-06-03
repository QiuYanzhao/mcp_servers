# MCP Servers

MCP服务器集合，包含多个MCP服务实现。

## 项目结构

```
mcpServers/
├── src/
│   └── mcp_servers/
│       ├── __init__.py
│       ├── base.py
│       └── stock_market/
│           ├── __init__.py
│           ├── service.py
│           └── main.py
├── tests/
│   └── test_stock_market.py
├── examples/
│   └── stock_market_example.py
├── docs/
├── pyproject.toml
├── mcp_config.json
├── start_stock_market_service.py
└── README.md
```

## 安装

```bash
# 使用uv安装
uv pip install -e ".[dev]"

# 或者使用pip
pip install -e ".[dev]"
```

## 使用

### 1. 启动A股行情数据服务

```bash
# 直接运行启动脚本
python start_stock_market_service.py

# 或者使用MCP客户端配置
# 将mcp_config.json中的配置添加到您的MCP客户端配置中
```

### 2. 使用示例

```bash
# 运行示例
python examples/stock_market_example.py
```

### 3. 代码中使用

```python
from src.mcp_servers.stock_market.service import StockMarketService

# 初始化服务
service = StockMarketService()

# 获取服务信息
info = service.get_server_info()
print(f"服务名称: {info['name']}")
```

## 开发

```bash
# 运行测试
pytest

# 代码格式化
black src tests

# 类型检查
mypy src

# 代码检查
flake8 src
```

## 功能特性

### A股行情数据服务

- 获取股票实时行情
- 获取股票K线数据
- 获取股票列表
- 搜索股票
- 获取市场指数
- 获取热门股票

## 许可证

MIT License