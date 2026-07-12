"""从 star_stocks 批量查询个股标签。"""

from __future__ import annotations

import logging

from star_stocks.database import db_session
from star_stocks.external.kaipanhong import normalize_stock_code
from star_stocks.services.stock_info import StockInfoService

logger = logging.getLogger(__name__)


def lookup_stock_tags(codes: list[str]) -> dict[str, str | None]:
    """按证券代码批量查询标签，键为归一化后的代码。"""
    if not codes:
        return {}
    try:
        with db_session() as db:
            return StockInfoService.lookup_tags_by_codes(db, codes)
    except Exception:
        logger.exception("批量查询个股标签失败")
        return {normalize_stock_code(code): None for code in codes if code}
