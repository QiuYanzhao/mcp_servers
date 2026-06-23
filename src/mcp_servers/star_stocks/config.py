"""star_stocks 环境初始化（加载 .env、解析项目根目录）。"""

import os
from pathlib import Path


def get_star_stocks_root() -> Path:
    env = os.environ.get("STAR_STOCKS_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    # mcpServers/src/mcp_servers/star_stocks/config.py -> private/star_stocks
    return Path(__file__).resolve().parents[3].parent / "star_stocks"


def init_star_stocks_env() -> Path:
    """加载 star_stocks 的 .env，需在导入 star_stocks 包之前调用。"""
    root = get_star_stocks_root()
    env_file = root / ".env"
    if env_file.exists():
        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)
    return root
