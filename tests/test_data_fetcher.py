"""
数据获取模块测试
"""

import pytest
from src.mcp_servers.stock_market.data_fetcher import StockDataFetcher


class TestLimitPriceCalculation:
    """涨跌停价格与封板判断（纯逻辑，不依赖行情接口）"""

    @pytest.mark.parametrize(
        "pre_close,expected_limit_up,pct",
        [
            (5.02, 5.52, 9.96),   # 涨跌幅 <10% 但封在交易所涨停价
            (10.03, 11.03, 9.97),
            (18.88, 20.77, 10.01),  # 涨跌幅 >10%
            (10.00, 11.00, 10.00),
        ],
    )
    def test_limit_up_at_exchange_price(self, pre_close, expected_limit_up, pct):
        """交易所四舍五入涨停价应被识别为涨停"""
        limit_up = StockDataFetcher._calc_limit_up_price(pre_close, 0.10)
        assert limit_up == expected_limit_up
        assert StockDataFetcher._is_at_limit_up(expected_limit_up, limit_up)

    def test_limit_up_miss_with_old_unrounded_logic(self):
        """旧逻辑（未舍入）会在 9.98% 附近漏判，新逻辑应命中"""
        pre_close = 5.02
        close = 5.52  # 交易所涨停价，涨跌幅约 9.96%
        raw_limit = pre_close * 1.10  # 5.522
        assert close < raw_limit - 0.001  # 旧逻辑漏判
        limit_up = StockDataFetcher._calc_limit_up_price(pre_close, 0.10)
        assert StockDataFetcher._is_at_limit_up(close, limit_up)

    def test_not_limit_up_when_below_exchange_price(self):
        """未封涨停价时不应误判"""
        pre_close = 10.00
        limit_up = StockDataFetcher._calc_limit_up_price(pre_close, 0.10)
        assert not StockDataFetcher._is_at_limit_up(10.99, limit_up)

    def test_limit_down_at_exchange_price(self):
        """跌停价四舍五入后应正确识别"""
        pre_close = 5.02
        limit_down = StockDataFetcher._calc_limit_down_price(pre_close, 0.10)
        assert limit_down == 4.52
        assert StockDataFetcher._is_at_limit_down(4.52, limit_down)

    @pytest.mark.parametrize(
        "symbol,stock_name,expected",
        [
            ("600519", "", 0.10),
            ("688001", "", 0.20),
            ("300750", "", 0.20),
            ("830799", "", 0.30),
            ("600519", "ST茅台", 0.05),
        ],
    )
    def test_get_limit_ratio(self, symbol, stock_name, expected):
        assert StockDataFetcher._get_limit_ratio(symbol, stock_name) == expected


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
