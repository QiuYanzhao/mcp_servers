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

        @self.mcp.tool(structured_output=False)
        def get_minute_kline(stock_code: str = "", stock_name: str = "", date: str = "", adaptive_threshold: float = 1.0) -> str:
            """
            获取指定交易日的1分钟K线数据

            用于获取单个交易日的分时形状与量能（只返回目标日当天，不会跨日）。
            数据已进行前复权处理（前复权基准=最新交易日）。
            通过 stock_code 或 stock_name 指定股票，优先使用 stock_code。

            Args:
                stock_code: 股票代码，如 "600519"（可选，与 stock_name 二选一）
                stock_name: 股票名称，如 "贵州茅台"（可选，stock_code 为空时使用）
                date: 目标交易日，格式 YYYY-MM-DD（如 "2026-10-16"）。
                      留空=最近交易日；盘前当日尚无数据时自动回退到上一交易日。
                      非交易日/未来日期/停牌日会返回明确错误。
                adaptive_threshold: 抽点阈值(如 1.0 表示 1%)，默认 1.0——默认即抽点
                                   （非 None 即抽点，只返回关键特征点）。传 0 保留全部点；
                                   传 None 会被参数校验拒绝。

            Returns:
                包含1分钟K线数据的JSON字符串：
                {"symbol", "date", "frequency", "count", "data": [...]}
                - date: 实际返回的交易日（YYYY-MM-DD），请求留空时以此确认拿到哪一天
                - count: 实际返回的点数
                - frequency: adaptive_1min（抽点结果）/ 1min（全量）
                data 每项字段（默认即抽点，只保留关键转折点；传 adaptive_threshold=0 时保留全量点）：
                - time: HH:mm（由原 datetime 截取）
                - open/high/low/close: 该分钟价格（前复权，2位小数）
                - volume: 该分钟成交量
                - change_pct: (该点分钟收盘价 - 目标日昨收)/昨收*100，2位小数；全部点同一基准
                - type: 抽点模式下每点都有，标明该点为何被保留
                  (open 首点 / trigger_pct 波动达阈值 / new_high 极值高点 / new_low 极值低点 / close 末点)
                - is_limit_up: 仅 type=new_high 的点返回，该分钟最高价是否触及涨停价
                - is_limit_down: 仅 type=new_low 的点返回，该分钟最低价是否触及跌停价
            """
            try:
                symbol = self._data_fetcher.resolve_stock_code(stock_code, stock_name)
                logger.info(f"获取1分钟K线数据: {symbol}, 日期: {date or '最近交易日'}, 阈值: {adaptive_threshold}")
                result = self._data_fetcher.get_minute_data(symbol, date, adaptive_threshold, stock_name)
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                logger.error(f"获取1分钟K线数据失败: {e}")
                return json.dumps({"error": str(e)}, ensure_ascii=False)

        @self.mcp.tool(structured_output=False)
        def get_minute_kline_batch(stocks: list | None = None, date: str = "", adaptive_threshold: float = 1.0) -> str:
            """
            批量获取指定交易日的1分钟K线数据（5线程并发，每线程独立通达信数据节点）

            用于复盘等场景批量拉取多只个股在同一交易日的日内K线形状与量能。
            内部按 5 个线程并发拉取，每个线程绑定不同的通达信数据节点分散负载；
            单只股票失败不影响其余股票（失败项进入 errors 列表）。

            Args:
                stocks: 股票列表，每项为 {"code": "600602", "name": "云赛智联"}，
                       name 可选。单次最多 30 只。
                date: 目标交易日，格式 YYYY-MM-DD。留空=最近交易日（整批统一使用该日期）；
                      盘前当日尚无数据时自动回退到上一交易日。非交易日/未来日期返回明确错误。
                adaptive_threshold: 抽点阈值(如 1.0 表示 1%)，默认 1.0——默认即抽点
                                   （非 None 即抽点，只返回关键特征点）。传 0 保留全部点。

            Returns:
                包含 date/results/errors/meta 的JSON字符串：
                - date: 本批统一使用的交易日
                - results: [{"code", "name", "symbol", "date", "frequency", "count", "data"}]
                  data 每项字段：time(HH:mm)/open/high/low/close/volume/change_pct（+type；is_limit_up/is_limit_down 分别仅 new_high/new_low 点返回，自适应模式下）
                  results 顺序不保证与传入 stocks 一致，按 code 匹配
                - errors: [{"code", "name", "reason"}]
                - meta: {"total", "success", "failed", "workers", "nodes"}
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

        @self.mcp.tool(structured_output=False)
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
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                logger.error(f"获取日K线数据失败: {e}")
                return json.dumps({"error": str(e)}, ensure_ascii=False)

        @self.mcp.tool(structured_output=False)
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
