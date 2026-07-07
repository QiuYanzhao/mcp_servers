"""
通达信服务器管理器

负责探测可用服务器、维护服务器列表、提供故障转移和自动重试功能。
"""

import logging
import threading
import time
from typing import List, Optional, Tuple

from star_stocks.market_data import (
    TdxHost,
    TdxServerProbeResult,
    scan_all_working_tdx_servers,
)

logger = logging.getLogger(__name__)

# 默认探测参数
DEFAULT_PROBE_SYMBOL = "600519"  # 贵州茅台，用于探测
DEFAULT_PROBE_COUNT = 5  # 探测时获取的K线数量
DEFAULT_CONNECT_TIMEOUT = 4  # 单台服务器连接超时（秒）
DEFAULT_TOTAL_TIMEOUT = 10  # 整轮探测总超时（秒）
DEFAULT_MAX_WORKERS = 20  # 并发探测线程数

# 服务器健康检查间隔（秒）
SERVER_HEALTH_CHECK_INTERVAL = 300  # 5分钟


class TdxServerManager:
    """
    通达信服务器管理器

    功能：
    1. 启动时并发探测可用服务器
    2. 维护可用服务器列表（按探测顺序排列）
    3. 提供获取当前最优服务器的方法
    4. 支持服务器故障时自动切换到下一个可用服务器
    5. 支持定期重新探测以更新服务器列表
    """

    def __init__(
        self,
        probe_symbol: str = DEFAULT_PROBE_SYMBOL,
        probe_count: int = DEFAULT_PROBE_COUNT,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        total_timeout: float = DEFAULT_TOTAL_TIMEOUT,
        max_workers: int = DEFAULT_MAX_WORKERS,
        auto_refresh: bool = True,
        refresh_interval: float = SERVER_HEALTH_CHECK_INTERVAL,
    ):
        """
        初始化服务器管理器

        Args:
            probe_symbol: 用于探测的股票代码，默认 600519（贵州茅台）
            probe_count: 探测时获取的K线数量
            connect_timeout: 单台服务器连接超时（秒）
            total_timeout: 整轮探测总超时（秒）
            max_workers: 并发探测线程数
            auto_refresh: 是否自动定期刷新服务器列表
            refresh_interval: 自动刷新间隔（秒）
        """
        self._probe_symbol = probe_symbol
        self._probe_count = probe_count
        self._connect_timeout = connect_timeout
        self._total_timeout = total_timeout
        self._max_workers = max_workers

        # 可用服务器列表（按探测顺序排列）
        self._available_servers: List[TdxServerProbeResult] = []
        # 当前使用的服务器索引
        self._current_index: int = 0
        # 服务器列表锁
        self._lock = threading.RLock()
        # 上次探测时间
        self._last_probe_time: float = 0
        # 探测耗时
        self._probe_duration: float = 0

        # 自动刷新相关
        self._auto_refresh = auto_refresh
        self._refresh_interval = refresh_interval
        self._refresh_thread: Optional[threading.Thread] = None
        self._stop_refresh = threading.Event()

        logger.info(
            "TdxServerManager 初始化: probe_symbol=%s, probe_count=%d, "
            "connect_timeout=%ss, total_timeout=%ss, max_workers=%d",
            probe_symbol,
            probe_count,
            connect_timeout,
            total_timeout,
            max_workers,
        )

    def start(self) -> bool:
        """
        启动服务器管理器

        执行初始探测并启动自动刷新线程（如果启用）。

        Returns:
            是否成功探测到可用服务器
        """
        logger.info("启动 TdxServerManager...")
        success = self.probe()

        if self._auto_refresh and not self._refresh_thread:
            self._start_refresh_thread()

        return success

    def stop(self):
        """停止服务器管理器"""
        logger.info("停止 TdxServerManager...")
        self._stop_refresh.set()
        if self._refresh_thread and self._refresh_thread.is_alive():
            self._refresh_thread.join(timeout=5)
            self._refresh_thread = None

    def probe(self) -> bool:
        """
        执行服务器探测

        并发探测所有通达信服务器，更新可用服务器列表。

        Returns:
            是否成功探测到可用服务器
        """
        logger.info("开始探测通达信服务器...")
        start_time = time.time()

        try:
            results = scan_all_working_tdx_servers(
                self._probe_symbol,
                count=self._probe_count,
                connect_timeout=self._connect_timeout,
                total_timeout=self._total_timeout,
                max_workers=self._max_workers,
            )

            elapsed = time.time() - start_time
            self._probe_duration = elapsed

            with self._lock:
                self._available_servers = results
                self._current_index = 0
                self._last_probe_time = time.time()

            if results:
                logger.info(
                    "服务器探测完成: 找到 %d 台可用服务器，耗时 %.2f 秒",
                    len(results),
                    elapsed,
                )
                for i, server in enumerate(results[:5]):  # 只显示前5台
                    logger.info(
                        "  [%d] %s:%d (%s) - %d 根K线",
                        i + 1,
                        server.host.host,
                        server.host.port,
                        server.host.name,
                        server.bar_count,
                    )
                if len(results) > 5:
                    logger.info("  ... 还有 %d 台可用服务器", len(results) - 5)
                return True
            else:
                logger.warning("服务器探测完成: 未找到可用服务器，耗时 %.2f 秒", elapsed)
                return False

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error("服务器探测失败: %s，耗时 %.2f 秒", e, elapsed)
            return False

    def get_current_server(self) -> Optional[Tuple[str, int]]:
        """
        获取当前可用服务器

        Returns:
            (host, port) 元组，如果没有可用服务器则返回 None
        """
        with self._lock:
            if not self._available_servers:
                return None
            server = self._available_servers[self._current_index]
            return (server.host.host, server.host.port)

    def get_current_host(self) -> Optional[TdxHost]:
        """
        获取当前可用服务器的 TdxHost 对象

        Returns:
            TdxHost 对象，如果没有可用服务器则返回 None
        """
        with self._lock:
            if not self._available_servers:
                return None
            return self._available_servers[self._current_index].host

    def switch_to_next_server(self) -> Optional[Tuple[str, int]]:
        """
        切换到下一个可用服务器

        当当前服务器出现问题时调用，循环切换到列表中的下一个服务器。

        Returns:
            新的 (host, port) 元组，如果没有可用服务器则返回 None
        """
        with self._lock:
            if not self._available_servers:
                logger.warning("没有可用服务器，无法切换")
                return None

            old_index = self._current_index
            self._current_index = (self._current_index + 1) % len(self._available_servers)
            new_server = self._available_servers[self._current_index]

            logger.info(
                "切换服务器: [%d] %s:%d -> [%d] %s:%d",
                old_index,
                self._available_servers[old_index].host.host,
                self._available_servers[old_index].host.port,
                self._current_index,
                new_server.host.host,
                new_server.host.port,
            )
            return (new_server.host.host, new_server.host.port)

    def get_all_servers(self) -> List[Tuple[str, int, str]]:
        """
        获取所有可用服务器列表

        Returns:
            列表，每个元素为 (host, port, name) 元组
        """
        with self._lock:
            return [
                (s.host.host, s.host.port, s.host.name)
                for s in self._available_servers
            ]

    def get_server_count(self) -> int:
        """获取可用服务器数量"""
        with self._lock:
            return len(self._available_servers)

    def get_status(self) -> dict:
        """
        获取服务器管理器状态

        Returns:
            包含状态信息的字典
        """
        with self._lock:
            current_server = None
            if self._available_servers:
                server = self._available_servers[self._current_index]
                current_server = {
                    "host": server.host.host,
                    "port": server.host.port,
                    "name": server.host.name,
                }

            return {
                "available_count": len(self._available_servers),
                "current_index": self._current_index,
                "current_server": current_server,
                "last_probe_time": self._last_probe_time,
                "probe_duration": self._probe_duration,
                "probe_symbol": self._probe_symbol,
            }

    def _start_refresh_thread(self):
        """启动自动刷新线程"""
        def refresh_loop():
            while not self._stop_refresh.is_set():
                # 等待指定间隔或收到停止信号
                if self._stop_refresh.wait(timeout=self._refresh_interval):
                    break
                # 执行刷新
                try:
                    logger.info("自动刷新服务器列表...")
                    self.probe()
                except Exception as e:
                    logger.error("自动刷新服务器列表失败: %s", e)

        self._refresh_thread = threading.Thread(
            target=refresh_loop,
            name="tdx-server-refresh",
            daemon=True,
        )
        self._refresh_thread.start()
        logger.info("自动刷新线程已启动，间隔: %d 秒", self._refresh_interval)


# 全局服务器管理器实例
_server_manager: Optional[TdxServerManager] = None
_manager_lock = threading.Lock()


def get_server_manager() -> TdxServerManager:
    """
    获取全局服务器管理器实例（单例模式）

    Returns:
        TdxServerManager 实例
    """
    global _server_manager
    if _server_manager is None:
        with _manager_lock:
            if _server_manager is None:
                _server_manager = TdxServerManager()
    return _server_manager


def init_server_manager(**kwargs) -> TdxServerManager:
    """
    初始化全局服务器管理器（可自定义参数）

    Args:
        **kwargs: 传递给 TdxServerManager 的参数

    Returns:
        TdxServerManager 实例
    """
    global _server_manager
    with _manager_lock:
        if _server_manager is not None:
            _server_manager.stop()
        _server_manager = TdxServerManager(**kwargs)
    return _server_manager
