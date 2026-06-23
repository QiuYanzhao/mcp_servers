"""
题材标志性个股（star_stocks）MCP 服务

提供题材、细分方向、个股及关联条目的增删改查，以及全量概览与 Markdown 导入。
"""

import logging
from pathlib import Path
from typing import Literal

from ..base import BaseMCPServer
from .config import get_star_stocks_root, init_star_stocks_env
from .db import db_session
from .helpers import err, ok

init_star_stocks_env()

from star_stocks.models import Stock, ThemeStock  # noqa: E402
from star_stocks.schemas import (  # noqa: E402
    StockCreate,
    SubDirectionCreate,
    SubDirectionPatch,
    SubDirectionOut,
    StockOut,
    ThemeCreate,
    ThemeOut,
    ThemeStockCreate,
    ThemeStockOut,
    ThemeStockPatch,
    ThemeUpdate,
)
from star_stocks.services import (  # noqa: E402
    ImportService,
    OverviewService,
    StockService,
    SubDirectionService,
    ThemeService,
    ThemeStockService,
)

logger = logging.getLogger(__name__)

RoleType = Literal["main_line", "rotation", "new", "normal"]
StockType = Literal["权重", "身位股", "人气股", "中军", "涨停个股"]


class StarStocksService(BaseMCPServer):
    """star_stocks 数据维护 MCP 服务。"""

    def __init__(self):
        super().__init__("star-stocks", "1.0.0")
        self.register_tools()
        self.register_resources()
        logger.info("star_stocks MCP 服务初始化完成")

    def register_tools(self):
        """注册 CRUD 工具。"""

        @self.mcp.tool()
        def list_themes(role_type: RoleType | None = None) -> str:
            """
            列出所有炒作题材（方向）。

            Args:
                role_type: 可选，按角色筛选：main_line / rotation / new / normal
            """
            try:
                with db_session() as db:
                    themes = ThemeService.list_themes(db, role_type)
                    return ok([ThemeOut.model_validate(t) for t in themes])
            except Exception as e:
                logger.exception("list_themes failed")
                return err(str(e))

        @self.mcp.tool()
        def get_theme(theme_id: int) -> str:
            """根据 ID 获取单个题材详情。"""
            try:
                with db_session() as db:
                    theme = ThemeService.get_theme(db, theme_id)
                    if not theme:
                        return err(f"题材 {theme_id} 不存在")
                    return ok(ThemeOut.model_validate(theme))
            except Exception as e:
                logger.exception("get_theme failed")
                return err(str(e))

        @self.mcp.tool()
        def create_theme(
            name: str,
            role_type: RoleType = "normal",
            rotation_rank: int | None = None,
            summary: str | None = None,
            sort_order: int = 0,
            is_active: bool = True,
        ) -> str:
            """
            创建炒作题材。

            Args:
                name: 题材名称
                role_type: 角色类型，默认 normal
                rotation_rank: 轮动序号（轮动题材时填写）
                summary: 摘要
                sort_order: 排序值
                is_active: 是否启用
            """
            try:
                data = ThemeCreate(
                    name=name,
                    role_type=role_type,
                    rotation_rank=rotation_rank,
                    summary=summary,
                    sort_order=sort_order,
                    is_active=is_active,
                )
                with db_session() as db:
                    theme = ThemeService.create_theme(db, data)
                    return ok(ThemeOut.model_validate(theme))
            except Exception as e:
                logger.exception("create_theme failed")
                return err(str(e))

        @self.mcp.tool()
        def update_theme(
            theme_id: int,
            name: str | None = None,
            role_type: RoleType | None = None,
            rotation_rank: int | None = None,
            summary: str | None = None,
            sort_order: int | None = None,
            is_active: bool | None = None,
        ) -> str:
            """更新题材信息，仅传入需要修改的字段。"""
            try:
                fields = {
                    "name": name,
                    "role_type": role_type,
                    "rotation_rank": rotation_rank,
                    "summary": summary,
                    "sort_order": sort_order,
                    "is_active": is_active,
                }
                payload = {k: v for k, v in fields.items() if v is not None}
                if not payload:
                    return err("请至少提供一个要更新的字段")
                data = ThemeUpdate(**payload)
                with db_session() as db:
                    theme = ThemeService.get_theme(db, theme_id)
                    if not theme:
                        return err(f"题材 {theme_id} 不存在")
                    theme = ThemeService.update_theme(db, theme, data)
                    return ok(ThemeOut.model_validate(theme))
            except Exception as e:
                logger.exception("update_theme failed")
                return err(str(e))

        @self.mcp.tool()
        def delete_theme(theme_id: int) -> str:
            """删除题材（级联删除其细分方向与关联个股条目）。"""
            try:
                with db_session() as db:
                    if not ThemeService.get_theme(db, theme_id):
                        return err(f"题材 {theme_id} 不存在")
                    ThemeService.delete_theme(db, theme_id)
                    return ok({"deleted": True, "theme_id": theme_id})
            except Exception as e:
                logger.exception("delete_theme failed")
                return err(str(e))

        @self.mcp.tool()
        def list_sub_directions(theme_id: int) -> str:
            """列出某题材下的所有细分方向。"""
            try:
                with db_session() as db:
                    subs = SubDirectionService.list_by_theme(db, theme_id)
                    return ok([SubDirectionOut.model_validate(s) for s in subs])
            except Exception as e:
                logger.exception("list_sub_directions failed")
                return err(str(e))

        @self.mcp.tool()
        def create_sub_direction(
            theme_id: int,
            name: str,
            score: int | None = None,
            sort_order: int = 0,
        ) -> str:
            """
            在某题材下创建细分方向。

            Args:
                theme_id: 所属题材 ID
                name: 细分方向名称
                score: 评分 0-100
                sort_order: 排序值
            """
            try:
                data = SubDirectionCreate(
                    theme_id=theme_id,
                    name=name,
                    score=score,
                    sort_order=sort_order,
                )
                with db_session() as db:
                    sub = SubDirectionService.create(db, data)
                    return ok(SubDirectionOut.model_validate(sub))
            except Exception as e:
                logger.exception("create_sub_direction failed")
                return err(str(e))

        @self.mcp.tool()
        def update_sub_direction(
            sub_direction_id: int,
            name: str | None = None,
            score: int | None = None,
            sort_order: int | None = None,
        ) -> str:
            """更新细分方向，仅传入需要修改的字段。"""
            try:
                fields = {"name": name, "score": score, "sort_order": sort_order}
                payload = {k: v for k, v in fields.items() if v is not None}
                if not payload:
                    return err("请至少提供一个要更新的字段")
                data = SubDirectionPatch(**payload)
                with db_session() as db:
                    sub = SubDirectionService.get(db, sub_direction_id)
                    if not sub:
                        return err(f"细分方向 {sub_direction_id} 不存在")
                    sub = SubDirectionService.patch(db, sub, data)
                    return ok(SubDirectionOut.model_validate(sub))
            except Exception as e:
                logger.exception("update_sub_direction failed")
                return err(str(e))

        @self.mcp.tool()
        def delete_sub_direction(sub_direction_id: int) -> str:
            """删除细分方向（级联删除其下关联个股条目）。"""
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
        def list_stocks(keyword: str | None = None) -> str:
            """搜索个股，可按代码或名称模糊匹配。"""
            try:
                with db_session() as db:
                    stocks = StockService.search(db, keyword)
                    return ok([StockOut.model_validate(s) for s in stocks])
            except Exception as e:
                logger.exception("list_stocks failed")
                return err(str(e))

        @self.mcp.tool()
        def create_stock(code: str, name: str) -> str:
            """创建或更新个股（按代码 upsert）。"""
            try:
                data = StockCreate(code=code, name=name)
                with db_session() as db:
                    stock = StockService.create(db, data)
                    db.commit()
                    db.refresh(stock)
                    return ok(StockOut.model_validate(stock))
            except Exception as e:
                logger.exception("create_stock failed")
                return err(str(e))

        @self.mcp.tool()
        def delete_stock(stock_id: int) -> str:
            """删除个股（若仍有关联条目则失败）。"""
            try:
                with db_session() as db:
                    StockService.delete(db, stock_id)
                    return ok({"deleted": True, "stock_id": stock_id})
            except Exception as e:
                logger.exception("delete_stock failed")
                return err(str(e))

        @self.mcp.tool()
        def list_theme_stocks(
            theme_id: int | None = None,
            sub_direction_id: int | None = None,
        ) -> str:
            """
            列出题材或细分方向下的个股关联条目。

            theme_id 与 sub_direction_id 二选一。
            """
            try:
                if (theme_id is None) == (sub_direction_id is None):
                    return err("theme_id 与 sub_direction_id 必须二选一")
                with db_session() as db:
                    rows = ThemeStockService.list_entries(
                        db, theme_id=theme_id, sub_direction_id=sub_direction_id
                    )
                    items = []
                    for entry, stock in rows:
                        item = ThemeStockOut.model_validate(entry)
                        item.code = stock.code
                        item.name = stock.name
                        items.append(item)
                    return ok(items)
            except Exception as e:
                logger.exception("list_theme_stocks failed")
                return err(str(e))

        @self.mcp.tool()
        def create_theme_stock(
            stock_type: StockType,
            theme_id: int | None = None,
            sub_direction_id: int | None = None,
            stock_id: int | None = None,
            code: str | None = None,
            name: str | None = None,
            is_distinctive: bool = False,
            remark: str | None = None,
            score: int | None = None,
            sort_order: int = 0,
        ) -> str:
            """
            在题材或细分方向下添加个股关联。

            theme_id 与 sub_direction_id 二选一；stock_id 与 code+name 二选一。
            """
            try:
                data = ThemeStockCreate(
                    theme_id=theme_id,
                    sub_direction_id=sub_direction_id,
                    stock_id=stock_id,
                    code=code,
                    name=name,
                    stock_type=stock_type,
                    is_distinctive=is_distinctive,
                    remark=remark,
                    score=score,
                    sort_order=sort_order,
                )
                with db_session() as db:
                    entry = ThemeStockService.create(db, data)
                    stock = db.get(Stock, entry.stock_id)
                    item = ThemeStockOut.model_validate(entry)
                    if stock:
                        item.code = stock.code
                        item.name = stock.name
                    return ok(item)
            except Exception as e:
                logger.exception("create_theme_stock failed")
                return err(str(e))

        @self.mcp.tool()
        def update_theme_stock(
            entry_id: int,
            stock_type: StockType | None = None,
            is_distinctive: bool | None = None,
            remark: str | None = None,
            score: int | None = None,
            sort_order: int | None = None,
        ) -> str:
            """更新个股关联条目（类型、标志性、备注、评分等）。"""
            try:
                fields = {
                    "stock_type": stock_type,
                    "is_distinctive": is_distinctive,
                    "remark": remark,
                    "score": score,
                    "sort_order": sort_order,
                }
                payload = {k: v for k, v in fields.items() if v is not None}
                if not payload:
                    return err("请至少提供一个要更新的字段")
                data = ThemeStockPatch(**payload)
                with db_session() as db:
                    entry = db.get(ThemeStock, entry_id)
                    if not entry:
                        return err(f"关联条目 {entry_id} 不存在")
                    entry = ThemeStockService.patch(db, entry, data)
                    stock = db.get(Stock, entry.stock_id)
                    item = ThemeStockOut.model_validate(entry)
                    if stock:
                        item.code = stock.code
                        item.name = stock.name
                    return ok(item)
            except Exception as e:
                logger.exception("update_theme_stock failed")
                return err(str(e))

        @self.mcp.tool()
        def delete_theme_stock(entry_id: int) -> str:
            """删除个股关联条目。"""
            try:
                with db_session() as db:
                    if not db.get(ThemeStock, entry_id):
                        return err(f"关联条目 {entry_id} 不存在")
                    ThemeStockService.delete(db, entry_id)
                    return ok({"deleted": True, "entry_id": entry_id})
            except Exception as e:
                logger.exception("delete_theme_stock failed")
                return err(str(e))

        @self.mcp.tool()
        def get_overview(keyword: str | None = None) -> str:
            """获取全量题材树（题材 → 细分方向 → 个股），支持关键词过滤。"""
            try:
                with db_session() as db:
                    overview = OverviewService.build(db, keyword)
                    return ok(overview)
            except Exception as e:
                logger.exception("get_overview failed")
                return err(str(e))

        @self.mcp.tool()
        def import_markdown(
            file_path: str,
            dry_run: bool = False,
            force: bool = False,
        ) -> str:
            """
            从 Markdown 文件导入题材数据。

            Args:
                file_path: Markdown 文件绝对或相对路径
                dry_run: 仅预览，不写库
                force: 清空后全量导入
            """
            try:
                path = Path(file_path).expanduser()
                if not path.is_absolute():
                    path = get_star_stocks_root().parent / path
                if not path.exists():
                    return err(f"文件不存在: {path}")
                content = path.read_text(encoding="utf-8")
                with db_session() as db:
                    result = ImportService.import_markdown(
                        db, content, dry_run=dry_run, force=force
                    )
                    return ok(result)
            except Exception as e:
                logger.exception("import_markdown failed")
                return err(str(e))

    def register_resources(self):
        """注册服务信息资源。"""

        @self.mcp.resource("star-stocks://service/info")
        def get_service_info() -> str:
            root = get_star_stocks_root()
            return ok(
                {
                    "name": self.name,
                    "version": self.version,
                    "star_stocks_root": str(root),
                    "entities": ["theme", "sub_direction", "stock", "theme_stock"],
                    "features": [
                        "题材 CRUD",
                        "细分方向 CRUD",
                        "个股查询/创建/删除",
                        "题材-个股关联 CRUD",
                        "全量概览",
                        "Markdown 导入",
                    ],
                }
            )
