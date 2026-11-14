"""EltdxQuotes 适配层离线单测：字段映射、start 透传、服务器端前复权参数"""

from datetime import datetime
from types import SimpleNamespace

import pandas as pd

from mcp_servers.stock_market.data_fetcher import EltdxQuotes


class FakeBar:
    def __init__(self, day, close, last_close_milli, lots, shares, amount=0.0):
        self.time = datetime.strptime(day, "%Y-%m-%d %H:%M")
        self.open = close
        self.high = close
        self.low = close
        self.close = close
        self.last_close_price_milli = last_close_milli
        self.volume_lots = lots
        self.volume_wire_value = shares
        self.amount = amount


class FakeBarsApi:
    def __init__(self, bars):
        self._bars = bars
        self.calls = []

    def get(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(bars=tuple(self._bars))


def _quotes(bars):
    q = EltdxQuotes.__new__(EltdxQuotes)
    q._client = SimpleNamespace(bars=FakeBarsApi(bars))
    return q


def test_bars_maps_server_fields_and_passes_start():
    """昨收/股数字段来自服务器；start 必须透传（按交易日取数依赖它）"""
    bars = [
        FakeBar("2026-10-27 15:00", 10.10, None, 100.0, 10000.0),
        FakeBar("2026-10-28 15:00", 10.20, 10100, 200.0, 20000.0),
    ]
    q = _quotes(bars)

    df = q.bars("600519", frequency=9, offset=2, start=240)

    call = q._client.bars.calls[0]
    assert call["start"] == 240
    assert call["count"] == 2
    assert call["period"] == "day"
    assert call["adjust"] == "qfq"  # 服务器端前复权
    # last_close 由 milli 转元；窗口首根缺失（DataFrame 中表现为 NaN）
    assert pd.isna(df["last_close"].tolist()[0])
    assert df["last_close"].tolist()[1] == 10.1
    assert df["shares"].tolist() == [10000.0, 20000.0]
    assert df["vol"].tolist() == [100.0, 200.0]


def test_bars_minute_also_requests_qfq():
    """分钟线同样请求服务器前复权，避免与日K口径不一致"""
    q = _quotes([FakeBar("2026-10-28 09:31", 10.0, None, 5.0, 500.0)])

    q.bars("000592", frequency=7, offset=1, start=0)

    call = q._client.bars.calls[0]
    assert call["period"] == "1min"
    assert call["adjust"] == "qfq"
