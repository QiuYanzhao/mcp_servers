"""
数据获取模块测试
"""

import pytest
from src.mcp_servers.stock_market.data_fetcher import StockDataFetcher


class TestStockDataFetcher:
    """数据获取器测试类"""

    def setup_method(self):
        """测试前准备"""
        self.fetcher = StockDataFetcher()

    def teardown_method(self):
        """测试后清理"""
        self.fetcher.close()

    def test_get_minute_data(self):
        """测试获取1分钟K线数据"""
        result = self.fetcher.get_minute_data("600519", count=10)

        assert "symbol" in result
        assert result["symbol"] == "600519"
        assert "data" in result
        assert isinstance(result["data"], list)

        if result["data"]:
            item = result["data"][0]
            assert "datetime" in item
            assert "open" in item
            assert "high" in item
            assert "low" in item
            assert "close" in item
            assert "volume" in item
            assert "amount" in item

    def test_get_daily_kline(self):
        """测试获取日K线数据"""
        result = self.fetcher.get_daily_kline("600519", count=30)

        assert "symbol" in result
        assert result["symbol"] == "600519"
        assert "adjust" in result
        assert result["adjust"] == "qfq"
        assert "data" in result
        assert isinstance(result["data"], list)

        if result["data"]:
            item = result["data"][0]
            assert "datetime" in item
            assert "open" in item
            assert "high" in item
            assert "low" in item
            assert "close" in item
            assert "volume" in item
            assert "amount" in item
            assert "ma5" in item
            assert "ma10" in item
            assert "ma20" in item
            assert "pre_close" in item
            assert "limit_up" in item
            assert "limit_down" in item

    def test_get_daily_kline_without_ma(self):
        """测试获取日K线数据（不含均线）"""
        result = self.fetcher.get_daily_kline("600519", count=10, include_ma=False)

        assert "data" in result
        if result["data"]:
            item = result["data"][0]
            assert "ma5" not in item

    def test_get_realtime_quote(self):
        """测试获取实时行情"""
        result = self.fetcher.get_realtime_quote("600519")

        assert "symbol" in result
        assert result["symbol"] == "600519"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
