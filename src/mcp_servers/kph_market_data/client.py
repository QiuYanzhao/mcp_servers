"""开盘红平台 API 客户端

统一封装开盘红平台的 HTTP 请求逻辑，对外提供各业务接口方法。
后续新增接口只需在此文件中追加新方法即可。
"""

from typing import Any

import requests

from .config import KPH_API, KPH_HIS_API
from .models import (
    LimitUpLadderResponse,
    LiveContentResponse,
    MarketHighlightsResponse,
)
from .logger import setup_logger

logger = setup_logger("kph_api")


class KPHClient:
    """开盘红平台 API 客户端

    支持实时接口和历史接口，历史接口使用独立域名和额外的 Date 参数。
    """

    def __init__(self) -> None:
        # 实时接口配置
        self._url: str = KPH_API["url"]
        self._base_params: dict[str, str] = dict(KPH_API["params"])
        self._headers: dict[str, str] = dict(KPH_API["headers"])
        self._timeout: int = KPH_API["timeout"]
        # 历史接口配置
        self._his_url: str = KPH_HIS_API["url"]
        self._his_base_params: dict[str, str] = dict(KPH_HIS_API["params"])
        self._his_headers: dict[str, str] = dict(KPH_HIS_API["headers"])

    def _post(self, params: dict[str, str]) -> dict[str, Any] | None:
        """
        发送 POST 请求并返回解析后的 JSON 数据

        Args:
            params: 完整的请求体参数

        Returns:
            成功时返回解析后的 JSON 字典，失败时返回 None
        """
        try:
            response = requests.post(
                self._url,
                headers=self._headers,
                data=params,
                timeout=self._timeout,
            )
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "")
            if "json" not in content_type:
                logger.warning("API 返回非 JSON 响应: Content-Type=%s", content_type)
                return None

            data = response.json()

            if data.get("errcode") != "0":
                logger.warning("API 返回错误码: errcode=%s", data.get("errcode"))
                return None

            return data

        except requests.exceptions.RequestException as e:
            logger.error("API 请求失败: %s", str(e))
            return None
        except ValueError as e:
            logger.error("JSON 解析失败: %s", str(e))
            return None

    def _build_params(self, overrides: dict[str, str] | None = None) -> dict[str, str]:
        """
        合并基础参数与接口特定参数

        Args:
            overrides: 接口特定的参数，会覆盖基础参数中的同名项

        Returns:
            合并后的完整请求参数字典
        """
        params = dict(self._base_params)
        if overrides:
            params.update(overrides)
        return params

    def _his_post(self, params: dict[str, str]) -> dict[str, Any] | None:
        """
        发送历史接口 POST 请求并返回解析后的 JSON 数据

        Args:
            params: 完整的请求体参数

        Returns:
            成功时返回解析后的 JSON 字典，失败时返回 None
        """
        try:
            response = requests.post(
                self._his_url,
                headers=self._his_headers,
                data=params,
                timeout=self._timeout,
            )
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "")
            if "json" not in content_type:
                logger.debug("历史 API 返回非标准 Content-Type: %s，尝试直接解析 JSON", content_type)

            data = response.json()

            if data.get("errcode") != "0":
                logger.warning("历史 API 返回错误码: errcode=%s", data.get("errcode"))
                return None

            return data

        except requests.exceptions.RequestException as e:
            logger.error("历史 API 请求失败: %s", str(e))
            return None
        except ValueError as e:
            logger.error("历史 API JSON 解析失败: %s", str(e))
            return None

    def _build_his_params(self, overrides: dict[str, str] | None = None) -> dict[str, str]:
        """
        合并历史接口基础参数与接口特定参数

        Args:
            overrides: 接口特定的参数，会覆盖基础参数中的同名项

        Returns:
            合并后的完整请求参数字典
        """
        params = dict(self._his_base_params)
        if overrides:
            params.update(overrides)
        return params

    def fetch_live_content(self, index: int = 0) -> LiveContentResponse | None:
        """
        获取大盘直播内容（概念点接口）

        Args:
            index: 分页起始位置，默认 0

        Returns:
            成功时返回 LiveContentResponse，失败时返回 None
        """
        params = self._build_params({
            "a": "ZhiBoContent",
            "c": "ConceptionPoint",
            "index": str(index),
        })
        data = self._post(params)
        if data is None:
            return None
        response = LiveContentResponse.from_dict(data)
        logger.info("成功获取直播数据，共 %d 条记录", len(response.items))
        return response

    def fetch_limit_up_ladder(self) -> LimitUpLadderResponse | None:
        """
        获取涨停天梯数据

        Returns:
            成功时返回 LimitUpLadderResponse，失败时返回 None
        """
        params = self._build_params({
            "a": "GetZhangTingTianTi",
            "c": "FuPanLa",
        })
        data = self._post(params)
        if data is None:
            return None
        response = LimitUpLadderResponse.from_dict(data)
        logger.info(
            "成功获取涨停天梯数据，题材 %d 个，个股 %d 只",
            len(response.themes),
            len(response.stocks),
        )
        return response

    def fetch_market_highlights(
        self, index: int = 0, limit: int = 30
    ) -> MarketHighlightsResponse | None:
        """
        获取盘面亮点数据

        Args:
            index: 分页起始位置，默认 0
            limit: 返回条数，默认 30

        Returns:
            成功时返回 MarketHighlightsResponse，失败时返回 None
        """
        params = self._build_params({
            "a": "GetPMSL_PMLD",
            "c": "FuPanLa",
            "Index": str(index),
            "st": str(limit),
        })
        data = self._post(params)
        if data is None:
            return None
        response = MarketHighlightsResponse.from_dict(data)
        logger.info("成功获取盘面亮点数据，共 %d 条", len(response.items))
        return response

    def fetch_historical_live_content(
        self, date: str, index: int = 0, st: int = 0
    ) -> LiveContentResponse | None:
        """
        获取历史大盘直播数据（概念点接口）

        Args:
            date: 历史日期，格式 YYYY-MM-DD
            index: 分页起始位置，默认 0
            st: 返回条数限制，0 表示不限制

        Returns:
            成功时返回 LiveContentResponse，失败时返回 None
        """
        params = self._build_his_params({
            "a": "ZhiBoContent",
            "c": "HisConceptionPoint",
            "index": str(index),
            "st": str(st),
            "Date": date,
        })
        data = self._his_post(params)
        if data is None:
            return None
        response = LiveContentResponse.from_dict(data)
        logger.info("成功获取历史直播数据（%s），共 %d 条记录", date, len(response.items))
        return response

    def fetch_historical_limit_up_ladder(self, date: str) -> LimitUpLadderResponse | None:
        """
        获取历史涨停天梯数据

        Args:
            date: 历史日期，格式 YYYY-MM-DD

        Returns:
            成功时返回 LimitUpLadderResponse，失败时返回 None
        """
        params = self._build_his_params({
            "a": "GetZhangTingTianTi",
            "c": "FuPanLa",
            "Date": date,
        })
        data = self._his_post(params)
        if data is None:
            return None
        response = LimitUpLadderResponse.from_dict(data)
        logger.info(
            "成功获取历史涨停天梯数据（%s），题材 %d 个，个股 %d 只",
            date,
            len(response.themes),
            len(response.stocks),
        )
        return response

    def fetch_historical_market_highlights(
        self, date: str, index: int = 0, limit: int = 30
    ) -> MarketHighlightsResponse | None:
        """
        获取历史盘面亮点数据

        Args:
            date: 历史日期，格式 YYYY-MM-DD
            index: 分页起始位置，默认 0
            limit: 返回条数，默认 30

        Returns:
            成功时返回 MarketHighlightsResponse，失败时返回 None
        """
        params = self._build_his_params({
            "a": "GetPMSL_PMLD",
            "c": "FuPanLa",
            "Index": str(index),
            "st": str(limit),
            "Date": date,
        })
        data = self._his_post(params)
        if data is None:
            return None
        response = MarketHighlightsResponse.from_dict(data)
        logger.info("成功获取历史盘面亮点数据（%s），共 %d 条", date, len(response.items))
        return response
