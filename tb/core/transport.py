"""选择取数方式：浏览器插件，或（仅 Mac / Linux）直接读 Chrome 的 cookie。

Windows 上读不到 Chrome 的 cookie，只走插件：等不到插件就报错并给出安装说明。
Mac / Linux 上 <PREFIX>_MODE（如 DMP_MODE）：
  auto（默认）  先直接读 Chrome 的 cookie，不用插件；读不到登录（如 Chrome 重启后会话 cookie 没了）
                且装过插件，才改走插件。没装插件就照常提示去 Chrome 登录。
  extension     强制走插件：等不到就报错并给出安装说明。
  cookies       只读 Chrome 的 cookie。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from . import bridge, browsers, extension, runlog
from .auth import NotLoggedIn
from .client import Client, TbError
from .platform import Platform

CONNECT_WAIT_FORCED = 60.0


def mode(plat: Platform) -> str:
    m = (plat.env("MODE") or "auto").strip().lower()
    return m if m in ("auto", "extension", "cookies") else "auto"


def _cookie_client(plat: Platform) -> Client:
    client = Client(plat)
    runlog.event("connect", platform=plat.name, mode="cookies")
    return client


def _seen_marker() -> Path:
    """「连上过插件」的标记。一个插件服务所有平台，所以标记也只有一个：Mac 上直接读不到登录时，任何一个平台连上过插件，就改走插件。
    位置：TB_STATE_ROOT/bridge-seen，默认 ~/.taobao-cli/（Windows：%LOCALAPPDATA%\\taobao-cli\\）。"""
    from .paths import state_root
    return state_root() / "bridge-seen"


def _wait_for_extension(server, seconds: float) -> bool:
    """等插件来连。插件平时每 30 秒醒一次；用户开着平台页面时几秒内就会来。
    不去打开浏览器页面（会在用户的 Chrome 里留下多余标签页）；等得久一点时在终端说明原因。"""
    if server.extension_seen.wait(min(4.0, seconds)):
        return True
    print("… 正在等浏览器插件响应（它每隔约 30 秒会检查一次）", file=sys.stderr)
    end = time.time() + max(0.0, seconds - 4.0)
    while time.time() < end:
        if server.extension_seen.wait(0.5):
            return True
    return server.extension_seen.is_set()


def _install_hint(plat: Platform, note: str = "") -> str:
    hint = ((note + "\n") if note else "") + ("没有连上浏览器插件。请确认：\n"
            f"  1. 已在 Chrome 里安装取数桥插件（安装方法见 extension/README.md）；\n"
            f"  2. Chrome 开着，并且有一个已登录的{plat.display}页面（{plat.login_page}）。")
    if os.name != "nt" and not plat.extension_only:
        hint += f"\n  不想装插件：设置环境变量 {plat.env_prefix}_MODE=cookies 改为直接读 Chrome 的 cookie。"
    return hint


SANDBOX_ENV = {"CODEX_SANDBOX": "Codex", "CODEX_SANDBOX_NETWORK_DISABLED": "Codex"}   # AI 助手在沙箱里跑命令时设的环境变量


def _ai_sandbox() -> str:
    """命令是不是在 AI 助手的沙箱里跑（沙箱会拦本机端口，插件连不进来）。返回助手名，不是返回空。"""
    return next((who for key, who in SANDBOX_ENV.items() if os.environ.get(key)), "")


def _browser_running() -> bool | None:
    """Chrome 或 Edge 开着没有。查不了（没权限等）返回 None，不下结论。"""
    try:
        if os.name == "nt":
            out = subprocess.run(["tasklist", "/NH"], capture_output=True, text=True, timeout=5).stdout.lower()
            return "chrome.exe" in out or "msedge.exe" in out
        out = subprocess.run(["ps", "-axo", "comm"], capture_output=True, text=True, timeout=5).stdout
        return any(x in out for x in ("Google Chrome", "Microsoft Edge", "/chrome", "chromium"))
    except Exception:
        return None


def _no_connection_hint(plat: Platform, found: list) -> str:
    """连不上插件时，按最可能的原因给一句具体的做法（AI 助手照着转告用户，别自己另想办法取数）。"""
    who = _ai_sandbox()
    if who:
        return (f"这条命令是在 {who} 的沙箱里运行的，沙箱拦了本机端口，浏览器插件连不进来。\n"
                f"  做法：改用 MCP——在你自己打开的终端里运行一次 mcp install，完全退出并重开 {who}，之后让它通过 MCP 取数；"
                "也可以在你自己打开的终端里运行这条命令。\n"
                "  不要改用 AI 助手自带的浏览器取数：那样用的是另一套登录，也绕开了只读和限速的保护。")
    if _browser_running() is False:
        return "Chrome 没有开着：打开装了取数桥插件的那个 Chrome，保持开着，再运行一次。"
    usable, note = extension.status(found)
    if not usable:
        return note + f"\n  装好后在同一个 Chrome 里打开 {plat.login_page} 确认已登录，再运行一次。"
    return ("取数桥插件装着也开着，但 1 分钟内没有连上：\n"
            "  1. 点 Chrome 右上角的取数桥图标看连接状态；不对就在 chrome://extensions 里点一下它的「刷新」；\n"
            "  2. 在你自己打开的终端里运行一次这条命令（AI 助手可能拦了本机端口）；\n"
            "  3. 杀毒或安全软件拦了本机 127.0.0.1 也会这样，把它加入信任。")


def wanted_account() -> str:
    """tb --account <名字> 指定的账号（总入口放进环境变量 TB_ACCOUNT，MCP 的 run 也这样传）。"""
    return (os.environ.get("TB_ACCOUNT") or "").strip()


def _use_account(server, client: Client, name: str) -> None:
    """拿到排队锁之后、取数之前先换号：换号和取数在同一条命令里，别的命令插不进来。"""
    res = server.submit({"account": {"op": "use", "scope": "taobao", "name": name}}, 60)
    if res.get("error"):
        raise TbError(f"无法切换到账号「{name}」：{res['error']}", stage="切换账号",
                      hint="请运行 tb account list 查看已保存的账号名称（需完全一致）；如账号已过期，请在插件中切换到该账号并重新登录。")
    acc = res["account"]
    client.session.account = {"uid": acc.get("uid") or "", "nick": acc.get("nick") or ""}
    client.session.instance = res.get("instance") or ""   # 换号的是哪个插件，取数也必须是它
    runlog.event("account", name=acc.get("name"), nick=acc.get("nick"), uid=acc.get("uid"), already=bool(acc.get("already")))
    print(f"已切换到账号「{acc.get('name')}」（{acc.get('nick')}），开始读取数据。", file=sys.stderr)


def make_client(plat: Platform) -> Client:
    m = "extension" if plat.extension_only else mode(plat)
    windows = os.name == "nt"
    account = wanted_account()
    if account:
        if m == "cookies":
            raise TbError("指定账号（--account）需要通过取数桥插件切换，无法与直接读取 Cookie 的方式同时使用。", stage="切换账号",
                          hint=f"请去掉 {plat.env_prefix}_MODE=cookies 后重新运行。")
        m = "extension"
    if browsers.wanted():
        if m == "cookies":
            raise TbError("指定浏览器（--browser）要通过取数桥插件，无法与直接读取 Cookie 的方式同时使用。", stage="选浏览器",
                          hint=f"请去掉 {plat.env_prefix}_MODE=cookies 后重新运行。")
        m = "extension"   # 直接读 Cookie 读的是默认 Chrome 资料，不是指定的那个浏览器
    if m == "cookies":
        if windows:
            raise TbError("Windows 上读不到 Chrome 的登录信息，只能通过浏览器插件取数。", stage="连接插件", hint=_install_hint(plat))
        return _cookie_client(plat)
    found = extension.find_installed()
    usable, note = extension.status(found)
    if m == "auto" and not windows:
        # Mac 先直接读 Chrome 的登录信息：Chrome 里登录着就能用，不经过插件
        try:
            return _cookie_client(plat)
        except NotLoggedIn:
            if not usable and not _seen_marker().exists():
                raise
            print("直接读 Chrome 的登录信息没读到，改用浏览器插件取数。", file=sys.stderr)
            m = "extension"

    server = bridge.BridgeServer(plat)
    server.start()
    ok = _wait_for_extension(server, CONNECT_WAIT_FORCED)
    if not ok:
        server.stop()
        raise TbError("没有连上浏览器插件。", stage="连接插件", hint=_no_connection_hint(plat, found))
    try:
        browsers.choose(server, plat)   # 几个浏览器都装了插件时选定一个，任务只派给它
    except BaseException:
        server.stop()
        raise
    got = server.version_of(server.bound)   # 查选定的那个插件的版本
    need = bridge.min_version(plat)
    if bridge.version_tuple(got) < bridge.version_tuple(need):
        server.stop()
        msg = f"浏览器里的取数桥插件太旧（{got or '0.3.0 或更早'}），需要 {need} 以上。"
        how = "在 chrome://extensions 里移除旧的取数桥，再按 extension/README.md 加载本工具自带的 extension/unpacked。"
        raise TbError(msg, stage="连接插件", hint=how)
    try:
        _seen_marker().parent.mkdir(parents=True, exist_ok=True)
        _seen_marker().write_text("1")
    except OSError:
        pass
    print(f"已连上浏览器插件，通过你的浏览器取数（用的是浏览器里已登录的{plat.display}）。", file=sys.stderr)
    runlog.event("connect", platform=plat.name, mode="extension", extension=got, port=server.port)
    client = Client(plat, cookies={}, session=bridge.BridgeSession(server))
    client._bridge_server = server  # 进程结束时随之关闭
    if account:
        try:
            _use_account(server, client, account)
        except BaseException:
            server.stop()
            raise
    return client
