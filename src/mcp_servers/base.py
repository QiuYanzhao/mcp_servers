"""
MCP服务器基础模块

提供MCP服务器的基础类和通用功能
"""

import logging
from typing import Any, Dict
from mcp.server.fastmcp import FastMCP

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class BaseMCPServer:
    """
    MCP服务器基类

    提供MCP服务器的基础功能和通用方法
    """

    def __init__(self, name: str, version: str = "1.0.0"):
        """
        初始化MCP服务器

        Args:
            name: 服务器名称
            version: 服务器版本
        """
        self.name = name
        self.version = version
        self.mcp = FastMCP(name)
        logger.info(f"初始化MCP服务器: {name} v{version}")

    def register_tools(self):
        """
        注册工具方法

        子类需要实现此方法来注册具体的工具
        """
        raise NotImplementedError("子类必须实现register_tools方法")

    def register_resources(self):
        """
        注册资源方法

        子类需要实现此方法来注册具体的资源
        """
        raise NotImplementedError("子类必须实现register_resources方法")

    def register_prompts(self):
        """
        注册提示模板方法

        子类需要实现此方法来注册具体的提示模板
        """
        raise NotImplementedError("子类必须实现register_prompts方法")

    def run(self, transport: str = "stdio"):
        """
        运行MCP服务器

        Args:
            transport: 传输方式，支持"stdio"和"http"
        """
        logger.info(f"启动MCP服务器: {self.name}")
        self.mcp.run(transport=transport)

    def get_server_info(self) -> Dict[str, Any]:
        """
        获取服务器信息

        Returns:
            包含服务器信息的字典
        """
        return {
            "name": self.name,
            "version": self.version,
            "transport": "stdio",
        }
