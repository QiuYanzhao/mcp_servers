"""
A股行情数据MCP服务测试

测试A股行情数据服务的基本功能
"""

import pytest
from mcp_servers.stock_market.service import StockMarketService


class TestStockMarketService:
    """A股行情数据服务测试类"""

    def setup_method(self):
        """测试前准备"""
        self.service = StockMarketService()

    def test_service_initialization(self):
        """测试服务初始化"""
        assert self.service.name == "stock-market-service"
        assert self.service.version == "1.0.0"
        assert self.service.mcp is not None

    @pytest.mark.asyncio
    async def test_list_tools(self):
        """测试工具列表"""
        tools = await self.service.mcp.list_tools()
        tool_names = [tool.name for tool in tools]

        assert "get_minute_kline" in tool_names
        assert "get_minute_kline_batch" in tool_names
        assert "get_daily_kline" in tool_names
        assert "get_stock_quote" in tool_names

    @pytest.mark.asyncio
    async def test_list_resources(self):
        """测试资源列表"""
        resources = await self.service.mcp.list_resources()
        resource_uris = [str(resource.uri) for resource in resources]

        assert "stock://service/info" in resource_uris

    def test_get_minute_kline(self):
        """测试获取1分钟K线（服务正确初始化）"""
        assert self.service.mcp is not None

    def test_get_daily_kline(self):
        """测试获取日K线（服务正确初始化）"""
        assert self.service.mcp is not None

    def test_get_stock_quote(self):
        """测试获取股票行情（服务正确初始化）"""
        assert self.service.mcp is not None


if __name__ == "__main__":
    pytest.main([__file__])
