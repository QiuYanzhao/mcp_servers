"""改动后实测验证：000592 / 600715（附 601398 复权口径对照）

验证思路：
1) 用 StockDataFetcher 走真实代码路径取数
2) 用 eltdx 原始接口独立取同一批数据做交叉核对（不复用适配层）
3) 逐项打印 PASS/FAIL，最后输出汇总
"""

import json
import sys

from eltdx import TdxClient

from mcp_servers.stock_market.data_fetcher import StockDataFetcher

SERVERS = [
    "110.41.147.114:7709",
    "47.113.94.204:7709",
    "124.70.176.52:7709",
    "121.36.54.217:7709",
    "119.147.212.81:7709",
]

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def raw_client():
    for host in SERVERS:
        try:
            c = TdxClient(host=host, probe_hosts=False, timeout=8)
            c.connect()
            print(f"[raw] 连接 {host}")
            return c
        except Exception as e:
            print(f"[raw] {host} 失败: {type(e).__name__}")
    raise SystemExit("无可用的通达信节点")


def raw_daily(c, code, count=130):
    return c.bars.get(code=code, period="day", count=count, adjust="qfq").bars


def raw_minutes(c, code, start=0, count=240):
    return c.bars.get(code=code, period="1min", start=start, count=count, adjust="qfq").bars


def raw_minutes_on(c, code, day, max_pages=40):
    """按 240 根为一页向前翻，取指定交易日当天的分钟线（RAW 口径）"""
    for page in range(max_pages):
        bars = raw_minutes(c, code, page * 240, 240)
        if not bars:
            return None
        days = {b.time.strftime("%Y-%m-%d") for b in bars}
        if day in days:
            return [b for b in bars if b.time.strftime("%Y-%m-%d") == day]
        if max(b.time.strftime("%Y-%m-%d") for b in bars) < day:
            return None  # 已翻到比目标日更早
    return None


def main():
    c = raw_client()
    f = StockDataFetcher()

    for code, name in [("000592", "平潭发展"), ("600715", "文投控股")]:
        print(f"\n================ {code} {name} ================")

        # ---------- 日K：昨收(服务器 last_close) / 股数 ----------
        daily = f.get_daily_kline(code, count=120)
        if "error" in daily:
            check(f"{code} 日K 取数", False, daily["error"])
            continue
        rows = daily["data"]
        last = rows[-1]
        prev = rows[-2]
        raw = raw_daily(c, code, 130)
        raw_last = raw[-1]

        check(f"{code} 日K 最新交易日", last["datetime"][:10] == raw_last.time.strftime("%Y-%m-%d"),
              f"SUT={last['datetime'][:10]} RAW={raw_last.time:%Y-%m-%d}")
        check(f"{code} 日K 收盘价一致", abs(last["close"] - float(raw_last.close)) < 0.005,
              f"SUT={last['close']} RAW={float(raw_last.close)}")
        # ① 昨收：pre_close 应为前一日收盘，且等于服务器 last_close
        check(f"{code} ①昨收=前一日收盘", abs(last["pre_close"] - prev["close"]) < 0.005,
              f"pre_close={last['pre_close']} 前一日close={prev['close']}")
        check(f"{code} ①昨收=服务器last_close",
              abs(last["pre_close"] - float(raw_last.last_close_price_milli) / 1000.0) < 0.005,
              f"SUT={last['pre_close']} RAW={float(raw_last.last_close_price_milli)/1000.0}")
        # ⑤ 股数：shares 应等于 volume_lots*100，volume(手) 等于 volume_lots
        check(f"{code} ⑤shares=vol_lots*100",
              abs(last["shares"] - float(raw_last.volume_lots) * 100) <= 100,
              f"SUT={last['shares']} RAW={float(raw_last.volume_lots)*100:.0f}")
        check(f"{code} volume单位=手", last["volume"] == int(round(float(raw_last.volume_lots))),
              f"SUT={last['volume']} RAW={float(raw_last.volume_lots):.2f}")
        check(f"{code} 涨跌停保持自算", last["limit_up"] is not None and last["limit_down"] is not None,
              f"limit_up={last['limit_up']} limit_down={last['limit_down']}")
        print("  最新日K:", json.dumps({k: last[k] for k in
              ("datetime", "close", "volume", "shares", "amount", "pre_close", "limit_up")},
              ensure_ascii=False))

        # ---------- 分钟K：服务器前复权 + 与日K口径一致 ----------
        day = last["datetime"][:10]
        minute = f.get_minute_data(code, date=day, adaptive_threshold=0)
        mrows = minute.get("data", [])
        check(f"{code} 分钟K 条数=240", len(mrows) == 240, f"count={len(mrows)}")
        if mrows:
            mlast = mrows[-1]
            raw_m = raw_minutes(c, code, 0, 240)
            check(f"{code} 分钟K 收盘=日K收盘(同口径)",
                  abs(mlast["close"] - last["close"]) < 0.02,
                  f"分钟末收盘={mlast['close']} 日K收盘={last['close']}")
            check(f"{code} 分钟K 与RAW逐点一致",
                  abs(mlast["close"] - float(raw_m[-1].close)) < 0.005,
                  f"SUT={mlast['close']} RAW={float(raw_m[-1].close)}")
            check(f"{code} 分钟K 昨收=日K昨收", abs(minute["prev_close"] - last["pre_close"]) < 0.005,
                  f"分钟prev_close={minute['prev_close']} 日Kpre_close={last['pre_close']}")
            print("  分钟末根:", json.dumps(mrows[-1], ensure_ascii=False))

        # ---------- 分钟K 历史交易日（验证 start 透传） ----------
        prev_day = prev["datetime"][:10]
        m_prev = f.get_minute_data(code, date=prev_day, adaptive_threshold=0)
        check(f"{code} 历史分钟线 {prev_day} 条数=240",
              len(m_prev.get("data", [])) == 240, f"count={len(m_prev.get('data', []))}")
        if m_prev.get("data"):
            raw_pm = raw_minutes(c, code, 240, 240)
            check(f"{code} 历史分钟线与RAW一致",
                  abs(m_prev["data"][-1]["close"] - float(raw_pm[-1].close)) < 0.005
                  and m_prev["date"] == prev_day,
                  f"SUT={m_prev['data'][-1]['close']} RAW={float(raw_pm[-1].close)} 日期={m_prev['date']}")

        # ---------- 朝③④ 分时：均价线 + 每分钟成交量 ----------
        intraday = f.get_intraday_chart(code, day)
        irows = intraday.get("data", [])
        check(f"{code} 分时 条数=240", len(irows) == 240, f"count={len(irows)}")
        if irows:
            n_avg = sum(1 for r in irows if r["avg_price"] is not None)
            check(f"{code} ③均价线逐点直给", n_avg == len(irows), f"有均值点数={n_avg}/{len(irows)}")
            vol_sum = sum(r["volume"] for r in irows)
            check(f"{code} ④分时量合计=日K成交量(手)",
                  abs(vol_sum - last["volume"]) <= 1, f"分时合计={vol_sum} 日K={last['volume']}")
            check(f"{code} 分时昨收与日K昨收一致",
                  abs(intraday["prev_close"] - last["pre_close"]) < 0.005,
                  f"分时prev_close={intraday['prev_close']} 日Kpre_close={last['pre_close']}")
            print("  分时首点:", json.dumps(irows[0], ensure_ascii=False),
                  "末点:", json.dumps(irows[-1], ensure_ascii=False))

        # ---------- 实时行情 ----------
        quote = f.get_realtime_quote(code)
        check(f"{code} 实时行情可取", "price" in quote and quote["price"] > 0,
              f"price={quote.get('price')} last_close={quote.get('last_close')}")

    # ---------- 复权口径专项对照：601398 工行 2026-10-21 除权 ----------
    print("\n================ 复权口径对照 601398 ================")
    r_daily = raw_daily(c, "601398", 60)
    by_day = {b.time.strftime("%Y-%m-%d"): b for b in r_daily}
    th, ty = by_day.get("2026-10-20"), by_day.get("2026-10-19")
    if th and ty:
        m_1020 = f.get_minute_data("601398", date="2026-10-20", adaptive_threshold=0)
        m_day = m_1020.get("data", [])
        if m_day:
            lastb = m_day[-1]
            raw_day = raw_minutes_on(c, "601398", "2026-10-20")
            daily_pct = (float(th.close) - float(ty.close)) / float(ty.close)
            minute_ratio = lastb["close"] / m_1020["prev_close"] if m_1020["prev_close"] else 0
            check("601398 分钟线已前复权（与日K同口径）",
                  abs(minute_ratio - (1 + daily_pct)) < 0.005,
                  f"分钟末收/昨收={minute_ratio:.4f} 日Kqfq涨跌={1+daily_pct:.4f}")
            if raw_day:
                check("601398 分钟线末根=RAW复权末根",
                      abs(lastb["close"] - float(raw_day[-1].close)) < 0.005,
                      f"SUT={lastb['close']} RAW={float(raw_day[-1].close)}")
    else:
        check("601398 除权日K可得", False, "未取到 2026-10-19/20 日K")

    f.close()
    c.close()

    fails = [r for r in RESULTS if not r[1]]
    print(f"\n汇总: {len(RESULTS) - len(fails)}/{len(RESULTS)} 项通过")
    if fails:
        for name, _, detail in fails:
            print("  FAIL:", name, detail)
        sys.exit(1)


if __name__ == "__main__":
    main()
