"""
A股行情数据获取模块

使用mootdx获取A股行情数据，支持：
- 1分钟K线数据（单日）
- 日K数据（含均线、涨跌停、流通市值）
- 前复权处理
"""

import logging
from typing import Dict, Optional

import pandas as pd
from mootdx.quotes import Quotes

# 配置日志
logger = logging.getLogger(__name__)

# 涨跌停计算常量
LIMIT_UP_RATIO = 0.10  # 主板涨跌停比例10%

# 默认服务器（通达信服务器）
DEFAULT_SERVER = "119.147.212.81:7709"


class StockDataFetcher:
    """
    A股行情数据获取类

    使用mootdx获取A股行情数据，提供前复权处理和指标计算功能。
    """

    def __init__(self, server: str = DEFAULT_SERVER):
        """
        初始化数据获取器

        Args:
            server: 通达信服务器地址，格式 "ip:port"
        """
        self._server = server
        self._client: Optional[Quotes] = None

    # 通达信行情服务器列表（备用）
    _TDX_SERVERS = [
        ("110.41.147.114", 7709),
        ("47.113.94.204", 7709),
        ("124.70.176.52", 7709),
        ("121.36.54.217", 7709),
    ]

    def _get_client(self) -> Quotes:
        """
        获取或创建行情客户端

        Returns:
            Quotes实例
        """
        if self._client is None:
            last_error = None
            for host, port in self._TDX_SERVERS:
                try:
                    logger.info(f"尝试连接通达信服务器: {host}:{port}")
                    self._client = Quotes.factory(
                        market="std",
                        server=(host, port),
                        timeout=15,
                    )
                    logger.info(f"成功连接通达信服务器: {host}:{port}")
                    return self._client
                except Exception as e:
                    last_error = e
                    logger.warning(f"连接 {host}:{port} 失败: {e}")
            raise ConnectionError(
                f"无法连接任何通达信服务器，最后错误: {last_error}"
            )
        return self._client

    def close(self):
        """关闭连接"""
        if self._client is not None:
            self._client.close()
            self._client = None
            logger.info("关闭mootdx行情客户端")

    def get_minute_data(self, symbol: str, count: int = 240) -> Dict:
        """
        获取1分钟K线数据

        Args:
            symbol: 股票代码，如 "600519"
            count: 获取的数据条数，默认240（约1个交易日）

        Returns:
            包含1分钟K线数据的字典
        """
        try:
            client = self._get_client()
            logger.info(f"获取{symbol}的1分钟K线数据，数量: {count}")

            # 获取1分钟K线数据 (frequency=7 对应1分钟线)
            df = client.bars(symbol=symbol, frequency=7, offset=count)

            if df is None or df.empty:
                logger.warning(f"未获取到{symbol}的1分钟K线数据")
                return {"error": "未获取到数据", "data": []}

            # 前复权处理
            df = self._apply_qfq(client, symbol, df)

            # 转换数据格式
            data_list = []
            for _, row in df.iterrows():
                data_list.append(
                    {
                        "datetime": str(row.get("datetime", "")),
                        "open": round(float(row.get("open", 0)), 2),
                        "high": round(float(row.get("high", 0)), 2),
                        "low": round(float(row.get("low", 0)), 2),
                        "close": round(float(row.get("close", 0)), 2),
                        "volume": int(row.get("volume", row.get("vol", 0))),
                        "amount": round(float(row.get("amount", 0)), 2),
                    }
                )

            return {
                "symbol": symbol,
                "frequency": "1min",
                "count": len(data_list),
                "data": data_list,
            }

        except Exception as e:
            logger.error(f"获取{symbol}的1分钟K线数据失败: {e}")
            return {"error": str(e), "data": []}

    def get_daily_kline(
        self,
        symbol: str,
        count: int = 120,
        include_ma: bool = True,
        include_limit: bool = True,
    ) -> Dict:
        """
        获取日K线数据

        Args:
            symbol: 股票代码，如 "600519"
            count: 获取的数据条数，默认120
            include_ma: 是否计算均线（5、10、20日）
            include_limit: 是否计算涨跌停价格

        Returns:
            包含日K线数据的字典
        """
        try:
            client = self._get_client()
            logger.info(f"获取{symbol}的日K线数据，数量: {count}")

            # 获取日K线数据 (frequency=9 对应日线)
            df = client.bars(symbol=symbol, frequency=9, offset=count)

            if df is None or df.empty:
                logger.warning(f"未获取到{symbol}的日K线数据")
                return {"error": "未获取到数据", "data": []}

            # 前复权处理
            df = self._apply_qfq(client, symbol, df)

            # 确保列名一致（mootdx返回的列名可能是close或vol）
            close_col = "close" if "close" in df.columns else "close"
            vol_col = "volume" if "volume" in df.columns else "vol"

            # 计算均线
            if include_ma:
                df["ma5"] = df[close_col].rolling(window=5).mean()
                df["ma10"] = df[close_col].rolling(window=10).mean()
                df["ma20"] = df[close_col].rolling(window=20).mean()

            # 计算昨日收盘价
            df["pre_close"] = df[close_col].shift(1)

            # 计算涨跌停价格
            if include_limit:
                df["limit_up"] = df["pre_close"] * (1 + LIMIT_UP_RATIO)
                df["limit_down"] = df["pre_close"] * (1 - LIMIT_UP_RATIO)

            # 转换数据格式
            data_list = []
            for _, row in df.iterrows():
                item = {
                    "datetime": str(row.get("datetime", "")),
                    "open": round(float(row.get("open", 0)), 2),
                    "high": round(float(row.get("high", 0)), 2),
                    "low": round(float(row.get("low", 0)), 2),
                    "close": round(float(row.get(close_col, 0)), 2),
                    "volume": int(row.get(vol_col, 0)),
                    "amount": round(float(row.get("amount", 0)), 2),
                }

                # 添加均线数据
                if include_ma:
                    item["ma5"] = (
                        round(float(row["ma5"]), 2)
                        if pd.notna(row.get("ma5"))
                        else None
                    )
                    item["ma10"] = (
                        round(float(row["ma10"]), 2)
                        if pd.notna(row.get("ma10"))
                        else None
                    )
                    item["ma20"] = (
                        round(float(row["ma20"]), 2)
                        if pd.notna(row.get("ma20"))
                        else None
                    )

                # 添加昨日收盘价
                item["pre_close"] = (
                    round(float(row["pre_close"]), 2)
                    if pd.notna(row.get("pre_close"))
                    else None
                )

                # 添加涨跌停价格
                if include_limit:
                    item["limit_up"] = (
                        round(float(row["limit_up"]), 2)
                        if pd.notna(row.get("limit_up"))
                        else None
                    )
                    item["limit_down"] = (
                        round(float(row["limit_down"]), 2)
                        if pd.notna(row.get("limit_down"))
                        else None
                    )

                data_list.append(item)

            return {
                "symbol": symbol,
                "frequency": "daily",
                "count": len(data_list),
                "adjust": "qfq",  # 前复权
                "indicators": {
                    "ma": ["ma5", "ma10", "ma20"] if include_ma else [],
                    "pre_close": True,
                    "limit": ["limit_up", "limit_down"] if include_limit else [],
                },
                "data": data_list,
            }

        except Exception as e:
            logger.error(f"获取{symbol}的日K线数据失败: {e}")
            return {"error": str(e), "data": []}

    def _apply_qfq(
        self, client: Quotes, symbol: str, df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        应用前复权处理

        Args:
            client: Quotes实例
            symbol: 股票代码
            df: 原始K线数据

        Returns:
            前复权后的DataFrame
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

    def get_realtime_quote(self, symbol: str) -> Dict:
        """
        获取实时行情数据

        Args:
            symbol: 股票代码

        Returns:
            实时行情数据字典
        """
        try:
            client = self._get_client()
            logger.info(f"获取{symbol}的实时行情")

            df = client.quotes(symbol=symbol)

            if df is None or df.empty:
                return {"error": "未获取到数据"}

            row = df.iloc[0]

            # mootdx返回的列名: price(当前价), last_close(昨收), open, high, low, vol, amount
            last_close = round(float(row.get("last_close", 0)), 2)
            price = round(float(row.get("price", 0)), 2)
            return {
                "symbol": symbol,
                "code": str(row.get("code", "")),
                "price": price,
                "last_close": last_close,
                "change_pct": round((price - last_close) / last_close * 100, 2) if last_close > 0 else 0,
                "open": round(float(row.get("open", 0)), 2),
                "high": round(float(row.get("high", 0)), 2),
                "low": round(float(row.get("low", 0)), 2),
                "volume": int(row.get("vol", row.get("volume", 0))),
                "amount": round(float(row.get("amount", 0)), 2),
            }

        except Exception as e:
            logger.error(f"获取{symbol}的实时行情失败: {e}")
            return {"error": str(e)}
