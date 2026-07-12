"""
通达信服务器管理器

与 star_stocks 保持一致的服务器解析策略：
1. 有缓存时直接读取 tdx_servers.json 首个 IP，不做预探测
2. 仅在缓存为空（首次使用）或实际取数失败时并发探测并更新缓存
"""

import logging
import threading
import time
from typing import List, Literal, Optional, Tuple

from star_stocks.market_data import (
    probe_and_refresh_tdx_servers,
    resolve_tdx_servers,
)

logger = logging.getLogger(__name__)

# 默认探测参数（缓存为空或取数失败触发全量探测时使用）
DEFAULT_PROBE_SYMBOL = "600519"  # 贵州茅台，用于探测
DEFAULT_PROBE_COUNT = 5  # 探测时获取的K线数量
DEFAULT_CONNECT_TIMEOUT = 4  # 单台服务器连接超时（秒）
DEFAULT_TOTAL_TIMEOUT = 10  # 整轮探测总超时（秒）
DEFAULT_MAX_WORKERS = 20  # 并发探测线程数

ServerSource = Literal["cache", "probe", ""]


class TdxServerManager:
    """
    通达信服务器管理器

    功能：
    1. 启动时读取缓存首选服务器（非必要不探测）
    2. 缓存为空时并发探测并写入 tdx_servers.json
    3. 缓存首选取数失败时触发一次并发探测刷新
    4. 在已解析的服务器列表内支持故障切换
    """

    def __init__(
        self,
        probe_symbol: str = DEFAULT_PROBE_SYMBOL,
        probe_count: int = DEFAULT_PROBE_COUNT,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        total_timeout: float = DEFAULT_TOTAL_TIMEOUT,
        max_workers: int = DEFAULT_MAX_WORKERS,
    ):
        """
        初始化服务器管理器

        Args:
            probe_symbol: 用于探测的股票代码，默认 600519（贵州茅台）
            probe_count: 探测时获取的K线数量
            connect_timeout: 单台服务器连接超时（秒）
            total_timeout: 整轮探测总超时（秒）
            max_workers: 并发探测线程数
        """
        self._probe_symbol = probe_symbol
        self._probe_count = probe_count
        self._connect_timeout = connect_timeout
        self._total_timeout = total_timeout
        self._max_workers = max_workers

        # 当前可用服务器列表（resolve 后按策略填充，缓存命中时通常只有 1 台）
        self._servers: List[Tuple[str, int]] = []
        # 服务器来源：cache=直接读缓存，probe=并发探测得到
        self._server_source: ServerSource = ""
        # 当前使用的服务器索引
        self._current_index: int = 0
        # 缓存首选取数失败后是否已触发过全量探测（每轮 resolve 重置）
        self._failure_refreshed: bool = False
        # 服务器列表锁
        self._lock = threading.RLock()
        # 串行化失败后的全量探测，避免并发请求重复刷新缓存。
        self._refresh_lock = threading.Lock()
        # 上次解析时间
        self._last_resolve_time: float = 0
        # 最近一次全量探测耗时（仅 source=probe 时有意义）
        self._probe_duration: float = 0

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
        启动服务器管理器：读取缓存或首次探测。

        Returns:
            是否成功解析到可用服务器
        """
        logger.info("启动 TdxServerManager...")
        return self.resolve()

    def stop(self):
        """停止服务器管理器（保留接口，当前无后台线程）。"""
        logger.info("停止 TdxServerManager...")

    def resolve(self) -> bool:
        """
        解析可用服务器：有缓存则直接用首个 IP，缓存为空才并发探测。

        Returns:
            是否成功解析到可用服务器
        """
        logger.info("解析通达信服务器（优先使用缓存）...")
        start_time = time.time()

        try:
            resolved = resolve_tdx_servers(
                self._probe_symbol,
                count=self._probe_count,
                connect_timeout=self._connect_timeout,
                total_timeout=self._total_timeout,
                max_workers=self._max_workers,
            )
            elapsed = time.time() - start_time
            self._apply_resolved(resolved, elapsed=elapsed)

            if self._servers:
                primary = self._servers[0]
                logger.info(
                    "服务器解析完成: 来源=%s, 可用 %d 台, 首选 %s:%d, 耗时 %.2f 秒",
                    self._server_source,
                    len(self._servers),
                    primary[0],
                    primary[1],
                    elapsed,
                )
                return True

            logger.warning("服务器解析完成: 未找到可用服务器，耗时 %.2f 秒", elapsed)
            return False

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error("服务器解析失败: %s，耗时 %.2f 秒", e, elapsed)
            return False

    def refresh_on_failure(self) -> bool:
        """
        缓存首选服务器取数失败后，并发探测并更新 tdx_servers.json。

        每个 resolve 周期内最多触发一次，避免反复全量扫描。

        Returns:
            是否成功刷新并得到可用服务器
        """
        with self._refresh_lock:
            with self._lock:
                if self._server_source != "cache" or self._failure_refreshed:
                    logger.info("本轮已执行过失败刷新，跳过重复探测")
                    return bool(self._servers)
                self._failure_refreshed = True

            logger.info("缓存首选服务器取数失败，开始并发探测并更新缓存...")
            start_time = time.time()

            try:
                resolved = probe_and_refresh_tdx_servers(
                    self._probe_symbol,
                    count=self._probe_count,
                    connect_timeout=self._connect_timeout,
                    total_timeout=self._total_timeout,
                    max_workers=self._max_workers,
                )
                elapsed = time.time() - start_time
                self._apply_resolved(resolved, elapsed=elapsed)

                if self._servers:
                    primary = self._servers[0]
                    logger.info(
                        "失败刷新完成: 可用 %d 台, 新首选 %s:%d, 耗时 %.2f 秒",
                        len(self._servers),
                        primary[0],
                        primary[1],
                        elapsed,
                    )
                    return True

                logger.error("失败刷新后仍未找到可用服务器，耗时 %.2f 秒", elapsed)
                return False

            except Exception as e:
                elapsed = time.time() - start_time
                logger.error("失败刷新探测异常: %s，耗时 %.2f 秒", e, elapsed)
                return False

    def should_refresh_on_failure(self) -> bool:
        """当前是否应在取数失败时触发全量探测（仅缓存首选且尚未刷新过）。"""
        with self._lock:
            return self._server_source == "cache" and not self._failure_refreshed

    def _apply_resolved(self, resolved, *, elapsed: float) -> None:
        """将 resolve / probe_and_refresh 结果写入内存状态。"""
        with self._lock:
            self._servers = list(resolved.servers)
            self._server_source = resolved.source
            self._current_index = 0
            self._last_resolve_time = time.time()
            if resolved.source == "probe":
                self._probe_duration = elapsed
            if resolved.source == "cache":
                # 新一轮缓存命中时，允许后续再次因失败触发探测
                self._failure_refreshed = False

    def get_current_server(self) -> Optional[Tuple[str, int]]:
        """
        获取当前可用服务器

        Returns:
            (host, port) 元组，如果没有可用服务器则返回 None
        """
        with self._lock:
            if not self._servers:
                return None
            return self._servers[self._current_index]

    def switch_to_next_server(self) -> Optional[Tuple[str, int]]:
        """
        切换到下一个可用服务器

        当当前服务器出现问题时调用，循环切换到列表中的下一个服务器。

        Returns:
            新的 (host, port) 元组，如果没有更多服务器可切换则返回 None
        """
        with self._lock:
            if not self._servers:
                logger.warning("没有可用服务器，无法切换")
                return None

            if len(self._servers) <= 1:
                logger.warning("仅有一台服务器，无法切换")
                return None

            old_index = self._current_index
            self._current_index = (self._current_index + 1) % len(self._servers)
            new_server = self._servers[self._current_index]

            old_host, old_port = self._servers[old_index]
            logger.info(
                "切换服务器: [%d] %s:%d -> [%d] %s:%d",
                old_index,
                old_host,
                old_port,
                self._current_index,
                new_server[0],
                new_server[1],
            )
            return new_server

    def get_all_servers(self) -> List[Tuple[str, int, str]]:
        """
        获取所有可用服务器列表

        Returns:
            列表，每个元素为 (host, port, name) 元组（name 暂为空）
        """
        with self._lock:
            return [(host, port, "") for host, port in self._servers]

    def get_server_count(self) -> int:
        """获取可用服务器数量"""
        with self._lock:
            return len(self._servers)

    def get_server_source(self) -> ServerSource:
        """获取当前服务器列表来源（cache / probe）。"""
        with self._lock:
            return self._server_source

    def get_status(self) -> dict:
        """
        获取服务器管理器状态

        Returns:
            包含状态信息的字典
        """
        with self._lock:
            current_server = None
            if self._servers:
                host, port = self._servers[self._current_index]
                current_server = {
                    "host": host,
                    "port": port,
                    "name": "",
                }

            return {
                "available_count": len(self._servers),
                "current_index": self._current_index,
                "current_server": current_server,
                "server_source": self._server_source,
                "failure_refreshed": self._failure_refreshed,
                "last_resolve_time": self._last_resolve_time,
                "probe_duration": self._probe_duration,
                "probe_symbol": self._probe_symbol,
            }

    # 兼容旧调用方
    def probe(self) -> bool:
        """兼容旧接口，等价于 resolve()。"""
        return self.resolve()


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
