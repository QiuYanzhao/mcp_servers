"""序列化与响应辅助。"""

import json
from typing import Any

from pydantic import BaseModel


def to_json(data: Any) -> str:
    if isinstance(data, BaseModel):
        payload = data.model_dump(mode="json")
    elif isinstance(data, list) and data and isinstance(data[0], BaseModel):
        payload = [item.model_dump(mode="json") for item in data]
    else:
        payload = data
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def ok(data: Any) -> str:
    return to_json(data)


def err(message: str) -> str:
    return json.dumps({"error": message}, ensure_ascii=False)
