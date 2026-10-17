"""A 股交易日历（与 star_stocks.utils.workday_checker 保持一致：exchange_calendars 的 XSHG 日历）。

用途：分钟K线按「交易日」取数时，需要知道目标日之后的交易日数量，才能算出
通达信 bars 接口的 start（从最新往前跳过的根数）。

exchange_calendars 缺失或目标日超出日历范围时，降级为「仅按周末判断」并告警
（与 star_stocks 的降级策略一致），此时节假日会被当作交易日，但分钟线窗口
自适应重试仍能定位到目标日。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

CALENDAR_NAME = "XSHG"


class CalendarError(ValueError):
    """交易日历相关错误（非交易日/超出范围/未来日期）。"""


@lru_cache(maxsize=1)
def _get_calendar():
    """获取上交所日历；不可用时返回 None（降级为周末判断）。"""
    try:
        import exchange_calendars as xcals

        return xcals.get_calendar(CALENDAR_NAME)
    except ImportError:
        logger.warning("exchange_calendars 未安装，交易日判断降级为仅按周末")
        return None
    except Exception as exc:  # pragma: no cover - 依赖库异常
        logger.warning("加载 %s 日历失败（%s），交易日判断降级为仅按周末", CALENDAR_NAME, exc)
        return None


def _as_date(value) -> date:
    """把 date/datetime/str 统一成 date。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return parse_date(str(value))


def parse_date(value: str) -> date:
    """解析日期字符串，容忍 2026-10-13 / 20261013 / 2026/10/13。"""
    text = (value or "").strip().replace("/", "-")
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise CalendarError(f"date 格式需为 YYYY-MM-DD（如 2026-10-13），收到：{value!r}")


def is_trading_day(target) -> bool:
    """判断是否为 A 股交易日。"""
    d = _as_date(target)
    cal = _get_calendar()
    if cal is None:
        return d.weekday() < 5
    try:
        return bool(cal.is_session(d.isoformat()))
    except Exception as exc:  # pragma: no cover - 超出日历范围等
        logger.warning("交易日判断异常（%s），按周末判断：%s", d.isoformat(), exc)
        return d.weekday() < 5


def resolve_session(target, direction: str = "previous") -> date:
    """把任意日期解析为最近的交易日（previous / next）。"""
    d = _as_date(target)
    cal = _get_calendar()
    if cal is None:
        step = -1 if direction == "previous" else 1
        cur = d
        while True:
            cur += timedelta(days=step)
            if is_trading_day(cur):
                return cur
    try:
        session = cal.date_to_session(d.isoformat(), direction=direction)
        return session.date()
    except Exception as exc:
        raise CalendarError(
            f"{d.isoformat()} 无法解析为交易日（超出日历范围：{exc}）"
        ) from exc


def latest_trading_day(today: Optional[date] = None) -> date:
    """最近交易日（含 today，若 today 为交易日）。"""
    anchor = _as_date(today or date.today())
    if is_trading_day(anchor):
        return anchor
    return resolve_session(anchor, direction="previous")


def trading_days_after(target, until: Optional[date] = None) -> int:
    """目标日之后（不含目标日）到 until（含）之间的交易日数量。

    until 默认取最近交易日；target 必须为交易日，否则抛 CalendarError。
    """
    d = _as_date(target)
    end = _as_date(until or latest_trading_day())
    if d > end:
        raise CalendarError(f"{d.isoformat()} 晚于最近交易日 {end.isoformat()}（未来日期）")
    if not is_trading_day(d):
        raise CalendarError(
            f"{d.isoformat()} 非交易日（最近交易日 {resolve_session(d, 'previous').isoformat()}）"
        )
    cal = _get_calendar()
    if cal is None:
        # 降级：按工作日估算（节假日会有偏差，由调用方的窗口重试兜底）
        days = 0
        cur = d
        while cur < end:
            cur += timedelta(days=1)
            if cur.weekday() < 5:
                days += 1
        return days
    try:
        sessions = cal.sessions_in_range(d.isoformat(), end.isoformat())
        return max(0, len(sessions) - 1)
    except Exception as exc:  # pragma: no cover
        raise CalendarError(f"交易日区间计算失败（{d}~{end}）：{exc}") from exc
