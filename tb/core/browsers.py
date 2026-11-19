"""一台电脑上几个浏览器（或几个 Chrome 用户资料）都装了取数桥插件时，选定其中一个取数。

为什么：几个插件同时在线，任务谁先来谁拿，各自登录的又可能是不同的账号（比如一个登店铺号、一个登买家号）。
做法（参照 Claude 连 Chrome：连着几个浏览器就列出来、选一个用）：
1. 只有一个在线：就用它，不问。
2. 指定了（tb --browser <账号名或插件编号>，即环境变量 TB_BROWSER）：用它，并按工具记住。
3. 这个工具上次用过哪个、它也在线：照旧用它。
4. 只有一个浏览器登录了淘宝系账号：用它，并记住。
5. 还分不出来：报错，列出每个浏览器登录的账号，让 AI 按用户说的店名或账号挑一个，用 --browser 指定（之后就记住了）。
选定后任务只派给这个插件（BridgeServer.bound）。

记住的选择在 state_root()/browsers.json：{工具名: {"instance": 插件编号, "nick": 当时登录的账号名}}。
tb browser 看记住了什么，tb browser forget [工具] 忘掉。
"""
from __future__ import annotations

import json
import os
import sys
import time

from .errors import TbError
from .paths import state_root

GRACE = 3.0        # 先等这么久，看还有没有别的插件来连（空闲的插件每 2 秒找一次命令行）
LATE_WAIT = 35.0   # 指定的、记住的那个还没来：最多再等这么久（插件睡着时 30 秒醒一次）


def _path():
    return state_root() / "browsers.json"


def load() -> dict:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_all(data: dict) -> None:
    try:
        _path().parent.mkdir(parents=True, exist_ok=True)
        _path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _save(tool: str, instance: str, nick: str) -> None:
    data = load()
    data[tool] = {"instance": instance, "nick": nick}
    data["_multi"] = True
    _save_all(data)


def mark_multi() -> None:
    """第二个插件来连时调用：记下这台电脑会有几个插件同时在线，以后每次先多等一会儿再选。"""
    data = load()
    if not data.get("_multi"):
        data["_multi"] = True
        _save_all(data)


def wanted() -> str:
    return (os.environ.get("TB_BROWSER") or "").strip()


def who(server, instance: str) -> str:
    """问这个插件：浏览器里现在登录的淘宝系账号叫什么（没登录回空）。只回账号名，不回 cookie。"""
    try:
        res = server.submit({"account": {"op": "list", "scope": "taobao"}}, 12, to=instance)
    except Exception:   # 这个浏览器连过又关了、或者不回话：当它没登录，不拖累别的
        return ""
    if res.get("error"):
        return ""
    return (((res.get("account") or {}).get("current") or {}).get("taobao") or {}).get("nick") or ""


def _wait(server, seconds: float, until) -> None:
    end = time.time() + seconds
    while time.time() < end and not until():
        time.sleep(0.2)


def _bind(server, tool: str, instance: str, nick: str, remember: bool) -> None:
    server.bound = instance
    if remember:
        _save(tool, instance, nick)
    print(f"这台电脑上有 {len(server.instances)} 个浏览器开着取数桥，这次用登录「{nick or '未登录'}」的那个（插件编号 {instance}）。",
          file=sys.stderr)


def _listing(nicks: dict) -> str:
    return "\n".join(f"  · 「{n or '没有登录淘宝'}」（插件编号 {i}）" for i, n in nicks.items())


def choose(server, plat) -> None:
    """插件已经连上之后、取数之前调用。选定后 server.bound 是那个插件的编号；只有一个在线时也绑定它。"""
    data = load()
    tool, want, mem = plat.name, wanted(), data.get(plat.name) or {}
    if want or data.get("_multi"):   # 这台电脑上出现过几个插件同时在线，才多等一会儿看还有谁来（平时不拖慢）
        _wait(server, GRACE, lambda: False)
    if want:
        nicks: dict[str, str] = {}

        def hits():
            if want in server.instances:   # 写的是插件编号：只问它一个
                if want not in nicks:
                    nicks[want] = who(server, want)
                return [want]
            for i in server.instances:
                if i not in nicks:
                    nicks[i] = who(server, i)
            return [i for i, n in nicks.items() if i == want or (n and want in n)]
        _wait(server, LATE_WAIT, lambda: len(hits()) == 1)
        found = hits()
        if len(found) == 1:
            return _bind(server, tool, found[0], nicks[found[0]], remember=True)
        raise TbError(f"没有找到登录「{want}」的浏览器（或者不止一个对得上）。现在开着取数桥的浏览器：\n" + _listing(nicks),
                      stage="选浏览器", hint="用 --browser 写准账号名或插件编号；要的那个浏览器得开着、插件开着。")
    if mem.get("instance") and mem["instance"] not in server.instances and len(server.instances) >= 1:
        _wait(server, LATE_WAIT, lambda: mem["instance"] in server.instances)
    if len(server.instances) <= 1:
        server.bound = server.instances[0] if server.instances else None
        return
    if not data.get("_multi"):
        data["_multi"] = True
        _save_all(data)
    if mem.get("instance") in server.instances:
        return _bind(server, tool, mem["instance"], mem.get("nick") or "", remember=False)
    nicks = {i: who(server, i) for i in server.instances}
    logged = [i for i, n in nicks.items() if n]
    if len(logged) == 1:
        return _bind(server, tool, logged[0], nicks[logged[0]], remember=True)
    raise TbError(f"这台电脑上有 {len(nicks)} 个浏览器开着取数桥，分不出这次该用哪个：\n" + _listing(nicks),
                  stage="选浏览器",
                  hint="按要看的店或账号选一个：tb --browser <账号名或插件编号> <平台> <命令>（只要指定一次，这个工具以后都记住）。")


def main(argv: list[str]) -> int:
    """tb browser：看每个工具记住用哪个浏览器；tb browser forget [工具]：忘掉（下次重新选）。"""
    data = load()
    if argv[:1] == ["forget"]:
        for tool in argv[1:] or [k for k in data if not k.startswith("_")]:
            data.pop(tool, None)
        _save_all(data)
        print("已忘掉，下次几个浏览器都开着时会重新选。")
        return 0
    tools = {k: v for k, v in data.items() if not k.startswith("_")}
    if not tools:
        print("还没有记住任何选择（只有一个浏览器开着取数桥时不用选）。")
    for tool, v in tools.items():
        print(f"· {tool}：登录「{v.get('nick') or '?'}」的浏览器（插件编号 {v.get('instance')}）")
    print("换一个：tb --browser <账号名或插件编号> <平台> <命令>；忘掉：tb browser forget [工具]")
    return 0
