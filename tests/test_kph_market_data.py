"""
开盘红平台行情数据MCP服务测试
"""

import pytest
from unittest.mock import Mock, patch
from src.mcp_servers.kph_market_data.client import KPHClient
from src.mcp_servers.kph_market_data.models import (
    LiveContentResponse,
    LimitUpLadderResponse,
    MarketHighlightsResponse,
)
from src.mcp_servers.kph_market_data.service import KPHMarketDataService


class TestKPHClient:
    """测试KPHClient类"""

    def test_init(self):
        """测试初始化"""
        client = KPHClient()
        assert client._url is not None
        assert client._his_url is not None
        assert client._timeout == 10

    @patch('src.mcp_servers.kph_market_data.client.requests.post')
    def test_fetch_live_content_success(self, mock_post):
        """测试获取直播内容成功"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "errcode": "0",
            "date": "2026-06-14",
            "Notice": "测试公告",
            "list": [
                {
                    "ID": "1",
                    "Time": 1623456789,
                    "Comment": "测试评论",
                    "UserName": "测试用户",
                    "Stock": [],
                    "PlateName": "",
                    "PlateZDF": "",
                    "BoomReason": "",
                    "Interpretation": ""
                }
            ]
        }
        mock_response.headers = {"Content-Type": "application/json"}
        mock_post.return_value = mock_response

        client = KPHClient()
        result = client.fetch_live_content()
        assert result is not None
        assert isinstance(result, LiveContentResponse)
        assert result.date == "2026-06-14"

    @patch('src.mcp_servers.kph_market_data.client.requests.post')
    def test_fetch_live_content_failure(self, mock_post):
        """测试获取直播内容失败"""
        import requests
        mock_post.side_effect = requests.exceptions.RequestException("网络错误")

        client = KPHClient()
        result = client.fetch_live_content()
        assert result is None

    @patch('src.mcp_servers.kph_market_data.client.requests.post')
    def test_fetch_limit_up_ladder_success(self, mock_post):
        """测试获取涨停天梯成功"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "errcode": "0",
            "Date": "2026-06-14",
            "StockList": [
                ["600519", "贵州茅台", 3, 1623456789, "001", "白酒", 0, 0, 0, 0, 0]
            ],
            "ZhuShuList": [
                ["001", "白酒", 5, 100000000, "600519,000858"]
            ]
        }
        mock_response.headers = {"Content-Type": "application/json"}
        mock_post.return_value = mock_response

        client = KPHClient()
        result = client.fetch_limit_up_ladder()
        assert result is not None
        assert isinstance(result, LimitUpLadderResponse)
        assert result.date == "2026-06-14"

    @patch('src.mcp_servers.kph_market_data.client.requests.post')
    def test_fetch_market_highlights_success(self, mock_post):
        """测试获取盘面亮点成功"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "errcode": "0",
            "date": "2026-06-14",
            "List": [
                {
                    "TimeMin": 1623456789,
                    "TagID": 1,
                    "ZSCode": "000001",
                    "Detail": "测试详情",
                    "TagShuXing": 0,
                    "TagName": "测试标签",
                    "StockList": [["600519", "贵州茅台"]],
                    "ZSName": "测试指数"
                }
            ]
        }
        mock_response.headers = {"Content-Type": "application/json"}
        mock_post.return_value = mock_response

        client = KPHClient()
        result = client.fetch_market_highlights()
        assert result is not None
        assert isinstance(result, MarketHighlightsResponse)
        assert result.date == "2026-06-14"


class TestKPHMarketDataService:
    """测试KPHMarketDataService类"""

    def test_init(self):
        """测试初始化"""
        service = KPHMarketDataService()
        assert service.name == "kph-market-data"
        assert service.version == "1.0.0"

    def test_format_live_content(self):
        """测试格式化直播内容"""
        service = KPHMarketDataService()
        
        # 创建测试数据
        from src.mcp_servers.kph_market_data.models import LiveContentItem
        item = LiveContentItem(
            id="1",
            time=1623456789,
            comment="测试评论",
            user_name="测试用户",
            stock=[["600519", "贵州茅台", 1.5]],
            plate_name="白酒",
            plate_zdf="2.5",
            boom_reason="测试原因",
            interpretation="测试解读"
        )
        
        response = LiveContentResponse(
            items=[item],
            date="2026-06-14",
            notice="测试公告"
        )
        
        result = service._format_live_content(response)
        assert "2026-06-14" in result
        assert "测试公告" in result
        assert "测试评论" in result
        assert "贵州茅台" in result

    def test_format_limit_up_ladder(self):
        """测试格式化涨停天梯"""
        service = KPHMarketDataService()
        
        # 创建测试数据
        from src.mcp_servers.kph_market_data.models import LimitUpStock, LimitUpTheme
        stock = LimitUpStock(
            code="600519",
            name="贵州茅台",
            board_height=3,
            limit_up_time=1623456789,
            theme_name="白酒"
        )
        
        theme = LimitUpTheme(
            name="白酒",
            zt_count=5,
            turnover=100000000
        )
        
        response = LimitUpLadderResponse(
            stocks=[stock],
            themes=[theme],
            date="2026-06-14"
        )
        
        result = service._format_limit_up_ladder(response)
        assert "2026-06-14" in result
        assert "白酒" in result
        assert "贵州茅台" in result
        assert "标签 —" in result

    def test_attach_stock_tags(self):
        service = KPHMarketDataService()
        from src.mcp_servers.kph_market_data.models import LimitUpStock

        stock = LimitUpStock(
            code="600519",
            name="贵州茅台",
            board_height=3,
            limit_up_time=1623456789,
            theme_name="白酒",
        )
        response = LimitUpLadderResponse(stocks=[stock], themes=[], date="2026-06-14")

        with patch(
            "src.mcp_servers.kph_market_data.service.lookup_stock_tags",
            return_value={"600519": "白酒,消费"},
        ):
            service._attach_stock_tags(response)

        assert stock.tags == "白酒,消费"

    def test_format_limit_up_ladder_with_tags(self):
        service = KPHMarketDataService()
        from src.mcp_servers.kph_market_data.models import LimitUpStock, LimitUpTheme

        stock = LimitUpStock(
            code="600519",
            name="贵州茅台",
            board_height=3,
            limit_up_time=1623456789,
            theme_name="白酒",
            tags="白酒,消费",
        )
        theme = LimitUpTheme(name="白酒", zt_count=5, turnover=100000000)
        response = LimitUpLadderResponse(stocks=[stock], themes=[theme], date="2026-06-14")

        result = service._format_limit_up_ladder(response)
        assert "标签 白酒,消费" in result

    def test_format_market_highlights(self):
        """测试格式化盘面亮点"""
        service = KPHMarketDataService()
        
        # 创建测试数据
        from src.mcp_servers.kph_market_data.models import MarketHighlightItem
        item = MarketHighlightItem(
            time_min=1623456789,
            tag_name="测试标签",
            zs_name="测试指数",
            detail="测试详情",
            stock_list=[["600519", "贵州茅台"]]
        )
        
        response = MarketHighlightsResponse(
            items=[item],
            date="2026-06-14"
        )
        
        result = service._format_market_highlights(response)
        assert "2026-06-14" in result
        assert "测试标签" in result
        assert "测试指数" in result
        assert "贵州茅台" in result


if __name__ == "__main__":
    pytest.main([__file__])