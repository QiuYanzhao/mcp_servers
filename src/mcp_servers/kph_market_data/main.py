"""
开盘红平台行情数据MCP服务启动脚本

用于启动开盘红平台行情数据MCP服务
"""

import logging
import sys
from .service import KPHMarketDataService

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """主函数"""
    try:
        logger.info("启动开盘红平台行情数据MCP服务...")
        service = KPHMarketDataService()
        service.run(transport="stdio")
    except KeyboardInterrupt:
        logger.info("服务被用户中断")
        sys.exit(0)
    except Exception as e:
        logger.error(f"服务启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()