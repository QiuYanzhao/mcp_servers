"""
复刻 get_minute_kline MCP工具逻辑
获取300308的分时行情数据并保存到项目根目录
"""

import json
import logging
import signal
import sys
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
from mootdx.quotes import Quotes

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 涨跌停计算常量
DEFAULT_LIMIT_RATIO = 0.10  # 主板涨跌停比例10%（默认）
LIMIT_PRICE_TOLERANCE = 0.005  # 涨停价比较容差（半分钱）

# 备用服务器列表
BACKUP_SERVERS = [
    "110.41.147.114:7709",
    "47.113.94.204:7709",
    "124.70.176.52:7709",
    "121.36.54.217:7709",
]


class MinuteKlineFetcher:
    """分钟K线数据获取器"""

    def __init__(self, server: str = "202.108.253.139:80"):
        """
        初始化数据获取器

        Args:
            server: 通达信服务器地址
        """
        self._server = server
        self._client: Optional[Quotes] = None
        self._current_server: Optional[str] = None

    def _connect_server(self, server: str) -> bool:
        """
        连接指定服务器

        Args:
            server: 服务器地址 (host:port)

        Returns:
            是否连接成功
        """
        try:
            host, port = server.split(":")
            logger.info(f"尝试连接通达信服务器: {host}:{port}")
            self._client = Quotes.factory(
                market="std",
                server=(host, int(port)),
                timeout=10,
            )
            self._current_server = server
            logger.info(f"成功连接通达信服务器: {host}:{port}")
            return True
        except Exception as e:
            logger.warning(f"连接服务器 {server} 失败: {e}")
            return False

    def _get_client(self) -> Quotes:
        """获取或创建行情客户端，支持自动切换服务器"""
        if self._client is not None:
            return self._client

        # 尝试主服务器
        if self._connect_server(self._server):
            return self._client

        # 尝试备用服务器
        for backup_server in BACKUP_SERVERS:
            if self._connect_server(backup_server):
                return self._client

        raise ConnectionError("无法连接任何通达信服务器")

    def close(self):
        """关闭连接"""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
            self._current_server = None
            logger.info("关闭通达信行情客户端")

    @staticmethod
    def _get_limit_ratio(symbol: str, stock_name: str = "") -> float:
        """
        根据股票代码和名称动态计算涨跌停比例

        规则：
        - ST / *ST 股票 → 5%
        - 科创板（688xxx）→ 20%
        - 创业板（300xxx, 301xxx）→ 20%
        - 北交所（8开头，如83xxxx, 87xxxx）→ 30%
        - 其余主板 → 10%
        """
        if stock_name and ("ST" in stock_name.upper() or "*ST" in stock_name.upper()):
            return 0.05

        code = symbol.strip()
        if code.startswith("688"):
            return 0.20
        if code.startswith(("300", "301")):
            return 0.20
        if code.startswith("8"):
            return 0.30

        return DEFAULT_LIMIT_RATIO

    @staticmethod
    def _calc_limit_up_price(pre_close: float, ratio: float) -> float:
        """计算涨停价（按交易所规则四舍五入到分）"""
        return round(pre_close * (1 + ratio), 2)

    @staticmethod
    def _calc_limit_down_price(pre_close: float, ratio: float) -> float:
        """计算跌停价（按交易所规则四舍五入到分）"""
        return round(pre_close * (1 - ratio), 2)

    @staticmethod
    def _is_at_limit_up(close: float, limit_up: float) -> bool:
        """判断收盘价是否封涨停"""
        return close >= limit_up - LIMIT_PRICE_TOLERANCE

    @staticmethod
    def _is_at_limit_down(close: float, limit_down: float) -> bool:
        """判断收盘价是否封跌停"""
        return close <= limit_down + LIMIT_PRICE_TOLERANCE

    def get_minute_data(self, symbol: str, count: int = 240, adaptive_threshold: float = 1.0, stock_name: str = "") -> Dict:
        """
        获取1分钟K线数据（复刻 get_minute_kline 逻辑）

        Args:
            symbol: 股票代码，如 "300308"
            count: 获取的数据条数，默认240（约1个交易日）
            adaptive_threshold: 自适应提取阈值(如 1.0 表示 1%)，默认 1.0。
                               设置为 0 或 None 可返回完整数据。
            stock_name: 股票名称，用于辅助判断涨跌停（ST股）

        Returns:
            包含1分钟K线数据的字典
        """
        client = self._get_client()
        logger.info(f"获取{symbol}的1分钟K线数据，数量: {count}")

        # 获取1分钟K线数据 (frequency=7 对应1分钟线)
        df = client.bars(symbol=symbol, frequency=7, offset=count)

        if df is None or df.empty:
            logger.warning(f"未获取到{symbol}的1分钟K线数据")
            return {"error": "未获取到1分钟K线数据", "data": []}

        logger.info(f"成功获取{len(df)}条1分钟K线数据")

        # 前复权处理
        df = self._apply_qfq(client, symbol, df)

        # 转换数据格式
        data_list = []
        for _, row in df.iterrows():
            data_list.append({
                "datetime": str(row.get("datetime", "")),
                "open": round(float(row.get("open", 0)), 2),
                "high": round(float(row.get("high", 0)), 2),
                "low": round(float(row.get("low", 0)), 2),
                "close": round(float(row.get("close", 0)), 2),
                "volume": int(row.get("volume", row.get("vol", 0))),
                "amount": round(float(row.get("amount", 0)), 2),
            })

        # 如果设置了自适应阈值，则提取关键特征点
        if adaptive_threshold is not None and adaptive_threshold > 0:
            logger.info(f"对{symbol}应用自适应提取，阈值: {adaptive_threshold}%")

            # 获取昨收以便判断涨跌停
            pre_close = 0.0
            try:
                daily_data = self._get_daily_kline_for_pre_close(symbol)
                if daily_data and len(daily_data) >= 2:
                    pre_close = daily_data[-2]["close"]
                    logger.info(f"获取昨收价成功: {pre_close}")
            except Exception as e:
                logger.warning(f"获取昨收数据失败，涨跌停判断可能不准确: {e}")

            data_list = self.extract_adaptive_kline(data_list, adaptive_threshold, pre_close, stock_name, symbol)
            return {
                "symbol": symbol,
                "frequency": "adaptive_1min",
                "count": len(data_list),
                "pre_close": pre_close,
                "limit_up_price": self._calc_limit_up_price(pre_close, self._get_limit_ratio(symbol, stock_name)) if pre_close > 0 else None,
                "limit_down_price": self._calc_limit_down_price(pre_close, self._get_limit_ratio(symbol, stock_name)) if pre_close > 0 else None,
                "data": data_list,
            }

        return {
            "symbol": symbol,
            "frequency": "1min",
            "count": len(data_list),
            "data": data_list,
        }

    def _get_daily_kline_for_pre_close(self, symbol: str) -> List[Dict]:
        """获取日K线数据用于计算昨收价"""
        client = self._get_client()
        df = client.bars(symbol=symbol, frequency=9, offset=2)

        if df is None or df.empty:
            return []

        # 前复权处理
        df = self._apply_qfq(client, symbol, df)

        data_list = []
        for _, row in df.iterrows():
            data_list.append({
                "datetime": str(row.get("datetime", "")),
                "close": round(float(row.get("close", 0)), 2),
            })
        return data_list

    def _apply_qfq(self, client: Quotes, symbol: str, df: pd.DataFrame) -> pd.DataFrame:
        """
        应用前复权处理
        """
        try:
            # 获取除权除息数据
            xdxr = client.xdxr(symbol=symbol)

            if xdxr is None or xdxr.empty:
                logger.info(f"{symbol}无除权除息数据，返回原始数据")
                return df

            # 应用前复权
            from mootdx.utils.adjust import to_qfq
            adjusted_df = to_qfq(df, xdxr)
            logger.info(f"{symbol}已完成前复权处理")
            return adjusted_df

        except Exception as e:
            logger.warning(f"{symbol}前复权处理失败，返回原始数据: {e}")
            return df

    def extract_adaptive_kline(self, data_list: List[Dict], threshold_pct: float = 1.0, pre_close: float = 0.0, stock_name: str = "", symbol: str = "") -> List[Dict]:
        """
        提取自适应 K线数据 (1% 波动 + 极值提取)

        Args:
            data_list: 1分钟 K线数据列表
            threshold_pct: 触发阈值百分比，默认 1.0%
            pre_close: 前收盘价，用于计算涨跌停
            stock_name: 股票名称，用于判断ST股
            symbol: 股票代码，用于计算涨跌停比例（如 300xxx 为创业板 20%）

        Returns:
            提取后的关键特征点列表
        """
        if not data_list:
            return []

        # 计算涨跌停价格
        limit_up_price = 0.0
        limit_down_price = 0.0
        if pre_close > 0:
            # 使用传入的 symbol 计算涨跌停比例，而非从 data_list 中获取
            ratio = self._get_limit_ratio(symbol, stock_name)
            limit_up_price = self._calc_limit_up_price(pre_close, ratio)
            limit_down_price = self._calc_limit_down_price(pre_close, ratio)
            logger.info(f"涨跌停计算: symbol={symbol}, ratio={ratio}, 涨停={limit_up_price}, 跌停={limit_down_price}")

        result = []

        # 1. 记录开盘价作为初始基准
        start_item = data_list[0]
        current_base_price = start_item['open']
        result.append({**start_item, "type": "open", "base_price": current_base_price})

        # 初始化极值跟踪
        max_price_so_far = start_item['high']
        min_price_so_far = start_item['low']

        # 2. 遍历后续数据
        for i in range(1, len(data_list)):
            item = data_list[i]
            price = item['close']

            # 检查是否为新的极值
            is_new_high = item['high'] > max_price_so_far
            is_new_low = item['low'] < min_price_so_far

            # 更新极值记录
            if is_new_high:
                max_price_so_far = item['high']
            if is_new_low:
                min_price_so_far = item['low']

            # 计算相对于基准的涨跌幅
            change_pct = (price - current_base_price) / current_base_price * 100 if current_base_price != 0 else 0

            should_record = False
            record_type = ""

            # 规则 A: 价格波动超过阈值
            if abs(change_pct) >= threshold_pct:
                should_record = True
                record_type = "trigger_pct"

            # 规则 B: 创截止目前的新高
            elif is_new_high:
                should_record = True
                record_type = "new_high"

            # 规则 C: 创截止目前的新低
            elif is_new_low:
                should_record = True
                record_type = "new_low"

            if should_record:
                new_record = {
                    **item,
                    "type": record_type,
                    "change_pct_from_base": round(change_pct, 2),
                    "base_price": current_base_price
                }

                # 如果是新高或新低，判断是否涨停跌停
                if pre_close > 0:
                    if record_type == "new_high":
                        new_record["is_limit_up"] = self._is_at_limit_up(item['high'], limit_up_price)
                    elif record_type == "new_low":
                        new_record["is_limit_down"] = self._is_at_limit_down(item['low'], limit_down_price)

                result.append(new_record)
                # 更新基准价格
                current_base_price = price

        # 3. 确保最后一条（收盘价）被记录
        last_item = data_list[-1]
        if result[-1]['datetime'] != last_item['datetime']:
            change_pct = (last_item['close'] - current_base_price) / current_base_price * 100 if current_base_price != 0 else 0
            result.append({
                **last_item,
                "type": "close",
                "change_pct_from_base": round(change_pct, 2),
                "base_price": current_base_price
            })

        return result


def timeout_handler(signum, frame):
    """超时处理函数"""
    logger.error("操作超时")
    sys.exit(1)


def main():
    """主函数"""
    # 设置超时处理 (60秒)
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(60)

    fetcher = MinuteKlineFetcher()

    try:
        # 获取300308的分时行情数据
        symbol = "300308"
        stock_name = "中际旭创"
        count = 240
        adaptive_threshold = 1.0

        logger.info(f"开始获取 {symbol}({stock_name}) 的分时行情数据")

        result = fetcher.get_minute_data(
            symbol=symbol,
            count=count,
            adaptive_threshold=adaptive_threshold,
            stock_name=stock_name
        )

        # 保存结果到项目根目录
        output_file = f"/Users/qyz/TraeProjects/mcp_servers/{symbol}_minute_kline.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        logger.info(f"数据已保存到: {output_file}")
        logger.info(f"数据条数: {result.get('count', 0)}")

        # 打印部分数据预览
        if result.get("data"):
            logger.info("数据预览（前5条）:")
            for i, item in enumerate(result["data"][:5]):
                logger.info(f"  [{i}] {item}")

    except Exception as e:
        logger.error(f"获取数据失败: {e}")
        raise
    finally:
        # 取消超时
        signal.alarm(0)
        fetcher.close()


if __name__ == "__main__":
    main()
