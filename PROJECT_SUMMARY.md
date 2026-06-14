# MCP Servers 项目总结

## 项目概述

这是一个MCP服务器集合项目，使用Python和uv包管理器开发。目前包含A股行情数据MCP服务和开盘红平台行情数据MCP服务。

## 项目结构

```
mcpServers/
├── src/
│   └── mcp_servers/
│       ├── __init__.py
│       ├── base.py
│       ├── stock_market/
│       │   ├── __init__.py
│       │   ├── service.py
│       │   └── main.py
│       └── kph_market_data/
│           ├── __init__.py
│           ├── config.py
│           ├── logger.py
│           ├── client.py
│           ├── models.py
│           ├── service.py
│           └── main.py
├── tests/
│   ├── test_stock_market.py
│   └── test_kph_market_data.py
├── examples/
│   ├── stock_market_example.py
│   └── kph_market_data_example.py
├── docs/
├── pyproject.toml
├── mcp_config.json
├── start_stock_market_service.py
├── start_kph_market_data_service.py
├── README.md
└── PROJECT_SUMMARY.md
```

## 核心功能

### 1. A股行情数据服务

- **get_minute_kline**: 获取1分钟K线数据
- **get_daily_kline**: 获取日K线数据
- **get_stock_quote**: 获取股票实时行情

### 2. 开盘红平台行情数据服务

- **get_live_content**: 获取当日大盘直播内容
- **get_limit_up_ladder**: 获取当日涨停天梯数据
- **get_market_highlights**: 获取当日盘面亮点数据
- **get_historical_live_content**: 获取历史大盘直播内容
- **get_historical_limit_up_ladder**: 获取历史涨停天梯数据
- **get_historical_market_highlights**: 获取历史盘面亮点数据

## 技术栈

- **Python**: 3.12+
- **包管理器**: uv
- **MCP框架**: FastMCP
- **测试框架**: pytest
- **代码质量**: black, flake8, mypy

## 使用方法

### 1. 安装依赖

```bash
uv pip install -e ".[dev]"
```

### 2. 启动服务

```bash
# 启动A股行情数据服务
python start_stock_market_service.py

# 启动开盘红平台行情数据服务
python start_kph_market_data_service.py
```

### 3. 运行测试

```bash
pytest tests/ -v
```

### 4. 运行示例

```bash
# 运行A股行情数据示例
python examples/stock_market_example.py

# 运行开盘红平台行情数据示例
python examples/kph_market_data_example.py
```

## 开发指南

### 添加新的MCP服务

1. 在 `src/mcp_servers/` 下创建新的服务目录
2. 继承 `BaseMCPServer` 基类
3. 实现 `register_tools()` 和 `register_resources()` 方法
4. 创建测试文件
5. 更新 `pyproject.toml` 如有新依赖

### 代码质量检查

```bash
# 代码格式化
black src tests examples

# 代码检查
flake8 src tests examples

# 类型检查
mypy src
```

## 项目特点

1. **模块化设计**: 每个MCP服务独立模块，便于扩展
2. **标准化结构**: 遵循Python项目最佳实践
3. **完整测试**: 包含单元测试和集成测试
4. **代码质量**: 使用black, flake8, mypy确保代码质量
5. **文档完善**: 包含README、示例和项目总结

## 下一步计划

1. 实现更多的MCP服务
2. 完善错误处理和日志记录
3. 添加配置文件支持
4. 实现服务注册和发现机制
5. 添加性能监控和统计功能

## 许可证

MIT License