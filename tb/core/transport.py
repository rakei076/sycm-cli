"""选择取数方式：浏览器插件，或（仅 Mac / Linux）直接读 Chrome 的 cookie。

Windows 上读不到 Chrome 的 cookie，只走插件：等不到插件就报错并给出安装说明。
Mac / Linux 上 <PREFIX>_MODE（如 DMP_MODE）：
  auto（默认）  曾经连上过插件才走插件（避免每次白等）；没连上就退回读 cookie 并说明；从没装过就直接读 cookie。
  extension     强制走插件：等不到就报错并给出安装说明。
  cookies       只读 Chrome 的 cookie。
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from . import bridge, extension
from .client import Client, TbError
from .platform import Platform

CONNECT_WAIT_AUTO = 40.0    # 插件休眠时靠每 30 秒一次的闹钟醒来，所以要覆盖至少一个周期
CONNECT_WAIT_FORCED = 60.0


def mode(plat: Platform) -> str:
    m = (plat.env("MODE") or "auto").strip().lower()
    return m if m in ("auto", "extension", "cookies") else "auto"


def _cookie_client(plat: Platform) -> Client:
    return Client(plat)


def _seen_marker() -> Path:
    """「连上过插件」的标记。一个插件服务所有平台，所以标记也只有一个：任何一个平台连上过，其他平台也优先走插件。
    位置：TB_STATE_ROOT/bridge-seen，默认 ~/.taobao-cli/（Windows：%LOCALAPPDATA%\\taobao-cli\\）。"""
    root = os.environ.get("TB_STATE_ROOT")
    if root:
        return Path(root).expanduser() / "bridge-seen"
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "taobao-cli" / "bridge-seen"
    return Path.home() / ".taobao-cli" / "bridge-seen"


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
    if os.name != "nt":
        hint += f"\n  不想装插件：设置环境变量 {plat.env_prefix}_MODE=cookies 改为直接读 Chrome 的 cookie。"
    return hint


def make_client(plat: Platform) -> Client:
    m = mode(plat)
    windows = os.name == "nt"
    if m == "cookies":
        if windows:
            raise TbError("Windows 上读不到 Chrome 的登录信息，只能通过浏览器插件取数。", stage="连接插件", hint=_install_hint(plat))
        return _cookie_client(plat)
    # 先看浏览器资料里装没装插件：装了（不管是哪个工具带来的）就直接用，不提示安装
    usable, note = extension.status(extension.find_installed())
    if m == "auto" and not windows and not usable and not _seen_marker().exists():
        return _cookie_client(plat)

    server = bridge.BridgeServer(plat)
    server.start()
    forced = m == "extension" or windows   # Windows 没有别的办法：等不到插件就报错
    ok = _wait_for_extension(server, CONNECT_WAIT_FORCED if forced else CONNECT_WAIT_AUTO)
    if not ok:
        server.stop()
        if forced:
            raise TbError("没有连上浏览器插件。", stage="连接插件", hint=_install_hint(plat, "" if usable else note))
        print("⚠️ 浏览器插件没有响应，退回原来的取数办法（读浏览器登录信息）。", file=sys.stderr)
        return _cookie_client(plat)
    got = server.extension_version
    if bridge.version_tuple(got) < bridge.version_tuple(bridge.MIN_EXTENSION_VERSION):
        server.stop()
        msg = f"浏览器里的取数桥插件太旧（{got or '0.3.0 或更早'}），需要 {bridge.MIN_EXTENSION_VERSION} 以上。"
        how = "在 chrome://extensions 里移除旧的取数桥，再按 extension/README.md 加载本工具自带的 extension/unpacked。"
        if forced:
            raise TbError(msg, stage="连接插件", hint=how)
        print(f"⚠️ {msg}先改用读浏览器登录信息的办法。{how}", file=sys.stderr)
        return _cookie_client(plat)
    try:
        _seen_marker().parent.mkdir(parents=True, exist_ok=True)
        _seen_marker().write_text("1")
    except OSError:
        pass
    print(f"已连上浏览器插件，通过你的浏览器取数（用的是浏览器里已登录的{plat.display}）。", file=sys.stderr)
    client = Client(plat, cookies={}, session=bridge.BridgeSession(server))
    client._bridge_server = server  # 进程结束时随之关闭
    return client
