"""
A股行情数据MCP服务

提供A股市场数据获取功能，包括：
- 1分钟K线数据（单日K线形状、量能）
- 日K数据（含5/10/20日均线、涨跌停、流通市值）
- 前复权处理
- 服务器自动探测和故障转移
"""

import json
import logging
import threading

from ..base import BaseMCPServer
from .data_fetcher import StockDataFetcher
from .server_manager import get_server_manager

# 配置日志
logger = logging.getLogger(__name__)


class StockMarketService(BaseMCPServer):
    """
    A股行情数据MCP服务

    提供A股市场数据获取功能，基于mootdx实现。
    支持服务器自动探测和故障转移。
    """

    def __init__(self):
        """初始化A股行情数据服务"""
        super().__init__("stock-market-service", "1.0.0")

        # 获取服务器管理器（仅创建实例，不阻塞缓存解析/首次探测）
        logger.info("正在初始化服务器管理器...")
        self._server_manager = get_server_manager()

        # 初始化数据获取器（使用服务器管理器模式）
        self._data_fetcher = StockDataFetcher(use_server_manager=True)
        self.register_tools()
        self.register_resources()
        logger.info("A股行情数据服务初始化完成")

        # 后台读取缓存；只有缓存为空时才会执行首次并发探测。
        resolve_thread = threading.Thread(target=self._resolve_servers, daemon=True)
        resolve_thread.start()

    def __del__(self):
        """析构函数，关闭连接"""
        if hasattr(self, "_data_fetcher"):
            self._data_fetcher.close()

    def _resolve_servers(self):
        """后台解析服务器缓存，缓存为空时执行首次探测。"""
        try:
            if self._server_manager.start():
                logger.info(
                    "服务器解析完成，来源: %s，可用服务器: %d 台",
                    self._server_manager.get_server_source(),
                    self._server_manager.get_server_count(),
                )
            else:
                logger.warning("服务器解析未找到可用服务器")
        except Exception as e:
            logger.error("服务器解析异常: %s", e)

    def register_tools(self):
        """注册工具方法"""

        @self._tool(structured_output=False)
        def get_minute_kline(stock_code: str = "", stock_name: str = "", date: str = "", adaptive_threshold: float = 1.0) -> str:
            """
            获取单只股票指定交易日的1分钟K线（分时形状与量能，前复权）。
            date 格式 YYYY-MM-DD，留空=最近交易日；adaptive_threshold 默认1.0即抽点（只保留关键转折点），传0保留全量点。
            """
            try:
                symbol = self._data_fetcher.resolve_stock_code(stock_code, stock_name)
                logger.info(f"获取1分钟K线数据: {symbol}, 日期: {date or '最近交易日'}, 阈值: {adaptive_threshold}")
                result = self._data_fetcher.get_minute_data(symbol, date, adaptive_threshold, stock_name)
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                logger.error(f"获取1分钟K线数据失败: {e}")
                return json.dumps({"error": str(e)}, ensure_ascii=False)

        @self._tool(structured_output=False)
        def get_minute_kline_batch(stocks: list | None = None, date: str = "", adaptive_threshold: float = 1.0) -> str:
            """
            批量获取多只股票同一交易日的1分钟K线（5线程并发，单只失败不影响其余）。
            stocks 每项 {“code”：“600602”,“name”：“云赛智联”}，单次最多30只；date 留空=最近交易日。
            """
            try:
                if not stocks:
                    return json.dumps(
                        {
                            "date": "",
                            "results": [],
                            "errors": [{"code": "", "name": "", "reason": "stocks 参数为空"}],
                            "meta": {"total": 0, "success": 0, "failed": 1, "workers": 0, "nodes": []},
                        },
                        ensure_ascii=False,
                    )
                # 单次最多 30 只，防止超时/超长响应
                stocks = stocks[:30]
                logger.info(
                    "批量获取1分钟K线数据: %d 只, 日期: %s, 阈值: %s",
                    len(stocks),
                    date or "最近交易日",
                    adaptive_threshold,
                )
                result = self._data_fetcher.get_minute_data_batch(
                    stocks, date, adaptive_threshold, max_workers=5
                )
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                logger.error(f"批量获取1分钟K线数据失败: {e}")
                return json.dumps(
                    {
                        "date": "",
                        "results": [],
                        "errors": [{"code": "", "name": "", "reason": str(e)}],
                        "meta": {"total": 0, "success": 0, "failed": 1, "workers": 0, "nodes": []},
                    },
                    ensure_ascii=False,
                )

        @self._tool(structured_output=False)
        def get_daily_kline(stock_code: str = "", stock_name: str = "", count: int = 120) -> str:
            """
            获取股票日K线（前复权，含 ma5/ma10/ma20、涨跌停价与是否涨跌停）。
            count 默认120；stock_code 或 stock_name 二选一，优先 stock_code。
            """
            try:
                symbol = self._data_fetcher.resolve_stock_code(stock_code, stock_name)
                logger.info(f"获取日K线数据: {symbol}, 数量: {count}")
                result = self._data_fetcher.get_daily_kline(symbol, count, stock_name=stock_name or "")
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                logger.error(f"获取日K线数据失败: {e}")
                return json.dumps({"error": str(e)}, ensure_ascii=False)

        @self._tool(structured_output=False)
        def get_stock_quote(stock_code: str = "", stock_name: str = "") -> str:
            """
            获取股票实时行情。
            stock_code 或 stock_name 二选一，优先 stock_code。
            """
            try:
                symbol = self._data_fetcher.resolve_stock_code(stock_code, stock_name)
                logger.info(f"获取股票实时行情: {symbol}")
                result = self._data_fetcher.get_realtime_quote(symbol)
                return json.dumps(result, ensure_ascii=False)
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
