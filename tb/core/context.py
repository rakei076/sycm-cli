"""公共参数自动补全框架：把登记表参数模板里的占位符换成真实值。

占位符写法（整个值就是一个占位符）：`{名字}`、`{名字:参数}`、`{名字:参数:-N}`。
名字对应的解析函数由平台子类通过 `placeholders` 注册（见 tb/platforms/dmp/context.py）。
日期一律用平台给的最新日期推算，不用本机日期。每类查询一次运行只查一次（`once`）。
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Callable

from .errors import TbError

PH = re.compile(r"^\{([a-z0-9_]+)(?::([^:}]+))?(?::(-?\d+))?\}$")


def shift(day: str, offset: str | None) -> str:
    if not offset:
        return day
    d = date.fromisoformat(day[:10]) + timedelta(days=int(offset))
    return d.isoformat()


class Context:
    # 名字 -> 解析函数 (ctx, arg, offset) -> 值；由平台子类覆盖
    placeholders: dict[str, Callable[["Context", str | None, str | None], Any]] = {}

    def __init__(self, client: Any, overrides: dict[str, Any] | None = None, item_id: str | None = None):
        self.client = client
        self.overrides = {k: str(v) for k, v in (overrides or {}).items()}
        self.item_id = item_id
        self._cache: dict[str, Any] = {}

    def once(self, key: str, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    def need_item(self) -> str:
        if not self.item_id:
            raise TbError("这个接口要指定宝贝。", stage="参数补全", hint="请加 --item <宝贝ID>。")
        return str(self.item_id)

    def value(self, raw: Any) -> Any:
        if not isinstance(raw, str):
            return raw
        m = PH.match(raw)
        if not m:
            return raw
        kind, arg, off = m.groups()
        fn = self.placeholders.get(kind)
        if fn is None:
            raise TbError(f"登记表里有不认识的占位符：{raw}", stage="参数补全")
        return fn(self, arg, off)

    def resolve(self, template: dict[str, Any]) -> dict[str, Any]:
        out = {}
        for k, v in template.items():
            out[k] = self.overrides[k] if k in self.overrides else self.value(v)
        for k, v in self.overrides.items():
            out.setdefault(k, v)
        return out
