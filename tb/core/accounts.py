"""tb account：在多个账号之间切换。

账号的登录 cookie 存在浏览器插件里（插件弹窗也能保存、切换、删除）；这里只叫插件「列出」「保存为某名字」「换成某名字」，
插件只回账号名和昵称，登录 cookie 不出浏览器。账号是淘宝系的（淘宝、天猫、千牛、生意参谋、达摩盘、万相台共用一套登录）。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import datetime

from . import bridge, browsers, runlog, transport
from .platform import Platform

ACCOUNT = Platform(
    name="account", display="账号切换", hosts={}, login_page="https://www.taobao.com", launch_url="",
    login_cookies=(), cookie_domains=(), referer="", expired_hints=(), write_re=re.compile(r"$^"),
    env_prefix="TB_ACCOUNT")

# Mac 上取数直接读 Chrome 存在硬盘上的 cookie；插件换完账号后，Chrome 过一会儿才写到硬盘
DISK_ID_COOKIE = ("taobao.com", "unb")
DISK_WAIT = 60.0


def _connect() -> bridge.BridgeServer:
    server = bridge.BridgeServer(ACCOUNT)
    server.start()
    if not transport._wait_for_extension(server, transport.CONNECT_WAIT_FORCED):
        server.stop()
        raise bridge.BridgeError("没有连上浏览器插件：账号切换要用取数桥插件。确认 Chrome 开着、插件开着，再试一次。")
    try:
        browsers.choose(server, ACCOUNT)   # 几个浏览器都装了插件时，换号只对选定的那个浏览器
    except BaseException:
        server.stop()
        raise
    got, need = server.version_of(server.bound), bridge.min_version(ACCOUNT)
    if bridge.version_tuple(got) < bridge.version_tuple(need):
        server.stop()
        raise bridge.BridgeError(f"浏览器里的取数桥插件是 {got or '旧版'}，账号切换要 {need} 以上：请更新插件。")
    return server


def _ask(server: bridge.BridgeServer, op: str, name: str = "") -> dict:
    res = server.submit({"account": {"op": op, "scope": "taobao", "name": name}}, 60)
    if res.get("error"):
        runlog.event("account", op=op, name=name, error=runlog._clean(res["error"]))
        raise bridge.BridgeError(str(res["error"]))
    acc = res["account"]
    if op in ("use", "save"):
        runlog.event("account", op=op, name=acc.get("name"), nick=acc.get("nick"), uid=acc.get("uid"),
                     already=bool(acc.get("already")))
    return acc


def _disk_uid() -> str | None:
    import browser_cookie3
    from urllib.parse import unquote
    domain, name = DISK_ID_COOKIE
    try:
        jar = browser_cookie3.chrome()
    except browser_cookie3.BrowserCookieError:
        return None
    return next((unquote(c.value) for c in jar if c.name == name and domain in (c.domain or "")), None)


def _wait_disk(uid: str) -> bool:
    """Mac：等 Chrome 把换好的登录写到硬盘，之后直接读 cookie 的取数才会用新账号。"""
    end = time.time() + DISK_WAIT
    while time.time() < end:
        if _disk_uid() == uid:
            return True
        time.sleep(2)
    return False


def _when(ms: float | None) -> str:
    return datetime.fromtimestamp(ms / 1000).strftime("%m-%d %H:%M:%S") if ms else "?"


def cmd_list(server, args) -> int:
    res = _ask(server, "list")
    cur = res["current"]["taobao"]
    now = f"现在登录：{cur['nick'] or cur['uid']}" if cur["loggedIn"] else "现在没有登录"
    print(f"【{cur['label']}】{now}")
    accounts = res["scopes"].get("taobao") or []
    if not accounts:
        print("  （还没有存过账号。在浏览器里登录后运行：tb account save <名字>）")
    for a in accounts:
        mark = "● " if a["active"] else "  "
        checked = a.get("alive")
        note = ("  ❌ 上次检查已掉线" if checked is False else "  ✅ 上次检查还在" if checked else "") + (f"（{_when(a['checkedAt'])}）" if a.get("checkedAt") else "")
        note = note or ("  ⚠️ 可能已过期，切过去后要重新登录" if a["expired"] else "")
        print(f"  {mark}{a['name']}（{a['nick']}，{_when(a['savedAt'])} 更新）{note}")
    return 0


def cmd_save(server, args) -> int:
    r = _ask(server, "save", args.name or "")
    print(f"✅ 已把现在登录的淘宝/天猫账号（{r['nick']}）存为「{r['name']}」。以后用 tb account use {r['name']} 换回来。")
    return 0


def cmd_use(server, args) -> int:
    r = _ask(server, "use", args.name)
    if r.get("already"):
        print(f"✅ 现在登录的已经是「{r['name']}」（{r['nick']}）。")
        return 0
    print(f"✅ 已换成「{r['name']}」（{r['nick']}）。浏览器里开着的后台页面刷新一下就是这个账号。")
    if os.name != "nt":
        if _wait_disk(r["uid"]):
            print("   直接读 Chrome 登录的取数也已经是这个账号。")
        else:
            print("   ⚠️ Chrome 还没把新登录写到硬盘：接下来一分钟内的取数可能还是上一个账号，稍等再取。", file=sys.stderr)
    return 0


def cmd_check(server, args) -> int:
    rows = _ask(server, "check", args.name or "")
    if not rows:
        print("还没有存过账号。")
        return 0
    for r in rows:
        mark = "✅ 还在" if r["alive"] else "❌ 掉线了" if r["alive"] is False else "❓ 查不出"
        print(f"{mark}  {r['name']}（{r['how']}）")
    if any(r["alive"] is False for r in rows):
        print("掉线的账号：在插件里切过去，按提示重新登录一次，插件会自动把存档换成新的登录。")
    return 0


def cmd_log(server, args) -> int:
    for e in _ask(server, "log"):
        rest = "  ".join(f"{k}={v}" for k, v in e.items() if k not in ("t", "op", "kind"))
        print(f"{_when(e['t'])}  {e['op']}  {rest}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="tb account", description="在多个淘宝 / 天猫账号之间切换（账号存在浏览器插件里）。")
    sp = ap.add_subparsers(dest="cmd")
    sp.add_parser("list", help="列出存过的账号和现在登录的账号（默认）")
    sp.add_parser("log", help="插件里最近的账号操作记录（排查切换问题用）")
    ck = sp.add_parser("check", help="查存下的账号还在不在（不切换、不影响浏览器里现在的登录）")
    ck.add_argument("name", nargs="?", help="只查这一个；不写就全部查")
    sv = sp.add_parser("save", help="把浏览器里现在登录的账号存下来")
    sv.add_argument("name", nargs="?", help="起个名字，如 主店；不写就用账号昵称")
    us = sp.add_parser("use", help="换成存过的某个账号")
    us.add_argument("name")
    args = ap.parse_args(argv)
    run = {"save": cmd_save, "use": cmd_use, "log": cmd_log, "check": cmd_check}.get(args.cmd, cmd_list)
    try:
        server = _connect()
    except bridge.BridgeError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    try:
        return run(server, args)
    except bridge.BridgeError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    finally:
        server.stop()
