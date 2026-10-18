"""
开盘红平台行情数据MCP服务

提供大盘直播、涨停天梯、盘面亮点的实时和历史数据查询
"""

import logging
from datetime import datetime

from ..base import BaseMCPServer
from .client import KPHClient
from .models import (
    LimitUpLadderResponse,
    LiveContentResponse,
    MarketHighlightsResponse,
)
from .stock_tags import lookup_stock_tags
from star_stocks.external.kaipanhong import normalize_stock_code

# 配置日志
logger = logging.getLogger(__name__)


class KPHMarketDataService(BaseMCPServer):
    """
    开盘红平台行情数据MCP服务

    提供大盘直播、涨停天梯、盘面亮点的实时和历史数据查询
    """

    def __init__(self):
        """初始化开盘红平台行情数据服务"""
        super().__init__("kph-market-data", "1.0.0")
        self._client = KPHClient()
        self.register_tools()
        self.register_resources()
        logger.info("开盘红平台行情数据服务初始化完成")

    def register_tools(self):
        """注册工具方法"""

        @self._tool()
        def get_live_content(index: int = 0) -> str:
            """
            获取当日大盘直播流信息（盘面解读、关联个股/板块、概念爆发原因）。
            index 分页起始位置，默认0（最新数据）。
            """
            try:
                logger.info(f"获取实时大盘直播数据，index: {index}")
                resp = self._client.fetch_live_content(index=index)
                if resp is None:
                    return "请求失败: 无法获取实时大盘直播数据，请检查网络连接。"
                return self._format_live_content(resp)
            except Exception as e:
                logger.error(f"获取实时大盘直播数据失败: {e}")
                return f"请求失败: {str(e)}"

        @self._tool()
        def get_limit_up_ladder() -> str:
            """
            获取当日涨停天梯数据（涨停题材排名与连板个股列表，含题材涨停家数、连板高度、涨停时间、个股标签）。
            """
            try:
                logger.info("获取实时涨停天梯数据")
                resp = self._client.fetch_limit_up_ladder()
                if resp is None:
                    return "请求失败: 无法获取实时涨停天梯数据，请检查网络连接。"
                self._attach_stock_tags(resp)
                return self._format_limit_up_ladder(resp)
            except Exception as e:
                logger.error(f"获取实时涨停天梯数据失败: {e}")
                return f"请求失败: {str(e)}"

        @self._tool()
        def get_market_highlights(index: int = 0, limit: int = 30) -> str:
            """
            获取当日盘面亮点事件列表（时间节点、标签类型、所属题材、关联个股）。
            index 默认0；limit 返回条数，默认30。
            """
            try:
                logger.info(f"获取实时盘面亮点数据，index: {index}, limit: {limit}")
                resp = self._client.fetch_market_highlights(index=index, limit=limit)
                if resp is None:
                    return "请求失败: 无法获取实时盘面亮点数据，请检查网络连接。"
                return self._format_market_highlights(resp)
            except Exception as e:
                logger.error(f"获取实时盘面亮点数据失败: {e}")
                return f"请求失败: {str(e)}"

        @self._tool()
        def get_historical_live_content(date: str, index: int = 0, st: int = 0) -> str:
            """
            获取指定历史日期的大盘直播流信息（概念点接口），用于复盘历史盘面。
            date 必填，格式 YYYY-MM-DD；index 默认0；st 返回条数限制，0表示不限制。
            """
            try:
                logger.info(f"获取历史大盘直播数据，date: {date}, index: {index}, st: {st}")
                resp = self._client.fetch_historical_live_content(date=date, index=index, st=st)
                if resp is None:
                    return f"请求失败: 无法获取 {date} 的历史大盘直播数据，请检查日期是否正确。"
                return self._format_live_content(resp)
            except Exception as e:
                logger.error(f"获取历史大盘直播数据失败: {e}")
                return f"请求失败: {str(e)}"

        @self._tool()
        def get_historical_limit_up_ladder(date: str) -> str:
            """
            获取指定历史日期的涨停天梯数据（涨停题材排名与连板个股列表）。
            date 必填，格式 YYYY-MM-DD。
            """
            try:
                logger.info(f"获取历史涨停天梯数据，date: {date}")
                resp = self._client.fetch_historical_limit_up_ladder(date=date)
                if resp is None:
                    return f"请求失败: 无法获取 {date} 的历史涨停天梯数据，请检查日期是否正确。"
                self._attach_stock_tags(resp)
                return self._format_limit_up_ladder(resp)
            except Exception as e:
                logger.error(f"获取历史涨停天梯数据失败: {e}")
                return f"请求失败: {str(e)}"

        @self._tool()
        def get_historical_market_highlights(
            date: str, index: int = 0, limit: int = 30
        ) -> str:
            """
            获取指定历史日期的盘面亮点事件列表（时间节点、标签类型、所属题材、关联个股）。
            date 必填，格式 YYYY-MM-DD；index 默认0；limit 返回条数，默认30。
            """
            try:
                logger.info(f"获取历史盘面亮点数据，date: {date}, index: {index}, limit: {limit}")
                resp = self._client.fetch_historical_market_highlights(
                    date=date, index=index, limit=limit
                )
                if resp is None:
                    return f"请求失败: 无法获取 {date} 的历史盘面亮点数据，请检查日期是否正确。"
                return self._format_market_highlights(resp)
            except Exception as e:
                logger.error(f"获取历史盘面亮点数据失败: {e}")
                return f"请求失败: {str(e)}"

    def register_resources(self):
        """注册资源方法"""

        @self.mcp.resource("kph://service/info")
        def get_service_info() -> str:
            """
            获取服务信息

            Returns:
                包含服务信息的JSON字符串
            """
            import json
            return json.dumps(
                {
                    "name": self.name,
                    "version": self.version,
                    "features": [
                        "大盘直播内容（实时+历史）",
                        "涨停天梯数据（实时+历史）",
                        "盘面亮点数据（实时+历史）",
                    ],
                    "data_source": "开盘红平台",
                },
                ensure_ascii=False,
                indent=2,
            )

    def _format_live_content(self, resp: LiveContentResponse) -> str:
        """将直播内容响应格式化为可读文本"""
        lines: list[str] = []
        lines.append(f"日期: {resp.date}")
        lines.append(f"公告: {resp.notice}")
        lines.append(f"共 {len(resp.items)} 条记录\n")

        for item in resp.items:
            timestamp = datetime.fromtimestamp(item.time).strftime("%H:%M:%S") if item.time else ""
            lines.append(f"[{timestamp}] {item.user_name}: {item.comment}")

            if item.stock:
                stocks = ", ".join(
                    f"{s[1]}({s[0]})" + (f" {'+' if s[2] >= 0 else ''}{s[2]}%" if len(s) > 2 else "")
                    for s in item.stock
                )
                lines.append(f"  关联个股: {stocks}")

            if item.plate_name:
                lines.append(f"  关联板块: {item.plate_name} {item.plate_zdf}%")

            if item.boom_reason:
                lines.append(f"  爆发原因: {item.boom_reason}")

            if item.interpretation:
                lines.append(f"  解读: {item.interpretation}")

            lines.append("")

        return "\n".join(lines)

    def _attach_stock_tags(self, resp: LimitUpLadderResponse) -> None:
        codes = [stock.code for stock in resp.stocks if stock.code]
        tags_map = lookup_stock_tags(codes)
        for stock in resp.stocks:
            stock.tags = tags_map.get(normalize_stock_code(stock.code))

    def _format_limit_up_ladder(self, resp: LimitUpLadderResponse) -> str:
        """将涨停天梯响应格式化为可读文本"""
        lines: list[str] = []
        lines.append(f"日期: {resp.date}")
        lines.append(f"涨停题材 {len(resp.themes)} 个，涨停个股 {len(resp.stocks)} 只\n")

        lines.append("=== 涨停题材 ===")
        for theme in sorted(resp.themes, key=lambda t: t.zt_count, reverse=True):
            lines.append(f"  {theme.name}: {theme.zt_count}家涨停, 成交额 {theme.turnover / 1e8:.2f}亿")

        lines.append("\n=== 连板个股（按连板高度排序）===")
        for stock in sorted(resp.stocks, key=lambda s: s.board_height, reverse=True):
            if stock.board_height >= 1:
                t = datetime.fromtimestamp(stock.limit_up_time).strftime("%H:%M:%S") if stock.limit_up_time else ""
                tags = stock.tags or "—"
                lines.append(
                    f"  {stock.name}({stock.code}): {stock.board_height}连板 "
                    f"| 涨停时间 {t} | 题材 {stock.theme_name} | 标签 {tags}"
                )

        return "\n".join(lines)

    def _format_market_highlights(self, resp: MarketHighlightsResponse) -> str:
        """将盘面亮点响应格式化为可读文本"""
        lines: list[str] = []
        lines.append(f"日期: {resp.date}")
        lines.append(f"共 {len(resp.items)} 条盘面亮点\n")

        for item in resp.items:
            timestamp = datetime.fromtimestamp(item.time_min).strftime("%H:%M") if item.time_min else ""
            stocks = ", ".join(f"{s[1]}({s[0]})" for s in item.stock_list) if item.stock_list else ""
            lines.append(f"[{timestamp}] [{item.tag_name}] {item.zs_name}")
            lines.append(f"  {item.detail}")
            if stocks:
                lines.append(f"  关联个股: {stocks}")
            lines.append("")

        return "\n".join(lines)

    def run(self, transport: str = "stdio"):
        """
        运行开盘红平台行情数据服务

        Args:
            transport: 传输方式
        """
        logger.info(f"启动开盘红平台行情数据服务，传输方式: {transport}")
        super().run(transport)