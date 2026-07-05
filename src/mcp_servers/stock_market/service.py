"""
A股行情数据MCP服务

提供A股市场数据获取功能，包括：
- 1分钟K线数据（单日K线形状、量能）
- 日K数据（含5/10/20日均线、涨跌停、流通市值）
- 前复权处理
"""

import json
import logging

from ..base import BaseMCPServer
from .data_fetcher import StockDataFetcher

# 配置日志
logger = logging.getLogger(__name__)


class StockMarketService(BaseMCPServer):
    """
    A股行情数据MCP服务

    提供A股市场数据获取功能，基于mootdx实现。
    """

    def __init__(self):
        """初始化A股行情数据服务"""
        super().__init__("stock-market-service", "1.0.0")
        self._data_fetcher = StockDataFetcher()
        self.register_tools()
        self.register_resources()
        logger.info("A股行情数据服务初始化完成")

    def __del__(self):
        """析构函数，关闭连接"""
        if hasattr(self, "_data_fetcher"):
            self._data_fetcher.close()

    def register_tools(self):
        """注册工具方法"""

        @self.mcp.tool()
        def get_minute_kline(stock_code: str = "", stock_name: str = "", count: int = 240, adaptive_threshold: float = 1.0) -> str:
            """
            获取1分钟K线数据

            用于获取单日的K线形状和量能情况。
            数据已进行前复权处理。
            通过 stock_code 或 stock_name 指定股票，优先使用 stock_code。

            Args:
                stock_code: 股票代码，如 "600519"（可选，与 stock_name 二选一）
                stock_name: 股票名称，如 "贵州茅台"（可选，stock_code 为空时使用）
                count: 获取的数据条数，默认240（约1个交易日）
                adaptive_threshold: 自适应提取阈值(如 1.0 表示 1%)，默认 1.0。
                                   如果设置此参数，将只返回满足条件的关键特征点，大幅减少数据量。
                                   设置为 0 或 None 可返回完整数据。

            Returns:
                包含1分钟K线数据的JSON字符串，字段包括：
                - datetime: 时间戳
                - open: 开盘价
                - high: 最高价
                - low: 最低价
                - close: 收盘价
                - volume: 成交量
                - amount: 成交额
                
                如果设置了 adaptive_threshold，还会包含以下字段：
                - type: 触发类型 (open/trigger_pct/new_high/new_low/close)
                - base_price: 触发时的基准价格
                - change_pct_from_base: 相对于基准价格的涨跌幅
            """
            try:
                symbol = self._data_fetcher.resolve_stock_code(stock_code, stock_name)
                logger.info(f"获取1分钟K线数据: {symbol}, 数量: {count}, 阈值: {adaptive_threshold}")
                result = self._data_fetcher.get_minute_data(symbol, count, adaptive_threshold, stock_name)
                return json.dumps(result, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"获取1分钟K线数据失败: {e}")
                return json.dumps({"error": str(e)}, ensure_ascii=False)

        @self.mcp.tool()
        def get_daily_kline(stock_code: str = "", stock_name: str = "", count: int = 120) -> str:
            """
            获取日K线数据

            获取股票的日K线数据，包含以下指标：
            - 5日均线（ma5）
            - 10日均线（ma10）
            - 20日均线（ma20）
            - 昨日收盘价（pre_close）
            - 今日涨停价（limit_up）
            - 今日跌停价（limit_down）
            - 是否涨停（is_limit_up）
            - 是否跌停（is_limit_down）

            数据已进行前复权处理。
            涨跌停价格根据股票代码自动匹配板块比例：
            - 主板：±10%
            - 科创板(688xxx)、创业板(300xxx/301xxx)：±20%
            - 北交所(8开头)：±30%
            - ST股票（名称含ST）：±5%
            通过 stock_code 或 stock_name 指定股票，优先使用 stock_code。

            Args:
                stock_code: 股票代码，如 "600519"（可选，与 stock_name 二选一）
                stock_name: 股票名称，如 "贵州茅台"（可选，stock_code 为空时使用）
                count: 获取的K线数量，默认120

            Returns:
                包含日K线数据的JSON字符串，字段包括：
                - datetime: 日期
                - open: 开盘价
                - high: 最高价
                - low: 最低价
                - close: 收盘价
                - volume: 成交量
                - amount: 成交额
                - ma5: 5日均线
                - ma10: 10日均线
                - ma20: 20日均线
                - pre_close: 昨日收盘价
                - limit_up: 涨停价
                - limit_down: 跌停价
                - is_limit_up: 是否涨停（收盘价 >= 四舍五入后的涨停价）
                - is_limit_down: 是否跌停（收盘价 <= 四舍五入后的跌停价）
            """
            try:
                symbol = self._data_fetcher.resolve_stock_code(stock_code, stock_name)
                logger.info(f"获取日K线数据: {symbol}, 数量: {count}")
                result = self._data_fetcher.get_daily_kline(symbol, count, stock_name=stock_name or "")
                return json.dumps(result, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"获取日K线数据失败: {e}")
                return json.dumps({"error": str(e)}, ensure_ascii=False)

        @self.mcp.tool()
        def get_stock_quote(stock_code: str = "", stock_name: str = "") -> str:
            """
            获取股票实时行情

            通过 stock_code 或 stock_name 指定股票，优先使用 stock_code。

            Args:
                stock_code: 股票代码，如 "600519"（可选，与 stock_name 二选一）
                stock_name: 股票名称，如 "贵州茅台"（可选，stock_code 为空时使用）

            Returns:
                包含股票实时行情信息的JSON字符串
            """
            try:
                symbol = self._data_fetcher.resolve_stock_code(stock_code, stock_name)
                logger.info(f"获取股票实时行情: {symbol}")
                result = self._data_fetcher.get_realtime_quote(symbol)
                return json.dumps(result, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"获取股票实时行情失败: {e}")
                return json.dumps({"error": str(e)}, ensure_ascii=False)

    def register_resources(self):
        """注册资源方法"""

        @self.mcp.resource("stock://service/info")
        def get_service_info() -> str:
            """
            获取服务信息

            Returns:
                包含服务信息的JSON字符串
            """
            return json.dumps(
                {
                    "name": self.name,
                    "version": self.version,
                    "features": [
                        "1分钟K线数据（单日K线形状、量能）",
                        "日K数据（含5/10/20日均线、涨跌停）",
                        "前复权处理",
                    ],
                    "data_source": "mootdx（通达信数据接口）",
                },
                ensure_ascii=False,
                indent=2,
            )

    def run(self, transport: str = "stdio"):
        """
        运行A股行情数据服务

        Args:
            transport: 传输方式
        """
        logger.info(f"启动A股行情数据服务，传输方式: {transport}")
        super().run(transport)
