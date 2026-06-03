"""
A股行情数据获取模块

使用mootdx获取A股行情数据，支持：
- 1分钟K线数据（单日）
- 日K数据（含均线、涨跌停、流通市值）
- 前复权处理
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
from mootdx.quotes import Quotes

# 配置日志
logger = logging.getLogger(__name__)

# 涨跌停计算常量
LIMIT_UP_RATIO = 0.10  # 主板涨跌停比例10%
LIMIT_UP_RATIO_ST = 0.05  # ST股涨跌停比例5%
LIMIT_UP_RATIO_KC = 0.20  # 科创板/创业板涨跌停比例20%


class StockDataFetcher:
    """
    A股行情数据获取类

    使用mootdx获取A股行情数据，提供前复权处理和指标计算功能。
    """

    def __init__(self):
        """初始化数据获取器"""
        self._client: Optional[Quotes] = None

    def _get_client(self) -> Quotes:
        """
        获取或创建行情客户端

        Returns:
            Quotes实例
        """
        if self._client is None:
            logger.info("创建mootdx行情客户端")
            self._client = Quotes.factory(market="std", bestip=True, heartbeat=True)
        return self._client

    def close(self):
        """关闭连接"""
        if self._client is not None:
            self._client.close()
            self._client = None
            logger.info("关闭mootdx行情客户端")

    def get_minute_data(
        self, symbol: str, count: int = 240
    ) -> Dict:
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
                        "open": float(row.get("open", 0)),
                        "high": float(row.get("high", 0)),
                        "low": float(row.get("low", 0)),
                        "close": float(row.get("close", 0)),
                        "volume": int(row.get("volume", 0)),
                        "amount": float(row.get("amount", 0)),
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

            # 计算均线
            if include_ma:
                df["ma5"] = df["close"].rolling(window=5).mean()
                df["ma10"] = df["close"].rolling(window=10).mean()
                df["ma20"] = df["close"].rolling(window=20).mean()

            # 计算昨日收盘价
            df["pre_close"] = df["close"].shift(1)

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
                    "close": round(float(row.get("close", 0)), 2),
                    "volume": int(row.get("volume", 0)),
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
            return {
                "symbol": symbol,
                "name": str(row.get("code", "")),
                "open": float(row.get("open", 0)),
                "high": float(row.get("high", 0)),
                "low": float(row.get("low", 0)),
                "close": float(row.get("close", 0)),
                "volume": int(row.get("volume", 0)),
                "amount": float(row.get("amount", 0)),
            }

        except Exception as e:
            logger.error(f"获取{symbol}的实时行情失败: {e}")
            return {"error": str(e)}
