"""接口登记表：每个平台一份 endpoints.json，一行一个只读接口。

字段：key（命令里用的名字）、board（板块）、page（页面）、route（页面路由）、title（中文说明）、
host（Platform.hosts 里的名字）、path、params（参数模板，占位符见 context.py）、
list_path（可选：这个路径下应当有数据，空了就报错）、note（可选：备注，比如需要开通）。
"""
from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Endpoint:
    key: str
    board: str
    page: str
    route: str
    title: str
    host: str
    path: str
    params: dict[str, Any] = field(default_factory=dict)
    list_path: str | None = None
    note: str | None = None

    @property
    def needs_item(self) -> bool:
        return any(isinstance(v, str) and v.startswith("{item") for v in self.params.values())


def load_file(path: Path) -> list[Endpoint]:
    return [Endpoint(**r) for r in json.loads(path.read_text(encoding="utf-8"))]


def find(endpoints: list[Endpoint], key: str, list_cmd: str) -> Endpoint:
    """按 key 找接口；找不到时提示最接近的几个。list_cmd 是「列出全部」的命令，例如 `dmp list`。"""
    eps = {e.key: e for e in endpoints}
    if key in eps:
        return eps[key]
    close = difflib.get_close_matches(key, eps.keys(), n=3, cutoff=0.4)
    tip = f"，你是不是要找：{'、'.join(close)}" if close else f"；用 `{list_cmd}` 查看全部"
    raise KeyError(f"登记表里没有 {key}{tip}")
