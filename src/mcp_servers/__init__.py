# MCP Servers 包
# 包含各种MCP服务实现

from .base import BaseMCPServer
from .kph_market_data.service import KPHMarketDataService

__all__ = ["BaseMCPServer", "KPHMarketDataService"]


def __getattr__(name):
    """Lazy import: StarStocksService 需要 sqlalchemy，仅在实际使用时加载。"""
    if name == "StarStocksService":
        from .star_stocks.service import StarStocksService
        return StarStocksService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
