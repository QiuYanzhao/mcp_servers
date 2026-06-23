#!/usr/bin/env python3
"""star_stocks MCP 服务启动脚本。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.mcp_servers.star_stocks.main import main

if __name__ == "__main__":
    main()
