"""
数据获取模块测试
"""

import pytest
from mcp_servers.stock_market.data_fetcher import StockDataFetcher


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
        """测试获取1分钟K线数据（默认最近交易日）"""
        result = self.fetcher.get_minute_data("600519")

        assert "symbol" in result
        assert result["symbol"] == "600519"
        assert "date" in result  # 按交易日取数，返回实际交易日
        assert "data" in result
        assert isinstance(result["data"], list)

        if result["data"]:
            item = result["data"][0]
            assert "time" in item
            assert "open" in item
            assert "high" in item
            assert "low" in item
            assert "close" in item
            assert "volume" in item
            assert "change_pct" in item
            assert "type" in item
            # 输出字段裁剪：datetime/amount/change_pct_from_base/base_price 不应出现在结果中
            assert "datetime" not in item
            assert "amount" not in item
            assert "change_pct_from_base" not in item
            assert "base_price" not in item

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


class TestMinuteDataBatch:
    """批量1分钟K线测试（节点池构建/失败隔离/真实批量拉取）"""

    def setup_method(self):
        """测试前准备"""
        self.fetcher = StockDataFetcher()

    def teardown_method(self):
        """测试后清理"""
        self.fetcher.close()

    def test_build_batch_nodes_dedup_and_cap(self, monkeypatch):
        """节点池：管理器列表优先 + 缓存探测节点 + 默认/备用补齐 + 去重 + 数量上限"""
        class FakeManager:
            def get_all_servers(self):
                return [
                    ("110.41.147.114", 7709, ""),  # 与备用列表重复，应去重
                    ("10.0.0.1", 7709, ""),
                ]

        monkeypatch.setattr(
            "mcp_servers.stock_market.data_fetcher.get_server_manager",
            lambda: FakeManager(),
        )
        # 缓存探测节点可控（模拟 tdx_servers.json 中已探测通过的服务器）
        monkeypatch.setattr(
            "mcp_servers.stock_market.data_fetcher.load_cached_tdx_servers",
            lambda: [("218.106.92.182", 7709), ("202.108.253.139", 80)],
        )
        nodes = self.fetcher._build_batch_nodes(max_nodes=5)

        assert len(nodes) == 5
        assert nodes[0] == "110.41.147.114:7709"  # 管理器列表顺序保持
        assert nodes[1] == "10.0.0.1:7709"
        assert "218.106.92.182:7709" in nodes  # 缓存探测节点进入池
        assert "202.108.253.139:80" in nodes  # 已知优质节点
        assert len(set(nodes)) == 5  # 无重复

    def test_build_batch_nodes_cap_smaller(self, monkeypatch):
        """节点池：max_nodes 小于可用节点数时截断"""
        class FakeManager:
            def get_all_servers(self):
                return [("10.0.0.1", 7709, "")]

        monkeypatch.setattr(
            "mcp_servers.stock_market.data_fetcher.get_server_manager",
            lambda: FakeManager(),
        )
        monkeypatch.setattr(
            "mcp_servers.stock_market.data_fetcher.load_cached_tdx_servers",
            lambda: [],
        )
        nodes = self.fetcher._build_batch_nodes(max_nodes=3)
        assert len(nodes) == 3

    def test_batch_failure_isolation(self, monkeypatch):
        """批量失败隔离：单只失败进入 errors，其余正常返回"""
        from mcp_servers.stock_market.data_fetcher import NonRetryableError

        def fake_payload(self, symbol, date="", adaptive_threshold=1.0, stock_name=""):
            if symbol == "999999":
                raise NonRetryableError("模拟失败")
            return {
                "symbol": symbol,
                "date": date,
                "frequency": "adaptive_1min",
                "count": 2,
                "data": [
                    {"time": "09:31", "open": 1.0, "high": 1.0, "low": 1.0,
                     "close": 1.0, "volume": 100, "change_pct": 0.0, "type": "open"},
                    {"time": "15:00", "open": 1.0, "high": 1.0, "low": 1.0,
                     "close": 1.0, "volume": 100, "change_pct": 1.0, "type": "close"},
                ],
            }

        monkeypatch.setattr(
            "mcp_servers.stock_market.data_fetcher.StockDataFetcher._fetch_minute_payload",
            fake_payload,
        )
        result = self.fetcher.get_minute_data_batch(
            [
                {"code": "600602", "name": "云赛智联"},
                {"code": "999999", "name": "失败票"},
                {"code": "600519", "name": "贵州茅台"},
            ],
            date="2026-10-15",
        )

        assert result["meta"]["total"] == 3
        assert result["meta"]["success"] == 2
        assert result["meta"]["failed"] == 1
        assert result["meta"]["workers"] == 5  # 默认5线程
        assert len(result["results"]) == 2
        assert len(result["errors"]) == 1
        assert result["date"] == "2026-10-15"
        assert result["errors"][0]["code"] == "999999"
        # 结果顺序不保证与入参一致，按 code 匹配
        assert {item["code"] for item in result["results"]} == {"600602", "600519"}
        assert all(item["date"] == "2026-10-15" for item in result["results"])

    def test_batch_empty_stocks(self):
        """空列表：直接返回空结果"""
        result = self.fetcher.get_minute_data_batch([])
        assert result["meta"]["total"] == 0
        assert result["results"] == []
        assert result["errors"] == []

    def test_batch_real_fetch(self, monkeypatch):
        """真实批量拉取（固定可用节点，验证结构与单只一致性）"""
        # 节点池固定为当日实测可用节点（202.108.253.139:80 已不可用），避免外部节点质量差异导致测试不稳定
        monkeypatch.setattr(
            "mcp_servers.stock_market.data_fetcher.StockDataFetcher._build_batch_nodes",
            lambda self, max_nodes=5: ["117.34.114.16:7709"],
        )
        result = self.fetcher.get_minute_data_batch(
            [
                {"code": "600519", "name": "贵州茅台"},
                {"code": "600036", "name": "招商银行"},
                {"code": "601318", "name": "中国平安"},
            ],
            date="2026-10-15",
            adaptive_threshold=1.0,
        )

        assert result["meta"]["total"] == 3
        assert result["meta"]["success"] == 3
        assert result["meta"]["failed"] == 0
        assert len(result["results"]) == 3
        for item in result["results"]:
            assert item["count"] > 0
            assert item["data"]
            first = item["data"][0]
            assert "time" in first  # 输出字段已裁剪为 HH:mm
            assert "open" in first
            assert "change_pct" in first
            assert "datetime" not in first
            assert "amount" not in first


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
