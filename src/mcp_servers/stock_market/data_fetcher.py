"""
A股行情数据获取模块

使用mootdx获取A股行情数据，支持：
- 1分钟K线数据（单日）
- 日K数据（含均线、涨跌停、流通市值）
- 前复权处理
- 服务器自动探测和故障转移
"""

import json
import logging
import os
from typing import Dict, List, Optional, Tuple

import pandas as pd
from mootdx.quotes import Quotes

from .server_manager import (
    PROBE_EMPTY_ERROR,
    TdxServerManager,
    TdxServersUnavailableError,
    get_server_manager,
)

# 配置日志
logger = logging.getLogger(__name__)

# 涨跌停计算常量
DEFAULT_LIMIT_RATIO = 0.10  # 主板涨跌停比例10%（默认）
LIMIT_PRICE_TOLERANCE = 0.005  # 涨停价比较容差（半分钱，适配价格最小变动单位）

# 默认服务器（通达信服务器）
DEFAULT_SERVER = "119.147.212.81:7709"

# 最大重试次数（切换服务器）
MAX_RETRY_COUNT = 3


class StockDataFetcher:
    """
    A股行情数据获取类

    使用mootdx获取A股行情数据，提供前复权处理和指标计算功能。
    支持服务器自动探测和故障转移。
    """

    def __init__(self, server: str = DEFAULT_SERVER, use_server_manager: bool = True):
        """
        初始化数据获取器

        Args:
            server: 通达信服务器地址，格式 "ip:port"（当 use_server_manager=False 时使用）
            use_server_manager: 是否使用服务器管理器（默认True，启用自动探测和故障转移）
        """
        self._server = server
        self._use_server_manager = use_server_manager
        self._client: Optional[Quotes] = None
        self._current_server: Optional[Tuple[str, int]] = None
        self._stock_name_to_code: Dict[str, str] = {}
        self._load_stock_list()

        if use_server_manager:
            logger.info("StockDataFetcher 初始化，启用服务器管理器模式")
        else:
            logger.info("StockDataFetcher 初始化，使用固定服务器: %s", server)

    # 通达信行情服务器列表（备用，当服务器管理器不可用时使用）
    _TDX_SERVERS = [
        ("110.41.147.114", 7709),
        ("47.113.94.204", 7709),
        ("124.70.176.52", 7709),
        ("121.36.54.217", 7709),
    ]

    @staticmethod
    def _get_limit_ratio(symbol: str, stock_name: str = "") -> float:
        """
        根据股票代码和名称动态计算涨跌停比例

        规则：
        - ST / *ST 股票 → 5%
        - 科创板（688xxx）→ 20%
        - 创业板（300xxx, 301xxx）→ 20%
        - 北交所（8开头，如83xxxx, 87xxxx）→ 30%
        - 其余主板 → 10%

        Args:
            symbol: 股票代码，如 "600519"
            stock_name: 股票名称，用于检测ST

        Returns:
            涨跌停比例（如 0.10 表示 ±10%）
        """
        # 通过名称检测ST
        if stock_name and ("ST" in stock_name.upper() or "*ST" in stock_name.upper()):
            return 0.05

        # 通过代码前缀区分板块
        code = symbol.strip()
        if code.startswith("688"):
            return 0.20  # 科创板
        if code.startswith(("300", "301")):
            return 0.20  # 创业板
        if code.startswith("8"):
            return 0.30  # 北交所

        return DEFAULT_LIMIT_RATIO  # 主板

    @staticmethod
    def _calc_limit_up_price(pre_close: float, ratio: float) -> float:
        """计算涨停价（按交易所规则四舍五入到分）"""
        return round(pre_close * (1 + ratio), 2)

    @staticmethod
    def _calc_limit_down_price(pre_close: float, ratio: float) -> float:
        """计算跌停价（按交易所规则四舍五入到分）"""
        return round(pre_close * (1 - ratio), 2)

    @staticmethod
    def _is_at_limit_up(close: float, limit_up: float) -> bool:
        """判断收盘价是否封涨停"""
        return close >= limit_up - LIMIT_PRICE_TOLERANCE

    @staticmethod
    def _is_at_limit_down(close: float, limit_down: float) -> bool:
        """判断收盘价是否封跌停"""
        return close <= limit_down + LIMIT_PRICE_TOLERANCE

    def _get_client(self, force_reconnect: bool = False) -> Quotes:
        """
        获取或创建行情客户端

        Args:
            force_reconnect: 是否强制重新连接

        Returns:
            Quotes实例
        """
        if self._client is not None and not force_reconnect:
            return self._client

        # 关闭旧连接
        if self._client is not None:
            try:
                self._client.close()
            except Exception as e:
                logger.debug("关闭旧连接异常: %s", e)
            self._client = None

        # 使用服务器管理器模式
        if self._use_server_manager:
            return self._get_client_from_manager()

        # 使用固定服务器模式
        return self._get_client_from_fixed_server()

    def _get_client_from_manager(self) -> Quotes:
        """
        从服务器管理器获取客户端

        Returns:
            Quotes实例
        """
        manager = get_server_manager()
        server = manager.get_current_server()

        if server is None:
            # 服务启动探测在线程中执行，请求抢先到达时同步完成缓存解析。
            logger.info("服务器列表尚未初始化，立即解析缓存服务器")
            if not manager.resolve():
                raise TdxServersUnavailableError(PROBE_EMPTY_ERROR)
            server = manager.get_current_server()
            if server is None:
                raise TdxServersUnavailableError(PROBE_EMPTY_ERROR)

        host, port = server
        try:
            logger.info("连接通达信服务器: %s:%d (来自服务器管理器)", host, port)
            self._client = Quotes.factory(
                market="std",
                server=(host, port),
                timeout=15,
            )
            self._current_server = (host, port)
            logger.info("成功连接通达信服务器: %s:%d", host, port)
            return self._client
        except Exception as e:
            logger.warning("连接服务器管理器当前服务器 %s:%d 失败: %s", host, port, e)
            # 尝试切换到下一个服务器
            return self._try_next_server(manager, e)

    def _try_next_server(self, manager: TdxServerManager, last_error: Exception) -> Quotes:
        """
        尝试连接下一个可用服务器

        Args:
            manager: 服务器管理器
            last_error: 上一个错误

        Returns:
            Quotes实例

        Raises:
            ConnectionError: 所有服务器都不可用
        """
        server_count = manager.get_server_count()
        for i in range(server_count - 1):  # 已经尝试过一台，所以减1
            next_server = manager.switch_to_next_server()
            if next_server is None:
                break

            host, port = next_server
            try:
                logger.info("尝试连接下一个服务器: %s:%d", host, port)
                self._client = Quotes.factory(
                    market="std",
                    server=(host, port),
                    timeout=15,
                )
                self._current_server = (host, port)
                logger.info("成功连接通达信服务器: %s:%d", host, port)
                return self._client
            except Exception as e:
                logger.warning("连接 %s:%d 失败: %s", host, port, e)
                last_error = e

        raise ConnectionError(
            f"无法连接任何通达信服务器，最后错误: {last_error}"
        )

    def _get_client_from_fixed_server(self) -> Quotes:
        """
        从固定服务器列表获取客户端

        Returns:
            Quotes实例
        """
        # 首先尝试配置的默认服务器
        try:
            host, port = self._server.split(":")
            logger.info("尝试连接默认服务器: %s:%s", host, port)
            self._client = Quotes.factory(
                market="std",
                server=(host, int(port)),
                timeout=15,
            )
            self._current_server = (host, int(port))
            logger.info("成功连接默认服务器: %s:%s", host, port)
            return self._client
        except Exception as e:
            logger.warning("连接默认服务器 %s 失败: %s", self._server, e)

        # 尝试备用服务器列表
        last_error = None
        for host, port in self._TDX_SERVERS:
            try:
                logger.info("尝试连接备用服务器: %s:%d", host, port)
                self._client = Quotes.factory(
                    market="std",
                    server=(host, port),
                    timeout=15,
                )
                self._current_server = (host, port)
                logger.info("成功连接备用服务器: %s:%d", host, port)
                return self._client
            except Exception as e:
                last_error = e
                logger.warning("连接 %s:%d 失败: %s", host, port, e)

        raise ConnectionError(
            f"无法连接任何通达信服务器，最后错误: {last_error}"
        )

    def close(self):
        """关闭连接"""
        if self._client is not None:
            try:
                self._client.close()
            except Exception as e:
                logger.debug("关闭连接异常: %s", e)
            self._client = None
            self._current_server = None
            logger.info("关闭mootdx行情客户端")

    def _execute_with_retry(self, operation_name: str, func, *args, **kwargs):
        """
        执行操作并在失败时自动重试（切换服务器）

        Args:
            operation_name: 操作名称（用于日志）
            func: 要执行的函数
            *args, **kwargs: 函数参数

        Returns:
            函数执行结果
        """
        last_error = None
        for attempt in range(MAX_RETRY_COUNT):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                logger.warning(
                    "%s 失败 (尝试 %d/%d): %s",
                    operation_name,
                    attempt + 1,
                    MAX_RETRY_COUNT,
                    e,
                )

                # 缓存首选服务器实际取数失败后，才执行全量探测并更新缓存。
                if self._use_server_manager and attempt < MAX_RETRY_COUNT - 1:
                    manager = get_server_manager()
                    if manager.should_refresh_on_failure():
                        # 并发探测结果为空时立即抛错，不再继续重试。
                        manager.refresh_on_failure()
                    elif manager.switch_to_next_server() is None:
                        raise TdxServersUnavailableError(
                            "已无可用通达信服务器可切换"
                        )

                    # 关闭失败连接，下一次尝试会连接刷新后列表的当前服务器。
                    if self._client is not None:
                        try:
                            self._client.close()
                        except Exception as close_error:
                            logger.debug("关闭失败连接异常: %s", close_error)
                    self._client = None
                    self._current_server = None
                    continue

                raise

        raise last_error

    def get_minute_data(self, symbol: str, count: int = 240, adaptive_threshold: float = 1.0, stock_name: str = "") -> Dict:
        """
        获取1分钟K线数据

        Args:
            symbol: 股票代码，如 "600519"
            count: 获取的数据条数，默认240（约1个交易日）
            adaptive_threshold: 自适应提取阈值(如 1.0 表示 1%)，默认 1.0。
                               如果设置此参数，将只返回满足条件的关键特征点。
                               设置为 0 或 None 可返回完整数据。
            stock_name: 股票名称，用于辅助判断涨跌停（ST股）

        Returns:
            包含1分钟K线数据的字典
        """
        def _fetch_minute_data():
            client = self._get_client()
            logger.info("获取%s的1分钟K线数据，数量: %d", symbol, count)

            # 获取1分钟K线数据 (frequency=7 对应1分钟线)
            df = client.bars(symbol=symbol, frequency=7, offset=count)

            if df is None or df.empty:
                logger.warning("未获取到%s的1分钟K线数据", symbol)
                raise ConnectionError("未获取到1分钟K线数据")

            # 前复权处理
            df = self._apply_qfq(client, symbol, df)

            # 转换数据格式
            data_list = []
            for _, row in df.iterrows():
                data_list.append(
                    {
                        "datetime": str(row.get("datetime", "")),
                        "open": round(float(row.get("open", 0)), 2),
                        "high": round(float(row.get("high", 0)), 2),
                        "low": round(float(row.get("low", 0)), 2),
                        "close": round(float(row.get("close", 0)), 2),
                        "volume": int(row.get("volume", row.get("vol", 0))),
                        "amount": round(float(row.get("amount", 0)), 2),
                    }
                )

            # 如果设置了自适应阈值，则提取关键特征点
            if adaptive_threshold is not None:
                logger.info("对%s应用自适应提取，阈值: %s%%", symbol, adaptive_threshold)

                # 获取昨收以便判断涨跌停
                pre_close = 0.0
                try:
                    daily_data = self.get_daily_kline(symbol, count=2, include_ma=False, include_limit=False)
                    if daily_data and not daily_data.get("error") and daily_data.get("data"):
                        # 取最后一条日线的收盘价作为 pre_close
                        if len(daily_data["data"]) >= 2:
                            pre_close = daily_data["data"][-2]["close"]
                        elif len(daily_data["data"]) == 1:
                            quote = self.get_realtime_quote(symbol)
                            if quote and not quote.get("error"):
                                pre_close = quote.get("last_close", 0.0)
                except Exception as e:
                    logger.warning("获取昨收数据失败，涨跌停判断可能不准确: %s", e)

                data_list = self.extract_adaptive_kline(data_list, adaptive_threshold, pre_close, stock_name)
                return {
                    "symbol": symbol,
                    "frequency": "adaptive_1min",
                    "count": len(data_list),
                    "data": data_list,
                }

            return {
                "symbol": symbol,
                "frequency": "1min",
                "count": len(data_list),
                "data": data_list,
            }

        try:
            return self._execute_with_retry(
                f"获取{symbol}的1分钟K线数据",
                _fetch_minute_data,
            )
        except Exception as e:
            logger.error("获取%s的1分钟K线数据失败: %s", symbol, e)
            return {"error": str(e), "data": []}

    def get_daily_kline(
        self,
        symbol: str,
        count: int = 120,
        include_ma: bool = True,
        include_limit: bool = True,
        stock_name: str = "",
    ) -> Dict:
        """
        获取日K线数据

        Args:
            symbol: 股票代码，如 "600519"
            count: 获取的数据条数，默认120
            include_ma: 是否计算均线（5、10、20日）
            include_limit: 是否计算涨跌停价格
            stock_name: 股票名称，用于区分ST股票（可选）

        Returns:
            包含日K线数据的字典
        """
        def _fetch_daily_kline():
            client = self._get_client()
            logger.info("获取%s的日K线数据，数量: %d", symbol, count)

            # 获取日K线数据 (frequency=9 对应日线)
            df = client.bars(symbol=symbol, frequency=9, offset=count)

            if df is None or df.empty:
                logger.warning("未获取到%s的日K线数据", symbol)
                raise ConnectionError("未获取到日K线数据")

            # 前复权处理
            df = self._apply_qfq(client, symbol, df)

            # 确保列名一致（mootdx返回的列名可能是close或vol）
            close_col = "close" if "close" in df.columns else "close"
            vol_col = "volume" if "volume" in df.columns else "vol"

            # 计算均线
            if include_ma:
                df["ma5"] = df[close_col].rolling(window=5).mean()
                df["ma10"] = df[close_col].rolling(window=10).mean()
                df["ma20"] = df[close_col].rolling(window=20).mean()

            # 计算昨日收盘价
            df["pre_close"] = df[close_col].shift(1)

            # 计算涨跌停价格（按交易所规则四舍五入到分，再判断封板状态）
            if include_limit:
                ratio = self._get_limit_ratio(symbol, stock_name)
                df["limit_up"] = df["pre_close"].apply(
                    lambda p: self._calc_limit_up_price(p, ratio) if pd.notna(p) else None
                )
                df["limit_down"] = df["pre_close"].apply(
                    lambda p: self._calc_limit_down_price(p, ratio) if pd.notna(p) else None
                )
                df["is_limit_up"] = df.apply(
                    lambda r: self._is_at_limit_up(r[close_col], r["limit_up"])
                    if pd.notna(r.get("limit_up"))
                    else False,
                    axis=1,
                )
                df["is_limit_down"] = df.apply(
                    lambda r: self._is_at_limit_down(r[close_col], r["limit_down"])
                    if pd.notna(r.get("limit_down"))
                    else False,
                    axis=1,
                )

            # 转换数据格式
            data_list = []
            for _, row in df.iterrows():
                item = {
                    "datetime": str(row.get("datetime", "")),
                    "open": round(float(row.get("open", 0)), 2),
                    "high": round(float(row.get("high", 0)), 2),
                    "low": round(float(row.get("low", 0)), 2),
                    "close": round(float(row.get(close_col, 0)), 2),
                    "volume": int(row.get(vol_col, 0)),
                    "amount": round(float(row.get("amount", 0)), 2),
                }

                # 添加均线数据
                if include_ma:
                    item["ma5"] = (
                        round(float(row["ma5"]), 2)
                        if pd.notna(row.get("ma5"))
                        else None
                    )
                    item["ma10"] = (
                        round(float(row["ma10"]), 2)
                        if pd.notna(row.get("ma10"))
                        else None
                    )
                    item["ma20"] = (
                        round(float(row["ma20"]), 2)
                        if pd.notna(row.get("ma20"))
                        else None
                    )

                # 添加昨日收盘价
                item["pre_close"] = (
                    round(float(row["pre_close"]), 2)
                    if pd.notna(row.get("pre_close"))
                    else None
                )

                # 添加涨跌停价格和状态
                if include_limit:
                    item["limit_up"] = (
                        round(float(row["limit_up"]), 2)
                        if pd.notna(row.get("limit_up"))
                        else None
                    )
                    item["limit_down"] = (
                        round(float(row["limit_down"]), 2)
                        if pd.notna(row.get("limit_down"))
                        else None
                    )
                    item["is_limit_up"] = (
                        bool(row["is_limit_up"])
                        if pd.notna(row.get("limit_up"))
                        else None
                    )
                    item["is_limit_down"] = (
                        bool(row["is_limit_down"])
                        if pd.notna(row.get("limit_down"))
                        else None
                    )

                data_list.append(item)

            return {
                "symbol": symbol,
                "frequency": "daily",
                "count": len(data_list),
                "adjust": "qfq",  # 前复权
                "indicators": {
                    "ma": ["ma5", "ma10", "ma20"] if include_ma else [],
                    "pre_close": True,
                    "limit": ["limit_up", "limit_down", "is_limit_up", "is_limit_down"]
                    if include_limit
                    else [],
                },
                "data": data_list,
            }

        try:
            return self._execute_with_retry(
                f"获取{symbol}的日K线数据",
                _fetch_daily_kline,
            )
        except Exception as e:
            logger.error("获取%s的日K线数据失败: %s", symbol, e)
            return {"error": str(e), "data": []}

    def _apply_qfq(
        self, client: Quotes, symbol: str, df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        应用前复权处理

        Args:
            client: Quotes实例
            symbol: 股票代码
            df: 原始K线数据

        Returns:
            前复权后的DataFrame
        """
        try:
            # 获取除权除息数据
            xdxr = client.xdxr(symbol=symbol)

            if xdxr is None or xdxr.empty:
                logger.info(f"{symbol}无除权除息数据，返回原始数据")
                return df

            # 应用前复权
            from mootdx.utils.adjust import to_qfq

            adjusted_df = to_qfq(df, xdxr)
            logger.info(f"{symbol}已完成前复权处理")
            return adjusted_df

        except Exception as e:
            logger.warning(f"{symbol}前复权处理失败，返回原始数据: {e}")
            return df

    def extract_adaptive_kline(self, data_list: List[Dict], threshold_pct: float = 1.0, pre_close: float = 0.0, stock_name: str = "") -> List[Dict]:
        """
        提取自适应 K线数据 (1% 波动 + 极值提取)
        
        Args:
            data_list: 1分钟 K线数据列表
            threshold_pct: 触发阈值百分比，默认 1.0%
            pre_close: 前收盘价，用于计算涨跌停
            stock_name: 股票名称，用于判断ST股
            
        Returns:
            提取后的关键特征点列表
        """
        if not data_list:
            return []

        # 计算涨跌停价格
        limit_up_price = 0.0
        limit_down_price = 0.0
        if pre_close > 0:
            ratio = self._get_limit_ratio(data_list[0].get('symbol', ''), stock_name)
            limit_up_price = self._calc_limit_up_price(pre_close, ratio)
            limit_down_price = self._calc_limit_down_price(pre_close, ratio)

        result = []
        
        # 1. 记录开盘价作为初始基准
        start_item = data_list[0]
        current_base_price = start_item['open']
        result.append({**start_item, "type": "open", "base_price": current_base_price})
        
        # 初始化极值跟踪
        max_price_so_far = start_item['high']
        min_price_so_far = start_item['low']

        # 2. 遍历后续数据
        for i in range(1, len(data_list)):
            item = data_list[i]
            price = item['close']
            
            # 检查是否为新的极值
            is_new_high = item['high'] > max_price_so_far
            is_new_low = item['low'] < min_price_so_far
            
            # 更新极值记录
            if is_new_high: max_price_so_far = item['high']
            if is_new_low: min_price_so_far = item['low']

            # 计算相对于基准的涨跌幅
            change_pct = (price - current_base_price) / current_base_price * 100 if current_base_price != 0 else 0
            
            should_record = False
            record_type = ""

            # 规则 A: 价格波动超过阈值
            if abs(change_pct) >= threshold_pct:
                should_record = True
                record_type = "trigger_pct"
            
            # 规则 B: 创截止目前的新高
            elif is_new_high:
                should_record = True
                record_type = "new_high"
            
            # 规则 C: 创截止目前的新低
            elif is_new_low:
                should_record = True
                record_type = "new_low"

            if should_record:
                new_record = {
                    **item, 
                    "type": record_type, 
                    "change_pct_from_base": round(change_pct, 2),
                    "base_price": current_base_price
                }
                
                # 如果是新高或新低，判断是否涨停跌停
                if pre_close > 0:
                    if record_type == "new_high":
                        new_record["is_limit_up"] = self._is_at_limit_up(item['high'], limit_up_price)
                    elif record_type == "new_low":
                        new_record["is_limit_down"] = self._is_at_limit_down(item['low'], limit_down_price)
                
                result.append(new_record)
                # 更新基准价格
                current_base_price = price

        # 3. 确保最后一条（收盘价）被记录
        last_item = data_list[-1]
        if result[-1]['datetime'] != last_item['datetime']:
            change_pct = (last_item['close'] - current_base_price) / current_base_price * 100 if current_base_price != 0 else 0
            result.append({
                **last_item, 
                "type": "close", 
                "change_pct_from_base": round(change_pct, 2),
                "base_price": current_base_price
            })

        return result

    def get_realtime_quote(self, symbol: str) -> Dict:
        """
        获取实时行情数据

        Args:
            symbol: 股票代码

        Returns:
            实时行情数据字典
        """
        def _fetch_realtime_quote():
            client = self._get_client()
            logger.info("获取%s的实时行情", symbol)

            df = client.quotes(symbol=symbol)

            if df is None or df.empty:
                raise ConnectionError("未获取到实时行情数据")

            row = df.iloc[0]

            # mootdx返回的列名: price(当前价), last_close(昨收), open, high, low, vol, amount
            last_close = round(float(row.get("last_close", 0)), 2)
            price = round(float(row.get("price", 0)), 2)
            return {
                "symbol": symbol,
                "code": str(row.get("code", "")),
                "price": price,
                "last_close": last_close,
                "change_pct": round((price - last_close) / last_close * 100, 2) if last_close > 0 else 0,
                "open": round(float(row.get("open", 0)), 2),
                "high": round(float(row.get("high", 0)), 2),
                "low": round(float(row.get("low", 0)), 2),
                "volume": int(row.get("vol", row.get("volume", 0))),
                "amount": round(float(row.get("amount", 0)), 2),
            }

        try:
            return self._execute_with_retry(
                f"获取{symbol}的实时行情",
                _fetch_realtime_quote,
            )
        except Exception as e:
            logger.error("获取%s的实时行情失败: %s", symbol, e)
            return {"error": str(e)}

    def _load_stock_list(self):
        """从文件加载股票名称->代码映射到内存"""
        data_dir = os.path.dirname(os.path.abspath(__file__))
        stock_list_path = os.path.join(data_dir, "stock_list.json")
        try:
            with open(stock_list_path, "r", encoding="utf-8") as f:
                stock_list = json.load(f)
            self._stock_name_to_code = {item["name"]: item["code"] for item in stock_list}
            logger.info(f"股票列表已加载，共 {len(self._stock_name_to_code)} 条")
        except FileNotFoundError:
            logger.warning(f"股票列表文件不存在: {stock_list_path}")
            self._stock_name_to_code = {}
        except Exception as e:
            logger.error(f"加载股票列表失败: {e}")
            self._stock_name_to_code = {}

    def resolve_stock_code(self, stock_code: Optional[str] = None, stock_name: Optional[str] = None) -> str:
        """
        解析股票代码：优先使用 stock_code，否则通过 stock_name 查找。

        Args:
            stock_code: 股票代码
            stock_name: 股票名称

        Returns:
            股票代码

        Raises:
            ValueError: 无法解析出有效的股票代码时
        """
        if stock_code and stock_code.strip():
            return stock_code.strip()

        if stock_name and stock_name.strip():
            name = stock_name.strip()
            # 精确匹配
            code = self._stock_name_to_code.get(name)
            if code:
                return code
            # 模糊匹配
            candidates = [
                (n, c) for n, c in self._stock_name_to_code.items() if name in n
            ]
            if len(candidates) == 1:
                return candidates[0][1]
            if len(candidates) > 1:
                names = ", ".join(f"{n}({c})" for n, c in candidates[:10])
                raise ValueError(
                    f"股票名称 '{name}' 匹配到多个结果: {names}，请补充更多关键字或使用股票代码"
                )
            raise ValueError(f"未找到名称包含 '{name}' 的股票")

        raise ValueError("请提供股票代码(stock_code)或股票名称(stock_name)")
