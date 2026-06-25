"""开盘红平台 API 响应数据模型

使用 dataclass 定义各接口的响应结构，提供 from_dict / from_list 工厂方法
将原始 JSON 转换为强类型对象，便于 IDE 补全和类型检查。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LiveContentItem:
    """概念点接口 - 单条直播内容"""

    id: str = ""
    uid: str = ""
    time: str = ""
    comment: str = ""
    type: str = ""
    plate_code: str = ""
    plate_name: str = ""
    plate_je: str = ""
    plate_zdf: str = ""
    theme_info: list = field(default_factory=list)
    interpretation: str = ""
    is_chart: str = ""
    share_data: dict = field(default_factory=dict)
    user_name: str = ""
    image: str = ""
    stock: list[list] = field(default_factory=list)
    dis_stock: list[list] = field(default_factory=list)
    theme_class_info: list = field(default_factory=list)
    style_index: list = field(default_factory=list)
    boom_reason: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> LiveContentItem:
        return cls(
            id=data.get("ID", ""),
            uid=data.get("UID", ""),
            time=data.get("Time", 0),
            comment=data.get("Comment", ""),
            type=data.get("Type", ""),
            plate_code=data.get("PlateCode", ""),
            plate_name=data.get("PlateName", ""),
            plate_je=data.get("PlateJE", ""),
            plate_zdf=data.get("PlateZDF", ""),
            theme_info=data.get("ThemeInfo", []),
            interpretation=data.get("Interpretation", ""),
            is_chart=data.get("IsChart", ""),
            share_data=data.get("ShareData", {}),
            user_name=data.get("UserName", ""),
            image=data.get("Image", ""),
            stock=data.get("Stock", []),
            dis_stock=data.get("DisStock", []),
            theme_class_info=data.get("ThemeClassInfo", []),
            style_index=data.get("styleIndex", []),
            boom_reason=data.get("BoomReason", ""),
        )


@dataclass
class LiveContentResponse:
    """概念点接口 - 完整响应"""

    items: list[LiveContentItem] = field(default_factory=list)
    errcode: str = ""
    notice: str = ""
    status: int = 0
    server_time: int = 0
    date: str = ""
    ttag: float = 0.0

    @classmethod
    def from_dict(cls, data: dict) -> LiveContentResponse:
        raw_list = data.get("list", data.get("List", []))
        return cls(
            items=[LiveContentItem.from_dict(item) for item in raw_list],
            errcode=data.get("errcode", ""),
            notice=data.get("Notice", ""),
            status=data.get("Status", 0),
            server_time=data.get("Time", 0),
            date=data.get("date", ""),
            ttag=data.get("ttag", 0.0),
        )


@dataclass
class LimitUpStock:
    """涨停天梯接口 - 个股数据"""

    code: str = ""
    name: str = ""
    board_height: int = 0
    limit_up_time: int = 0
    theme_code: str = ""
    theme_name: str = ""
    theme_zt_count: int = 0
    amount_in: int = 0
    amount_out: int = 0
    tags: str | None = None

    @classmethod
    def from_list(cls, data: list) -> LimitUpStock:
        return cls(
            code=data[0] if len(data) > 0 else "",
            name=data[1] if len(data) > 1 else "",
            board_height=data[2] if len(data) > 2 else 0,
            limit_up_time=data[3] if len(data) > 3 else 0,
            theme_code=data[4] if len(data) > 4 else "",
            theme_name=data[5] if len(data) > 5 else "",
            theme_zt_count=data[8] if len(data) > 8 else 0,
            amount_in=data[9] if len(data) > 9 else 0,
            amount_out=data[10] if len(data) > 10 else 0,
        )


@dataclass
class LimitUpTheme:
    """涨停天梯接口 - 题材数据

    对应 ZhuShuList 数组中的每个元素：
    [0] 题材代码, [1] 题材名称, [2] 题材涨停家数,
    [3] 成交额（元）, [4] 涨停个股代码（逗号分隔）
    """

    code: str = ""
    name: str = ""
    zt_count: int = 0
    turnover: int = 0
    stock_codes: str = ""

    @classmethod
    def from_list(cls, data: list) -> LimitUpTheme:
        return cls(
            code=data[0] if len(data) > 0 else "",
            name=data[1] if len(data) > 1 else "",
            zt_count=data[2] if len(data) > 2 else 0,
            turnover=data[3] if len(data) > 3 else 0,
            stock_codes=data[4] if len(data) > 4 else "",
        )


@dataclass
class LimitUpLadderResponse:
    """涨停天梯接口 - 完整响应"""

    stocks: list[LimitUpStock] = field(default_factory=list)
    themes: list[LimitUpTheme] = field(default_factory=list)
    date: str = ""
    ttag: float = 0.0
    errcode: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> LimitUpLadderResponse:
        return cls(
            stocks=[LimitUpStock.from_list(item) for item in data.get("StockList", [])],
            themes=[LimitUpTheme.from_list(item) for item in data.get("ZhuShuList", [])],
            date=data.get("Date", data.get("date", "")),
            ttag=data.get("ttag", 0.0),
            errcode=data.get("errcode", ""),
        )


@dataclass
class MarketHighlightItem:
    """盘面亮点接口 - 单条亮点"""

    time_min: int = 0
    tag_id: int = 0
    zs_code: str = ""
    detail: str = ""
    tag_shuxing: int = 0
    tag_name: str = ""
    stock_list: list[list[str]] = field(default_factory=list)
    zs_name: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> MarketHighlightItem:
        return cls(
            time_min=data.get("TimeMin", 0),
            tag_id=data.get("TagID", 0),
            zs_code=data.get("ZSCode", ""),
            detail=data.get("Detail", ""),
            tag_shuxing=data.get("TagShuXing", 0),
            tag_name=data.get("TagName", ""),
            stock_list=data.get("StockList", []),
            zs_name=data.get("ZSName", ""),
        )


@dataclass
class MarketHighlightsResponse:
    """盘面亮点接口 - 完整响应"""

    items: list[MarketHighlightItem] = field(default_factory=list)
    date: str = ""
    server_time: int = 0
    ttag: float = 0.0
    errcode: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> MarketHighlightsResponse:
        return cls(
            items=[MarketHighlightItem.from_dict(item) for item in data.get("List", [])],
            date=data.get("date", ""),
            server_time=data.get("Time", 0),
            ttag=data.get("ttag", 0.0),
            errcode=data.get("errcode", ""),
        )
