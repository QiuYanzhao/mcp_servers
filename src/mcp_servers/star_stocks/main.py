"""star_stocks MCP 服务入口。"""

import logging
import sys

from .service import StarStocksService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    try:
        logger.info("启动 star_stocks MCP 服务...")
        service = StarStocksService()
        service.run(transport="stdio")
    except KeyboardInterrupt:
        logger.info("服务被用户中断")
        sys.exit(0)
    except Exception as e:
        logger.error("服务启动失败: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
