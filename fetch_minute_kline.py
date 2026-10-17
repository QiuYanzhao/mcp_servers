"""get_minute_kline 的命令行调试入口（直接复用包内实现，不再重复复刻逻辑）

与 src/mcp_servers/stock_market/data_fetcher.py 的当前实现保持一致：
- 按「交易日」取数：date 参数（YYYY-MM-DD），留空 = 最近交易日
- 前复权基准 = 最新交易日（xdxr + 原始日K 本地计算）
- 抽点：adaptive_threshold 非 None 即抽点，传 0 保留全部逐分钟点
- 输出字段：time/open/high/low/close/volume/change_pct（+ type/is_limit_up/is_limit_down）

用法（必须用项目 uv 环境，全局 python3 缺依赖）：
    uv run python fetch_minute_kline.py                                  # 300308 中际旭创，最近交易日
    uv run python fetch_minute_kline.py 600519 贵州茅台 2026-10-15
    uv run python fetch_minute_kline.py 300308 中际旭创 2026-10-15 0     # 阈值 0 = 全部逐分钟点
    uv run python fetch_minute_kline.py 300308 中际旭创 2026-10-15 0 --save
    uv run python fetch_minute_kline.py 300308 中际旭创 --node 117.34.114.16:7709
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# 未安装本包时（仅 clone 仓库直接跑），把 src 加进搜索路径
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from mcp_servers.stock_market.data_fetcher import (  # noqa: E402
    DEFAULT_SERVER,
    StockDataFetcher,
    NonRetryableError,
)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="get_minute_kline 命令行调试")
    parser.add_argument("stock_code", nargs="?", default="300308", help="股票代码，默认 300308")
    parser.add_argument("stock_name", nargs="?", default="", help="股票名称（可选）")
    parser.add_argument("date", nargs="?", default="", help="交易日 YYYY-MM-DD，留空=最近交易日")
    parser.add_argument(
        "adaptive_threshold",
        nargs="?",
        type=float,
        default=1.0,
        help="抽点阈值（%%），默认 1.0；传 0 保留全部点",
    )
    parser.add_argument("--node", default="", help="固定通达信节点 host:port（默认用服务器管理器）")
    parser.add_argument("--save", action="store_true", help="把完整 JSON 存到当前目录")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    fetcher = StockDataFetcher(
        server=args.node or DEFAULT_SERVER,
        use_server_manager=not bool(args.node),
    )

    try:
        result = fetcher.get_minute_data(
            args.stock_code, args.date, args.adaptive_threshold, args.stock_name
        )
    except NonRetryableError as e:  # 参数/数据范围类（非交易日、未来日期、该日无数据）
        result = {"error": str(e), "data": []}
    finally:
        fetcher.close()

    output_json = json.dumps(result, ensure_ascii=False)

    print("=== get_minute_kline 工具返回值（compact JSON）===")
    print(output_json if len(output_json) <= 2000 else output_json[:2000] + "...")

    print("\n=== 统计 ===")
    if result.get("error"):
        print(f"error={result['error']}")
    else:
        data = result.get("data") or []
        print(
            f"symbol={result.get('symbol')}, date={result.get('date')}, "
            f"frequency={result.get('frequency')}, count={result.get('count')}"
        )
        if data:
            print(f"首点 {data[0]['time']} open={data[0]['open']} | "
                  f"末点 {data[-1]['time']} close={data[-1]['close']} | "
                  f"末点 change_pct={data[-1]['change_pct']}")
    print(f"完整 JSON 字符数: {len(output_json)}")

    if args.save and not result.get("error"):
        out = Path.cwd() / f"{result.get('symbol')}_minute_kline_{result.get('date')}.json"
        out.write_text(output_json, encoding="utf-8")
        print(f"已保存: {out}")

    return 1 if result.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
