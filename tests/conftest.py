"""pytest 共享配置。

移除 Hermes 终端注入的 PYTHONPATH 条目（hermes-agent 的 python3.11
site-packages），避免其 3.11 二进制包（pydantic_core 等）与项目 venv
（python3.12）冲突导致导入崩溃。等价于运行前 `env -u PYTHONPATH`。
"""

import sys

_HERMES_MARKERS = (".hermes/hermes-agent", "hermes-agent/venv")
sys.path[:] = [
    p for p in sys.path if p and not any(marker in p for marker in _HERMES_MARKERS)
]
