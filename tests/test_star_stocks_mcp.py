"""star_stocks MCP 服务测试。"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.mcp_servers.star_stocks.config import get_star_stocks_root, init_star_stocks_env
from src.mcp_servers.star_stocks.service import StarStocksService

EXPECTED_TOOLS = {
    "list_themes_with_sub_directions",
    "list_main_rotation_trees",
    "get_theme_tree",
    "create_theme",
    "create_sub_direction",
    "create_theme_stock",
    "update_theme",
    "update_sub_direction",
    "update_theme_stock",
    "delete_theme_stock",
    "delete_sub_direction",
    "delete_theme",
}


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
    def test_init_registers_expected_tools(self):
        service = StarStocksService()
        assert service.name == "star-stocks"
        registered = set(service.mcp._tool_manager._tools.keys())
        assert registered == EXPECTED_TOOLS

    @patch("src.mcp_servers.star_stocks.service.db_session")
    def test_list_themes_with_sub_directions_empty(self, mock_db_session):
        mock_db = MagicMock()
        mock_db_session.return_value.__enter__.return_value = mock_db

        with patch(
            "src.mcp_servers.star_stocks.service.McpQueryService.list_themes_with_sub_directions",
            return_value=[],
        ):
            service = StarStocksService()
            fn = service.mcp._tool_manager._tools["list_themes_with_sub_directions"].fn
            result = fn()
            assert result.strip() == "[]"

    @patch("src.mcp_servers.star_stocks.service.db_session")
    def test_get_theme_tree_not_found(self, mock_db_session):
        mock_db = MagicMock()
        mock_db_session.return_value.__enter__.return_value = mock_db

        with patch(
            "src.mcp_servers.star_stocks.service.McpQueryService.get_theme_tree",
            return_value=None,
        ):
            service = StarStocksService()
            fn = service.mcp._tool_manager._tools["get_theme_tree"].fn
            result = fn(theme_id=999)
            assert '"error"' in result
            assert "不存在" in result


def test_start_script_exists():
    root = Path(__file__).resolve().parents[1]
    assert (root / "start_star_stocks_service.py").exists()
