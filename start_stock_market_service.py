#!/usr/bin/env python3
"""
A股行情数据MCP服务启动脚本

用于启动A股行情数据MCP服务
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.mcp_servers.stock_market.main import main


if __name__ == "__main__":
    main()