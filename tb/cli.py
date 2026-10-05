"""tb 总入口：tb <平台> <命令...>。各平台的命令由它自己的 cli 模块定义。"""
from __future__ import annotations

import importlib
import sys

from .platforms import PLATFORMS


def _force_utf8() -> None:
    """Windows 中文系统的默认编码是 GBK，输出被管道接走时打印中文/符号会崩；统一用 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _plugin() -> int:
    """tb plugin：看这台电脑装没装取数桥插件（任何一个工具带来的都算），不用连网、不用等插件。"""
    from .core import extension
    found = extension.find_installed()
    for x in found:
        print(f"· {x.browser} · {x.profile}：{'开着' if x.enabled else '停用'}，版本 {x.version or '读不到'}，文件夹 {x.path or '?'}")
    ok, note = extension.status(found)
    print(("✅ " if ok else "⚠️ ") + note)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print("用法：tb <平台> <命令...>    例：tb 1688 doctor\n可用平台：" + "、".join(PLATFORMS) + "\n列出平台：tb --list\n检查插件：tb plugin")
        return 0
    if argv[0] == "--list":
        print("\n".join(PLATFORMS))
        return 0
    if argv[0] == "plugin":
        return _plugin()
    name, rest = argv[0], argv[1:]
    if name not in PLATFORMS:
        print(f"❌ 不认识的平台：{name}。可用：{'、'.join(PLATFORMS)}", file=sys.stderr)
        return 1
    return importlib.import_module(PLATFORMS[name]).main(rest)


if __name__ == "__main__":
    sys.exit(main())
