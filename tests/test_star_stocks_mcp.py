"""star_stocks MCP 服务测试。"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.mcp_servers.star_stocks.config import get_star_stocks_root, init_star_stocks_env
from src.mcp_servers.star_stocks.service import StarStocksService


class TestStarStocksConfig:
    def test_get_star_stocks_root(self):
        root = get_star_stocks_root()
        assert root.name == "star_stocks"
        assert (root / "pyproject.toml").exists()

    def test_init_star_stocks_env(self, monkeypatch):
        root = get_star_stocks_root()
        monkeypatch.chdir(root)
        init_star_stocks_env()


class TestStarStocksService:
    def test_init(self):
        service = StarStocksService()
        assert service.name == "star-stocks"

    @patch("src.mcp_servers.star_stocks.service.db_session")
    def test_list_themes_empty(self, mock_db_session):
        mock_db = MagicMock()
        mock_db_session.return_value.__enter__.return_value = mock_db

        with patch(
            "src.mcp_servers.star_stocks.service.ThemeService.list_themes",
            return_value=[],
        ):
            service = StarStocksService()
            tools = {t.name: t for t in service.mcp._tool_manager._tools.values()}
            # FastMCP internal API may differ; call tool function via registered name
            list_fn = None
            for name, tool in service.mcp._tool_manager._tools.items():
                if name == "list_themes":
                    list_fn = tool.fn
                    break
            assert list_fn is not None
            result = list_fn()
            assert '"themes"' not in result
            assert result.strip().startswith("[")

    @patch("src.mcp_servers.star_stocks.service.db_session")
    def test_get_theme_not_found(self, mock_db_session):
        mock_db = MagicMock()
        mock_db_session.return_value.__enter__.return_value = mock_db

        with patch(
            "src.mcp_servers.star_stocks.service.ThemeService.get_theme",
            return_value=None,
        ):
            service = StarStocksService()
            get_fn = service.mcp._tool_manager._tools["get_theme"].fn
            result = get_fn(theme_id=999)
            assert '"error"' in result
            assert "不存在" in result


def test_start_script_exists():
    root = Path(__file__).resolve().parents[1]
    assert (root / "start_star_stocks_service.py").exists()
