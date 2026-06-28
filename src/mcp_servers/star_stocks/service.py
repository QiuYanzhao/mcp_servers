"""
题材标志性个股（star_stocks）MCP 服务

按使用场景提供查询、新增、更新、删除工具。
"""

import logging
from typing import Literal

from ..base import BaseMCPServer
from .config import init_star_stocks_env
from .db import db_session
from .helpers import err, ok

init_star_stocks_env()

from star_stocks.models import ThemeStock  # noqa: E402
from star_stocks.schemas import (  # noqa: E402
    SubDirectionCreate,
    SubDirectionOut,
    ThemeCreate,
    ThemeMcpUpdate,
    ThemeOut,
    ThemeStockCreate,
    ThemeStockMcpUpdate,
    ThemeStockOut,
    ThemeStockPatch,
    ThemeUpdate,
)
from star_stocks.services.mcp_query import McpQueryService  # noqa: E402
from star_stocks.services import (  # noqa: E402
    SubDirectionService,
    ThemeService,
    ThemeStockService,
)

logger = logging.getLogger(__name__)

RoleType = Literal["main_line", "rotation", "normal"]
StockType = Literal["权重", "身位股", "人气股", "中军", "涨停个股"]


class StarStocksService(BaseMCPServer):
    """star_stocks 数据维护 MCP 服务。"""

    def __init__(self):
        super().__init__("star-stocks", "2.1.0")
        self.register_tools()
        logger.info("star_stocks MCP 服务初始化完成")

    def register_tools(self):
        # ── 查询 ──

        @self.mcp.tool()
        def list_themes_with_sub_directions() -> str:
            """查询所有题材及包含的细分方向（不含个股），细分方向按评分从高到低排序（只读）。"""
            try:
                with db_session() as db:
                    data = McpQueryService.list_themes_with_sub_directions(db)
                    return ok(data)
            except Exception as e:
                logger.exception("list_themes_with_sub_directions failed")
                return err(str(e))

        @self.mcp.tool()
        def list_main_rotation_trees() -> str:
            """
            查询主线与轮动题材的完整树（题材 → 细分方向 → 个股）。
            主线在前、轮动在后；细分方向与个股均按评分降序（只读）。
            """
            try:
                with db_session() as db:
                    data = McpQueryService.list_main_rotation_trees(db)
                    return ok(data)
            except Exception as e:
                logger.exception("list_main_rotation_trees failed")
                return err(str(e))

        @self.mcp.tool()
        def get_theme_tree(theme_id: int) -> str:
            """
            查询指定题材的完整树（题材 → 细分方向 → 个股）。
            细分方向与个股均按评分降序（只读）。
            """
            try:
                with db_session() as db:
                    tree = McpQueryService.get_theme_tree(db, theme_id)
                    if not tree:
                        return err(f"题材 {theme_id} 不存在")
                    return ok(tree)
            except Exception as e:
                logger.exception("get_theme_tree failed")
                return err(str(e))

        # ── 新增 ──

        @self.mcp.tool()
        def create_theme(
            name: str,
            role_type: RoleType = "normal",
            rotation_rank: int | None = None,
            summary: str | None = None,
        ) -> str:
            """新增炒作方向（题材）。"""
            try:
                data = ThemeCreate(
                    name=name,
                    role_type=role_type,
                    rotation_rank=rotation_rank,
                    summary=summary,
                )
                with db_session() as db:
                    theme = ThemeService.create_theme(db, data)
                    return ok(ThemeOut.model_validate(theme))
            except Exception as e:
                logger.exception("create_theme failed")
                return err(str(e))

        @self.mcp.tool()
        def create_sub_direction(theme_id: int, name: str) -> str:
            """向指定题材下新增细分方向（不可设置评分）。"""
            try:
                data = SubDirectionCreate(theme_id=theme_id, name=name)
                with db_session() as db:
                    sub = SubDirectionService.create(db, data)
                    return ok(SubDirectionOut.model_validate(sub))
            except Exception as e:
                logger.exception("create_sub_direction failed")
                return err(str(e))

        @self.mcp.tool()
        def create_theme_stock(
            stock_type: StockType,
            code: str,
            name: str,
            theme_id: int | None = None,
            sub_direction_id: int | None = None,
            is_distinctive: bool = False,
            remark: str | None = None,
        ) -> str:
            """向题材或细分方向下新增个股。theme_id 与 sub_direction_id 二选一（不可设置评分）。"""
            try:
                data = ThemeStockCreate(
                    theme_id=theme_id,
                    sub_direction_id=sub_direction_id,
                    code=code,
                    name=name,
                    stock_type=stock_type,
                    is_distinctive=is_distinctive,
                    remark=remark,
                )
                with db_session() as db:
                    entry = ThemeStockService.create(db, data)
                    return ok(ThemeStockOut.model_validate(entry))
            except Exception as e:
                logger.exception("create_theme_stock failed")
                return err(str(e))

        # ── 更新 ──

        @self.mcp.tool()
        def update_theme(
            theme_id: int,
            role_type: RoleType | None = None,
            summary: str | None = None,
        ) -> str:
            """更新题材：仅允许修改角色（role_type）与摘要（summary/备注）。"""
            try:
                if role_type is None and summary is None:
                    return err("请至少提供 role_type 或 summary")
                data = ThemeMcpUpdate(role_type=role_type, summary=summary)
                patch = ThemeUpdate(**data.model_dump(exclude_unset=True))
                with db_session() as db:
                    theme = ThemeService.get_theme(db, theme_id)
                    if not theme:
                        return err(f"题材 {theme_id} 不存在")
                    theme = ThemeService.update_theme(db, theme, patch)
                    return ok(ThemeOut.model_validate(theme))
            except Exception as e:
                logger.exception("update_theme failed")
                return err(str(e))

        @self.mcp.tool()
        def update_theme_stock(
            entry_id: int,
            stock_type: StockType | None = None,
            is_distinctive: bool | None = None,
            remark: str | None = None,
        ) -> str:
            """更新个股：仅允许修改备注、类型、是否最具辨识度（不可修改评分）。"""
            try:
                fields = {
                    "stock_type": stock_type,
                    "is_distinctive": is_distinctive,
                    "remark": remark,
                }
                payload = {k: v for k, v in fields.items() if v is not None}
                if not payload:
                    return err("请至少提供一个要更新的字段")
                data = ThemeStockMcpUpdate(**payload)
                patch = ThemeStockPatch(**data.model_dump(exclude_unset=True))
                with db_session() as db:
                    entry = db.get(ThemeStock, entry_id)
                    if not entry:
                        return err(f"个股条目 {entry_id} 不存在")
                    entry = ThemeStockService.patch(db, entry, patch)
                    return ok(ThemeStockOut.model_validate(entry))
            except Exception as e:
                logger.exception("update_theme_stock failed")
                return err(str(e))

        # ── 删除 ──

        @self.mcp.tool()
        def delete_theme_stock(entry_id: int) -> str:
            """删除细分方向或题材下的指定个股条目。"""
            try:
                with db_session() as db:
                    if not db.get(ThemeStock, entry_id):
                        return err(f"个股条目 {entry_id} 不存在")
                    ThemeStockService.delete(db, entry_id)
                    return ok({"deleted": True, "entry_id": entry_id})
            except Exception as e:
                logger.exception("delete_theme_stock failed")
                return err(str(e))

        @self.mcp.tool()
        def delete_sub_direction(sub_direction_id: int) -> str:
            """删除指定细分方向（一并删除其下关联个股）。"""
            try:
                with db_session() as db:
                    if not SubDirectionService.get(db, sub_direction_id):
                        return err(f"细分方向 {sub_direction_id} 不存在")
                    SubDirectionService.delete(db, sub_direction_id)
                    return ok({"deleted": True, "sub_direction_id": sub_direction_id})
            except Exception as e:
                logger.exception("delete_sub_direction failed")
                return err(str(e))

        @self.mcp.tool()
        def delete_theme(theme_id: int) -> str:
            """删除指定题材（一并删除关联细分方向与个股）。"""
            try:
                with db_session() as db:
                    if not ThemeService.get_theme(db, theme_id):
                        return err(f"题材 {theme_id} 不存在")
                    ThemeService.delete_theme(db, theme_id)
                    return ok({"deleted": True, "theme_id": theme_id})
            except Exception as e:
                logger.exception("delete_theme failed")
                return err(str(e))
