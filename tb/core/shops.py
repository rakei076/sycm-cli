"""本机记下「登录账号 → 店铺」：一个登录能看几家店时，平台会在请求之间跳店，Client 按这里记的店拦下别家店的数据。
第一次取数时记下；用 --shop 指定别的店时改成那家。

存在整台电脑共用的目录（paths.machine_root）下的 shops.json：{"<平台>:<登录账号编号>": {"shop": 店铺编号, "seen": 日期}}。只有编号，没有经营数据。
"""
from __future__ import annotations

import json
from datetime import date

from .paths import machine_root


def _file():
    return machine_root() / "shops.json"


def _load() -> dict:
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def lookup(platform: str, uid: str) -> str | None:
    return (_load().get(f"{platform}:{uid}") or {}).get("shop")


def remember(platform: str, uid: str, shop: str) -> str | None:
    """记下这次的店铺，返回以前记的（没有就 None）。"""
    path = _file()
    data = _load()
    key = f"{platform}:{uid}"
    before = (data.get(key) or {}).get("shop")
    data[key] = {"shop": shop, "seen": date.today().isoformat()}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return before
