"""命令行的状态目录。

两种：
- state_root()：这一份工具自己的（连上过插件的标记、MCP 输出）。TB_STATE_ROOT 可以改；默认 ~/.taobao-cli/，
  Windows 是 %LOCALAPPDATA%\\taobao-cli\\。
- machine_root()：整台电脑共用的（插件排队锁、运行日志、账号对应的店铺）。浏览器插件只有一个，
  电脑上装了几份工具（比如两个 AI 助手各带一份、各自设了 TB_STATE_ROOT）也必须排同一个队、记进同一份日志，
  所以不跟着 TB_STATE_ROOT 走；只有测试用 TB_MACHINE_ROOT 指到临时目录。
"""
from __future__ import annotations

import os
from pathlib import Path


def _default() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "taobao-cli"
    return Path.home() / ".taobao-cli"


def state_root() -> Path:
    root = os.environ.get("TB_STATE_ROOT")
    return Path(root).expanduser() if root else _default()


def machine_root() -> Path:
    root = os.environ.get("TB_MACHINE_ROOT")
    return Path(root).expanduser() if root else _default()
