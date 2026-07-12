"""通达信服务器缓存优先与失败刷新策略测试。"""

import pytest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.mcp_servers.stock_market.data_fetcher import StockDataFetcher
from src.mcp_servers.stock_market.server_manager import (
    PROBE_EMPTY_ERROR,
    TdxServerManager,
    TdxServersUnavailableError,
)


@patch("src.mcp_servers.stock_market.server_manager.resolve_tdx_servers")
def test_manager_uses_cached_primary_without_probe(mock_resolve):
    """启动时应直接采用 resolve 返回的缓存首选服务器。"""
    mock_resolve.return_value = SimpleNamespace(
        servers=[("1.1.1.1", 7709)],
        source="cache",
    )
    manager = TdxServerManager()

    assert manager.start()
    assert manager.get_current_server() == ("1.1.1.1", 7709)
    assert manager.get_server_source() == "cache"
    assert manager.should_refresh_on_failure()


@patch("src.mcp_servers.stock_market.server_manager.probe_and_refresh_tdx_servers")
@patch("src.mcp_servers.stock_market.server_manager.resolve_tdx_servers")
def test_manager_refreshes_cache_after_actual_failure(mock_resolve, mock_refresh):
    """缓存服务器实际取数失败后应探测并切换到新的首选服务器。"""
    mock_resolve.return_value = SimpleNamespace(
        servers=[("1.1.1.1", 7709)],
        source="cache",
    )
    mock_refresh.return_value = SimpleNamespace(
        servers=[("2.2.2.2", 7709), ("3.3.3.3", 7709)],
        source="probe",
    )
    manager = TdxServerManager()
    assert manager.start()

    assert manager.refresh_on_failure()
    assert manager.get_current_server() == ("2.2.2.2", 7709)
    assert manager.get_server_source() == "probe"
    assert not manager.should_refresh_on_failure()
    mock_refresh.assert_called_once()


@patch("src.mcp_servers.stock_market.server_manager.probe_and_refresh_tdx_servers")
@patch("src.mcp_servers.stock_market.server_manager.resolve_tdx_servers")
def test_manager_raises_when_probe_returns_empty(mock_resolve, mock_refresh):
    """缓存服务器失败后，若并发探测结果为空应直接抛错。"""
    mock_resolve.return_value = SimpleNamespace(
        servers=[("1.1.1.1", 7709)],
        source="cache",
    )
    mock_refresh.return_value = SimpleNamespace(servers=[], source="probe")
    manager = TdxServerManager()
    assert manager.start()

    with pytest.raises(TdxServersUnavailableError, match=PROBE_EMPTY_ERROR):
        manager.refresh_on_failure()


@patch("src.mcp_servers.stock_market.data_fetcher.get_server_manager")
def test_fetcher_returns_error_when_probe_empty(mock_get_manager):
    """并发探测为空时，MCP 取数应直接返回失败，不再继续重试。"""
    manager = Mock()
    manager.should_refresh_on_failure.return_value = True
    manager.refresh_on_failure.side_effect = TdxServersUnavailableError(PROBE_EMPTY_ERROR)
    mock_get_manager.return_value = manager

    fetcher = StockDataFetcher(use_server_manager=True)
    operation = Mock(side_effect=ConnectionError("timeout"))

    with pytest.raises(TdxServersUnavailableError, match=PROBE_EMPTY_ERROR):
        fetcher._execute_with_retry("测试取数", operation)

    manager.refresh_on_failure.assert_called_once()
    assert operation.call_count == 1


@patch("src.mcp_servers.stock_market.data_fetcher.get_server_manager")
def test_get_daily_kline_returns_error_for_mcp_when_probe_empty(mock_get_manager):
    """并发探测为空时，对外接口应返回带 error 的失败结果。"""
    manager = Mock()
    manager.get_current_server.return_value = ("1.1.1.1", 7709)
    manager.should_refresh_on_failure.return_value = True
    manager.refresh_on_failure.side_effect = TdxServersUnavailableError(PROBE_EMPTY_ERROR)
    mock_get_manager.return_value = manager

    fetcher = StockDataFetcher(use_server_manager=True)
    fetcher._client = Mock()
    fetcher._client.bars.return_value = None
    fetcher._current_server = ("1.1.1.1", 7709)

    result = fetcher.get_daily_kline("600519", count=5)

    assert result["error"] == PROBE_EMPTY_ERROR
    assert result["data"] == []
    manager.refresh_on_failure.assert_called_once()


@patch("src.mcp_servers.stock_market.data_fetcher.get_server_manager")
def test_fetcher_triggers_probe_only_after_operation_failure(mock_get_manager):
    """取数异常时刷新缓存，然后使用刷新后的服务器重试。"""
    manager = Mock()
    manager.should_refresh_on_failure.return_value = True
    manager.refresh_on_failure.return_value = True
    mock_get_manager.return_value = manager

    fetcher = StockDataFetcher(use_server_manager=True)
    operation = Mock(side_effect=[ConnectionError("timeout"), {"data": [1]}])

    result = fetcher._execute_with_retry("测试取数", operation)

    assert result == {"data": [1]}
    manager.refresh_on_failure.assert_called_once()
    manager.switch_to_next_server.assert_not_called()
