"""
A股行情数据获取模块

使用mootdx获取A股行情数据，支持：
- 1分钟K线数据（单日）
- 日K数据（含均线、涨跌停、流通市值）
- 前复权处理
- 服务器自动探测和故障转移
"""

import bisect
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
from mootdx.quotes import Quotes

from . import trading_calendar
from .server_manager import (
    PROBE_EMPTY_ERROR,
    TdxServerManager,
    TdxServersUnavailableError,
    get_server_manager,
)

try:
    # 缓存内全部已探测通达信服务器（质量有保障），批量接口节点池主力
    from star_stocks.market_data.tdx_probe import load_cached_tdx_servers
except ImportError:  # pragma: no cover - 测试环境无 star_stocks 依赖时降级
    load_cached_tdx_servers = None

# 配置日志
logger = logging.getLogger(__name__)


class NonRetryableError(Exception):
    """参数/数据范围类错误：换节点重试也不会成功，应直接反馈调用方。"""


# 涨跌停计算常量
DEFAULT_LIMIT_RATIO = 0.10  # 主板涨跌停比例10%（默认）
LIMIT_PRICE_TOLERANCE = 0.005  # 涨停价比较容差（半分钱，适配价格最小变动单位）

# 默认服务器（通达信服务器）
DEFAULT_SERVER = "119.147.212.81:7709"

# 最大重试次数（切换服务器）
MAX_RETRY_COUNT = 3

# 行情类中间结果缓存有效期（秒）：服务常驻进程，跨交易日需能刷新到最新一根
CACHE_TTL_SECONDS = 60


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
        # 除权事件乘数缓存：symbol -> (写入时刻, [(事件日, 前复权乘数), ...])
        self._adjust_events_cache: Dict[str, Tuple[float, List[Tuple[str, float]]]] = {}
        # 原始日K缓存：symbol -> (写入时刻, DataFrame)（复权乘数计算、昨收取数复用）
        self._daily_raw_cache: Dict[str, Tuple[float, pd.DataFrame]] = {}
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

    @staticmethod
    def _calc_change_pct(price: float, pre_close: float) -> float:
        if pd.isna(pre_close) or pre_close <= 0:
            return 0.0
        return round((price - pre_close) / pre_close * 100, 2)

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

    def _build_batch_nodes(self, max_nodes: int = 5) -> List[str]:
        """
        构建批量拉取节点池（去重，优先服务器管理器活跃列表）

        节点来源优先级：服务器管理器当前列表 → 已知优质节点 → 默认服务器 → 备用服务器列表。
        去重后取前 max_nodes 个，保证并发 worker 使用不同通达信节点分散负载。

        Args:
            max_nodes: 最大节点数，默认 5

        Returns:
            ["ip:port", ...] 列表
        """
        nodes: List[Tuple[str, int]] = []
        seen = set()

        # 1) 服务器管理器当前活跃列表（缓存首选/探测结果）
        if self._use_server_manager:
            try:
                manager = get_server_manager()
                for host, port, _ in manager.get_all_servers():
                    key = (host, port)
                    if key not in seen:
                        seen.add(key)
                        nodes.append(key)
            except Exception as e:
                logger.warning("读取服务器管理器列表失败，使用默认+备用节点: %s", e)

        # 2) 缓存内全部已探测服务器（探测通过，质量有保障）
        if load_cached_tdx_servers is not None:
            try:
                for host, port in load_cached_tdx_servers():
                    key = (host, port)
                    if key not in seen:
                        seen.add(key)
                        nodes.append(key)
            except Exception as e:
                logger.warning("读取通达信服务器缓存失败: %s", e)

        # 3) 已知优质节点（fetch_minute_kline 默认节点，实测稳定）
        try:
            key = ("202.108.253.139", 80)
            if key not in seen:
                seen.add(key)
                nodes.append(key)
        except Exception:
            pass

        # 4) 默认服务器
        try:
            host, port = self._server.split(":")
            key = (host, int(port))
            if key not in seen:
                seen.add(key)
                nodes.append(key)
        except Exception:
            pass

        # 4) 备用服务器列表
        for host, port in self._TDX_SERVERS:
            key = (host, port)
            if key not in seen:
                seen.add(key)
                nodes.append(key)

        return [f"{h}:{p}" for h, p in nodes[:max_nodes]]

    def get_minute_data_batch(
        self,
        stocks: List[Dict],
        date: str = "",
        adaptive_threshold: float = 1.0,
        max_workers: int = 5,
    ) -> Dict:
        """
        批量获取指定交易日的1分钟K线数据（多线程并发，每线程独立通达信节点）

        每个 worker 线程创建独立的 StockDataFetcher（固定服务器模式）绑定
        不同通达信节点，互不共享客户端连接，线程安全。单只股票失败不拖垮
        整批（错误进入 errors 列表）。

        Args:
            stocks: 股票列表，每项 {"code": "600602", "name": "云赛智联"}（name 可选）
            date: 目标交易日 YYYY-MM-DD；留空=最近交易日（同一批统一使用该日期）
            adaptive_threshold: 自适应提取阈值(如 1.0 表示 1%)，默认 1.0
            max_workers: 并发线程数，默认 5（与节点池数量取较小值）

        Returns:
            {
                "date": "YYYY-MM-DD",
                "results": [{"code", "name", "symbol", "date", "frequency", "count", "data"}],
                "errors": [{"code", "name", "reason"}],
                "meta": {"total", "success", "failed", "workers", "nodes"}
            }
        """
        nodes = self._build_batch_nodes(max_nodes=max_workers)
        workers = max(1, min(max_workers, len(nodes)))
        results: List[Dict] = []
        errors: List[Dict] = []
        lock = threading.Lock()

        # 统一解析目标交易日，保证同一批所有个股口径一致
        try:
            batch_day, _ = self._normalize_target_day(date)
        except Exception as e:
            return {
                "date": "",
                "results": [],
                "errors": [{"code": "", "name": "", "reason": str(e)}],
                "meta": {"total": len(stocks), "success": 0, "failed": 1, "workers": 0, "nodes": nodes},
            }

        def _fetch(idx: int, stock: Dict):
            code = str(stock.get("code", "")).strip()
            name = str(stock.get("name", "")).strip()
            # 正常路径绑定本轮节点；失败时顺次换节点重试（最多3个不同节点，兜底节点故障/单节点对某市场支持差）
            node_indexes = [(idx + k) % len(nodes) for k in range(min(3, len(nodes)))]
            last_error: Optional[Exception] = None
            for node_idx in node_indexes:
                node = nodes[node_idx]
                fetcher: Optional[StockDataFetcher] = None
                try:
                    # 每线程独立 fetcher + 固定服务器模式，天然线程隔离
                    fetcher = StockDataFetcher(server=node, use_server_manager=False)
                    data = fetcher._fetch_minute_payload(code, batch_day, adaptive_threshold, name)
                    with lock:
                        results.append(
                            {
                                "code": code,
                                "name": name,
                                "symbol": data.get("symbol", code),
                                "date": data.get("date", batch_day),
                                "frequency": data.get("frequency", ""),
                                "count": data.get("count", 0),
                                "data": data.get("data", []),
                            }
                        )
                    return
                except NonRetryableError as e:
                    # 停牌/非交易日/超范围等：换节点同样失败，直接记错误
                    last_error = e
                    logger.warning("批量获取%s在%s失败（不重试）: %s", code, batch_day, e)
                    break
                except Exception as e:
                    last_error = e
                    logger.warning(
                        "批量获取%s使用节点%s异常: %s，换节点重试",
                        code, node, e,
                    )
                finally:
                    if fetcher is not None:
                        try:
                            fetcher.close()
                        except Exception:
                            pass
            with lock:
                errors.append(
                    {"code": code, "name": name, "reason": str(last_error or "未知错误")}
                )

        with ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="minute_batch"
        ) as pool:
            list(pool.map(lambda t: _fetch(t[0], t[1]), enumerate(stocks)))

        return {
            "date": batch_day,
            "results": results,
            "errors": errors,
            "meta": {
                "total": len(stocks),
                "success": len(results),
                "failed": len(errors),
                "workers": workers,
                "nodes": nodes,
            },
        }

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

        参数/数据范围类错误（NonRetryableError）不重试，直接抛给调用方。

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
            except NonRetryableError:
                raise
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

    def get_minute_data(self, symbol: str, date: str = "", adaptive_threshold: float = 1.0, stock_name: str = "") -> Dict:
        """
        获取指定交易日的1分钟K线数据

        Args:
            symbol: 股票代码，如 "600519"
            date: 目标交易日 YYYY-MM-DD（容忍 YYYYMMDD）；留空=最近交易日
                  （盘前当日尚无数据时自动回退到上一交易日）
            adaptive_threshold: 自适应提取阈值(如 1.0 表示 1%)，默认 1.0；传 0 保留全部点
            stock_name: 股票名称，用于辅助判断涨跌停（ST股）

        Returns:
            {"symbol", "date", "frequency", "count", "data": [...]}；
            失败返回 {"error": ..., "data": []}
        """
        try:
            return self._execute_with_retry(
                f"获取{symbol}的1分钟K线数据",
                self._fetch_minute_payload,
                symbol,
                date,
                adaptive_threshold,
                stock_name,
            )
        except NonRetryableError as e:
            logger.warning("获取%s的1分钟K线数据失败（参数/数据范围类）: %s", symbol, e)
            return {"error": str(e), "data": []}
        except Exception as e:
            logger.error("获取%s的1分钟K线数据失败: %s", symbol, e)
            return {"error": str(e), "data": []}

    def _fetch_minute_payload(
        self, symbol: str, date: str = "", adaptive_threshold: float = 1.0, stock_name: str = ""
    ) -> Dict:
        """获取目标交易日分钟线（异常向外抛，供批量接口区分是否值得换节点重试）。"""
        client = self._get_client()
        day_str, is_default = self._normalize_target_day(date)

        rows = self._resolve_minute_window(client, symbol, day_str)
        if rows is None and is_default:
            # 默认取最近交易日：盘前当日尚无分钟数据 → 自动回退上一交易日
            prev_day = trading_calendar.resolve_session(day_str, "previous").isoformat()
            rows = self._resolve_minute_window(client, symbol, prev_day)
            if rows is not None:
                logger.info("%s 在 %s 暂无分钟数据，回退到上一交易日 %s", symbol, day_str, prev_day)
                day_str = prev_day
        if rows is None or len(rows) == 0:
            raise NonRetryableError(
                f"{symbol} 在 {day_str} 无分钟数据（停牌/未上市，或日期超出分钟线可回溯范围）"
            )

        # 前复权 + 昨收（与日K同一复权口径）
        df = self._apply_qfq(client, symbol, rows)
        pre_close = self._get_prev_close(symbol, day_str)
        logger.info("获取%s在%s的分钟线 %d 根，昨收 %s", symbol, day_str, len(df), pre_close)

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
                    "change_pct": self._calc_change_pct(float(row.get("close", 0)), pre_close),
                }
            )

        if not data_list:
            raise NonRetryableError(f"{symbol} 在 {day_str} 无分钟数据")

        # 抽点（adaptive_threshold 非 None 即抽点；0 保留全部点）
        if adaptive_threshold is not None:
            logger.info("对%s在%s应用自适应提取，阈值: %s%%", symbol, day_str, adaptive_threshold)
            data_list = self.extract_adaptive_kline(
                data_list, adaptive_threshold, pre_close, stock_name, symbol
            )
            for item in data_list:
                item["change_pct"] = self._calc_change_pct(item["close"], pre_close)
            data_list = self._finalize_output_fields(data_list)
            return {
                "symbol": symbol,
                "date": day_str,
                "frequency": "adaptive_1min",
                "count": len(data_list),
                "data": data_list,
            }

        data_list = self._finalize_output_fields(data_list)
        return {
            "symbol": symbol,
            "date": day_str,
            "frequency": "1min",
            "count": len(data_list),
            "data": data_list,
        }

    def _normalize_target_day(self, date_str: str) -> Tuple[str, bool]:
        """解析/校验目标交易日，返回 (YYYY-MM-DD, 是否为默认的最近交易日)。"""
        text = (date_str or "").strip()
        today = datetime.now().date()
        if not text or text.lower() in ("today", "latest", "最近交易日"):
            day = trading_calendar.latest_trading_day(today)
            return day.isoformat(), True

        try:
            day = trading_calendar.parse_date(text)
        except ValueError as e:
            raise NonRetryableError(str(e)) from e

        if day > today:
            raise NonRetryableError(
                f"date={day.isoformat()} 为未来日期，最近交易日为 "
                f"{trading_calendar.latest_trading_day(today).isoformat()}"
            )
        if not trading_calendar.is_trading_day(day):
            raise NonRetryableError(
                f"date={day.isoformat()} 非交易日（最近交易日 "
                f"{trading_calendar.resolve_session(day, 'previous').isoformat()}）"
            )
        return day.isoformat(), False

    def _resolve_minute_window(
        self, client: Quotes, symbol: str, day_str: str, max_tries: int = 5
    ) -> Optional[pd.DataFrame]:
        """定位目标交易日的分钟线（恰好该日 240 根）。

        通达信 bars 接口语义：start = 从最新一根往前跳过的根数（越大越早），
        offset 单次上限 800。以「该日之后的交易日数 × 240」估算 start，取回后按日切片；
        个股停牌、次新等导致「分钟根数 ≠ 交易日数 × 240」时，按窗口与目标日的先后
        逐日挪动 start 重试（窗口偏新→往早挪，窗口偏旧→往近挪）。
        """
        try:
            k = trading_calendar.trading_days_after(day_str)
        except ValueError as e:
            raise NonRetryableError(str(e)) from e

        start = max(0, k * 240 - 240)
        tried = set()

        for _ in range(max_tries):
            if start in tried:
                break
            tried.add(start)

            df = client.bars(symbol=symbol, frequency=7, start=start, offset=800)
            if df is None or len(df) == 0:
                # 空返回有两种可能：节点异常（可重试）或已超出该节点的分钟线历史深度。
                # 用 start=0 的最小窗口探一下，能取到就是超范围，取不到就是节点问题。
                probe = client.bars(symbol=symbol, frequency=7, start=0, offset=10)
                if probe is None or len(probe) == 0:
                    raise ConnectionError("未获取到分钟K线数据")
                break
            day_strs = [str(v)[:10] for v in df["datetime"]]
            oldest, newest = day_strs[0], day_strs[-1]

            if day_str < oldest:
                # 窗口整体偏新 → 往更早的方向挪
                start += 240
            elif day_str > newest:
                # 窗口整体偏旧 → 往更近的方向挪
                start = start - 240 if start >= 240 else 0
            else:
                subset = df[[s == day_str for s in day_strs]]
                if len(subset):
                    return subset.reset_index(drop=True)
                # 窗口跨越目标日但当日无数据（如盘中未开始/停牌半日）→ 往更近挪
                start = start - 240 if start >= 240 else 0
        return None

    def _get_prev_close(self, symbol: str, day_str: str) -> float:
        """目标交易日的昨收（与分钟线同一复权口径；取不到返回 0.0）。"""
        try:
            raw = self._get_raw_daily(symbol)
            if raw is None or len(raw) == 0:
                return 0.0
            adjusted = self._apply_qfq(None, symbol, raw)
            days = [str(v)[:10] for v in adjusted["datetime"]]
            if day_str not in days:
                return 0.0
            pos = days.index(day_str)
            if pos == 0:
                return 0.0
            return round(float(adjusted["close"].iloc[pos - 1]), 2)
        except Exception as e:
            logger.warning("获取%s在%s的昨收失败: %s", symbol, day_str, e)
        return 0.0

    def _get_raw_daily(self, symbol: str, count: int = 250) -> Optional[pd.DataFrame]:
        """未被复权的日K（按股票短时缓存），供复权乘数计算与昨收取数复用。

        缓存带 TTL：MCP 服务常驻进程，跨交易日仍须能取到最新一根日K。
        """
        cached = self._daily_raw_cache.get(symbol)
        if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]
        df = self._get_client().bars(symbol=symbol, frequency=9, offset=count)
        self._daily_raw_cache[symbol] = (time.monotonic(), df)
        return df

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
        应用前复权处理（基于通达信除权除息数据本地计算，前复权基准=最新交易日）

        前复权乘数：对每个除权除息事件，事件日之前的价格乘以
            ((前一日收盘 * 10 - 每10股派息 + 每10股配股数 * 配股价)
             / (10 + 每10股配股数 + 每10股送转股数)) / 前一日收盘

        说明：
        - 乘数序列固定以「最新交易日的日K」为基准计算，与传入窗口无关，因此分钟线
          只取历史某一天时，其复权口径与日K接口完全一致
        - 仅调整 open/high/low/close，不调整 volume（分钟量能用于横向比较，保持原始值）

        Args:
            client: Quotes实例
            symbol: 股票代码
            df: 原始K线数据（含 datetime 列）

        Returns:
            前复权后的DataFrame
        """
        try:
            events = self._get_adjust_events(symbol)
            if not events or df is None or df.empty:
                return df

            out = df.copy()
            day_strs = [str(v)[:10] for v in out["datetime"]]

            # 从最新一根往前扫，累积「事件日晚于当前行」的乘数
            factors = [1.0] * len(day_strs)
            ei = len(events) - 1
            running = 1.0
            for idx in sorted(range(len(day_strs)), key=lambda i: day_strs[i], reverse=True):
                current_day = day_strs[idx]
                while ei >= 0 and events[ei][0] > current_day:
                    running *= events[ei][1]
                    ei -= 1
                factors[idx] = running

            if all(abs(f - 1.0) < 1e-9 for f in factors):
                return df

            for field in ("open", "high", "low", "close"):
                out[field] = [round(float(v) * f, 2) for v, f in zip(out[field], factors)]
            logger.info("%s已完成前复权处理（%d 个除权事件）", symbol, len(events))
            return out

        except Exception as e:
            logger.warning(f"{symbol}前复权处理失败，返回原始数据: {e}")
            return df

    def _get_adjust_events(self, symbol: str) -> List[Tuple[str, float]]:
        """获取除权除息事件的前复权乘数列表（按事件日升序），按股票短时缓存。"""
        cached = self._adjust_events_cache.get(symbol)
        if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]

        events: List[Tuple[str, float]] = []
        try:
            events = self._build_adjust_events(symbol)
        except Exception as e:
            logger.warning("%s 除权数据计算失败，按不复权处理: %s", symbol, e)
            events = []

        self._adjust_events_cache[symbol] = (time.monotonic(), events)
        return events

    def _build_adjust_events(self, symbol: str) -> List[Tuple[str, float]]:
        """由通达信 xdxr + 原始日K 计算每个除权事件的乘数（事件日, ratio）。"""
        client = self._get_client()
        xdxr = client.xdxr(symbol=symbol)
        if xdxr is None or len(xdxr) == 0:
            return []

        ex = xdxr[xdxr["category"] == 1].copy()
        if len(ex) == 0:
            return []

        # 事件日的「前一日收盘」需要原始日K；取 250 根（约一年）覆盖所有可能影响的事件
        raw = self._get_raw_daily(symbol)
        if raw is None or len(raw) == 0:
            return []
        closes: Dict[str, float] = {}
        for dt, cl in zip(raw["datetime"], raw["close"]):
            try:
                closes[str(dt)[:10]] = float(cl)
            except (TypeError, ValueError):
                continue
        if not closes:
            return []
        trade_days = sorted(closes)

        events: List[Tuple[str, float]] = []
        for _, row in ex.iterrows():
            try:
                ex_day = f"{int(row['year']):04d}-{int(row['month']):02d}-{int(row['day']):02d}"
            except (TypeError, ValueError, KeyError):
                continue
            # 前一日收盘：日K中严格早于事件日的最后一根
            prev_pos = bisect.bisect_left(trade_days, ex_day) - 1
            if prev_pos < 0:
                continue
            prev_close = closes[trade_days[prev_pos]]
            if prev_close <= 0:
                continue

            def _num(key: str) -> float:
                value = row.get(key)
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    return 0.0
                return 0.0 if pd.isna(value) else value

            fenhong = _num("fenhong")        # 每10股派息（元）
            peigu = _num("peigu")            # 每10股配股（股）
            peigujia = _num("peigujia")      # 配股价（元）
            songzhuangu = _num("songzhuangu")  # 每10股送转（股）
            denominator = 10 + peigu + songzhuangu
            if denominator <= 0:
                continue
            ex_rights_price = (prev_close * 10 - fenhong + peigu * peigujia) / denominator
            ratio = ex_rights_price / prev_close
            if ratio <= 0 or abs(ratio - 1.0) < 1e-9:
                continue
            events.append((ex_day, ratio))

        events.sort(key=lambda item: item[0])
        if events:
            logger.info("%s 除权事件 %d 个: %s", symbol, len(events), events[-3:])
        return events

    def extract_adaptive_kline(self, data_list: List[Dict], threshold_pct: float = 1.0, pre_close: float = 0.0, stock_name: str = "", symbol: str = "") -> List[Dict]:
        """
        提取自适应 K线数据 (1% 波动 + 全天极值提取)

        规则：
        - 规则 A（波动突破）：当前收盘价相对滚动基准价波动 ≥ 阈值 → trigger_pct
        - 规则 B（全天最高）：当前最高价 == 全天最高价（扫描前预先计算，仅首次命中）→ new_high
        - 规则 C（全天最低）：当前最低价 == 全天最低价（扫描前预先计算，仅首次命中）→ new_low
        - 滚动基准：每记录一根，基准价更新为该根收盘价
        - 收盘补记：最后一根若未记录则强制补记，标记 type=close
        """
        if not data_list:
            return []

        # 计算涨跌停价格
        limit_up_price = 0.0
        limit_down_price = 0.0
        if pre_close > 0:
            # 使用传入的 symbol 计算涨跌停比例，而非从 data_list 中获取（data_list 中没有 symbol 字段）
            ratio = self._get_limit_ratio(symbol, stock_name)
            limit_up_price = self._calc_limit_up_price(pre_close, ratio)
            limit_down_price = self._calc_limit_down_price(pre_close, ratio)
            logger.info("涨跌停计算: symbol=%s, ratio=%.2f, 涨停=%.2f, 跌停=%.2f", symbol, ratio, limit_up_price, limit_down_price)

        result = []
        
        # 1. 记录开盘价作为初始基准
        start_item = data_list[0]
        current_base_price = start_item['open']
        result.append({**start_item, "type": "open", "base_price": current_base_price})

        # 逐根扫描前：计算全天最高/最低价（规则 B/C 的比较基准）
        day_high = max(item['high'] for item in data_list)
        day_low = min(item['low'] for item in data_list)
        # 全天极值是否已记录（开盘即极值时视为已记录，避免一字板等全同价场景重复记录）
        high_recorded = start_item['high'] == day_high
        low_recorded = start_item['low'] == day_low

        # 2. 遍历后续数据
        for i in range(1, len(data_list)):
            item = data_list[i]
            price = item['close']

            # 规则 B/C：当前最高价是否等于全天最高价/最低价（仅首次命中记录）
            is_new_high = (item['high'] == day_high) and not high_recorded
            is_new_low = (item['low'] == day_low) and not low_recorded
            if is_new_high:
                high_recorded = True
            if is_new_low:
                low_recorded = True

            # 计算相对于基准的涨跌幅
            change_pct = (price - current_base_price) / current_base_price * 100 if current_base_price != 0 else 0
            
            should_record = False
            record_type = ""

            # 规则 B/C 优先：当前价等于全天最高/最低（极值标记信息量更高，优先于波动标记）
            if is_new_high:
                should_record = True
                record_type = "new_high"
            elif is_new_low:
                should_record = True
                record_type = "new_low"
            # 规则 A: 价格波动超过阈值（非极值点的波动突破）
            elif abs(change_pct) >= threshold_pct:
                should_record = True
                record_type = "trigger_pct"

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

    def _finalize_output_fields(self, data_list: List[Dict]) -> List[Dict]:
        """输出字段裁剪（仅在全部处理计算完成后调用，不影响处理过程）。

        - datetime → time（内容由 yyyy-MM-dd HH:mm 截取为 HH:mm）
        - 删除 amount / change_pct_from_base / base_price
        """
        for item in data_list:
            item["time"] = str(item.get("datetime", ""))[11:16]
            item.pop("datetime", None)
            item.pop("amount", None)
            item.pop("change_pct_from_base", None)
            item.pop("base_price", None)
        return data_list

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
