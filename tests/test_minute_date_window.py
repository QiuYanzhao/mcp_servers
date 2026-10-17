"""按交易日取分钟线（date 参数）与窗口定位的离线单元测试

不访问行情服务器：用假 client / 假日历验证窗口计算、切片、错误口径与复权乘数。
"""

import pandas as pd
import pytest

from mcp_servers.stock_market import trading_calendar
from mcp_servers.stock_market.data_fetcher import NonRetryableError, StockDataFetcher

DAYS = ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"]


def _minute_times():
    """A股单日 240 根分钟线时间刻度（09:31~11:30、13:01~15:00）"""
    times = []
    times += [f"09:{m:02d}" for m in range(31, 60)]   # 29
    times += [f"10:{m:02d}" for m in range(60)]       # 60
    times += [f"11:{m:02d}" for m in range(0, 31)]    # 31
    times += [f"13:{m:02d}" for m in range(1, 60)]    # 59
    times += [f"14:{m:02d}" for m in range(60)]       # 60
    times += ["15:00"]                                # 1
    return times


TIMES = _minute_times()
assert len(TIMES) == 240


def _make_full_df(days, skip_days=()):
    rows = []
    for d in days:
        if d in skip_days:
            continue
        for t in TIMES:
            rows.append({"datetime": f"{d} {t}:00", "open": 10.0, "high": 10.1,
                         "low": 9.9, "close": 10.0, "volume": 100, "amount": 1000.0})
    return pd.DataFrame(rows)


class FakeClient:
    """模拟通达信 bars 的 start/offset 语义：start=从最新往前跳过根数"""

    def __init__(self, df, calls=None):
        self._df = df
        self.calls = calls if calls is not None else []

    def bars(self, symbol="", frequency=9, start=0, offset=100, **kwargs):
        self.calls.append({"start": start, "offset": offset})
        n = len(self._df)
        end = n - start
        begin = max(0, n - start - offset)
        if end <= 0:
            return pd.DataFrame(columns=self._df.columns)
        return self._df.iloc[begin:end].reset_index(drop=True)


@pytest.fixture()
def fetcher(monkeypatch):
    """构造不依赖服务器的 StockDataFetcher（跳过股票列表加载与连接）"""
    f = StockDataFetcher.__new__(StockDataFetcher)
    f._server = "127.0.0.1:7709"
    f._use_server_manager = False
    f._client = None
    f._current_server = None
    f._stock_name_to_code = {}
    f._adjust_events_cache = {}
    monkeypatch.setattr(
        trading_calendar, "trading_days_after", lambda day, until=None: len(DAYS) - 1 - DAYS.index(day)
    )
    return f


class TestResolveMinuteWindow:
    def test_slices_target_day_exactly(self, fetcher):
        df = _make_full_df(DAYS)
        client = FakeClient(df)

        rows = fetcher._resolve_minute_window(client, "300308", "2026-10-14")

        assert rows is not None
        assert len(rows) == 240
        assert {str(v)[:10] for v in rows["datetime"]} == {"2026-10-14"}
        # k=2 → start = 2*240-240 = 240
        assert client.calls[0] == {"start": 240, "offset": 800}

    def test_latest_day_uses_start_zero(self, fetcher):
        client = FakeClient(_make_full_df(DAYS))
        rows = fetcher._resolve_minute_window(client, "300308", "2026-10-16")

        assert rows is not None and len(rows) == 240
        assert client.calls[0]["start"] == 0

    def test_retries_when_stock_halted_after_target(self, fetcher):
        """个股在目标日之后停牌 → 分钟根数少于交易日数，需前移窗口重试"""
        df = _make_full_df(DAYS, skip_days={"2026-10-15", "2026-10-16"})
        client = FakeClient(df)

        rows = fetcher._resolve_minute_window(client, "300308", "2026-10-14")

        assert rows is not None and len(rows) == 240
        assert {str(v)[:10] for v in rows["datetime"]} == {"2026-10-14"}
        assert len(client.calls) >= 1

    def test_returns_none_when_day_absent(self, fetcher):
        df = _make_full_df(DAYS, skip_days={"2026-10-14"})
        client = FakeClient(df)

        assert fetcher._resolve_minute_window(client, "300308", "2026-10-14") is None


class TestTargetDayValidation:
    def test_default_is_latest_trading_day(self, fetcher, monkeypatch):
        monkeypatch.setattr(
            trading_calendar, "latest_trading_day", lambda today=None: trading_calendar.parse_date("2026-10-16")
        )
        day, is_default = fetcher._normalize_target_day("")
        assert day == "2026-10-16" and is_default is True

    def test_accepts_compact_format(self, fetcher):
        day, is_default = fetcher._normalize_target_day("20261015")
        assert day == "2026-10-15" and is_default is False

    def test_rejects_non_trading_day(self, fetcher, monkeypatch):
        monkeypatch.setattr(trading_calendar, "is_trading_day", lambda d: False)
        monkeypatch.setattr(
            trading_calendar, "resolve_session", lambda d, direction="previous": trading_calendar.parse_date("2026-10-09")
        )
        with pytest.raises(NonRetryableError) as exc:
            fetcher._normalize_target_day("2026-10-11")
        assert "非交易日" in str(exc.value)

    def test_rejects_future_date(self, fetcher):
        with pytest.raises(NonRetryableError) as exc:
            fetcher._normalize_target_day("2099-01-05")
        assert "未来日期" in str(exc.value)

    def test_rejects_bad_format(self, fetcher):
        with pytest.raises(NonRetryableError) as exc:
            fetcher._normalize_target_day("abc")
        assert "格式" in str(exc.value)


class TestQfq:
    def test_factors_apply_before_event_only(self, fetcher, monkeypatch):
        """事件日之前的价格乘以乘数，事件日及之后不变；volume 不调整"""
        df = _make_full_df(["2026-10-09", "2026-10-12"])
        monkeypatch.setattr(fetcher, "_get_adjust_events", lambda symbol: [("2026-10-12", 0.5)])

        out = fetcher._apply_qfq(None, "300308", df)

        before = out[out["datetime"].str.startswith("2026-10-09")]
        after = out[out["datetime"].str.startswith("2026-10-12")]
        assert set(before["close"]) == {5.0}
        assert set(after["close"]) == {10.0}
        assert set(out["volume"]) == {100}  # 量能不参与复权

    def test_no_events_returns_original(self, fetcher, monkeypatch):
        df = _make_full_df(["2026-10-15"])
        monkeypatch.setattr(fetcher, "_get_adjust_events", lambda symbol: [])
        out = fetcher._apply_qfq(None, "600519", df)
        assert out is df


class TestMinutePayloadErrors:
    def test_empty_response_is_retryable(self, fetcher):
        """节点返回空数据 → 视为连接问题（可换节点重试），不能误判为该日无数据"""
        fetcher._get_client = lambda: FakeClient(pd.DataFrame(columns=["datetime"]))
        with pytest.raises(ConnectionError):
            fetcher._fetch_minute_payload("600519", "2026-10-15")

    def test_day_absent_raises_non_retryable(self, fetcher):
        """有数据但目标日缺失（停牌/超范围）→ 不可重试错误"""
        fetcher._get_client = lambda: FakeClient(_make_full_df(DAYS, skip_days={"2026-10-14"}))
        with pytest.raises(NonRetryableError) as exc:
            fetcher._fetch_minute_payload("920002", "2026-10-14")
        assert "无分钟数据" in str(exc.value)

    def test_get_minute_data_returns_error_dict(self, fetcher, monkeypatch):
        def boom(*args, **kwargs):
            raise NonRetryableError("模拟不可用")

        monkeypatch.setattr(fetcher, "_fetch_minute_payload", boom)
        result = fetcher.get_minute_data("600519", date="2026-10-15")
        assert result["error"] == "模拟不可用"
        assert result["data"] == []
