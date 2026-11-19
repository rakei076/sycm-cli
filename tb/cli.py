# 店铺数据工具 · 作者 Rakel · https://rakel.top · MIT 协议
"""tb 总入口：tb <平台> <命令...>。各平台的命令由它自己的 cli 模块定义。"""
from __future__ import annotations

import importlib
import os
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


GLOBAL_OPTIONS = {"--account": "TB_ACCOUNT", "--shop": "TB_SHOP", "--browser": "TB_BROWSER"}


def _take_globals(argv: list[str]) -> list[str]:
    """放在平台前面的总选项，放进环境变量交给取数那一层：
    tb --account <名字> <平台> <命令…>   先换成这个账号再取数（TB_ACCOUNT）
    tb --shop <店铺编号> <平台> <命令…>  这个登录能看几家店时，只要这一家的数据（TB_SHOP）
    tb --browser <账号名或插件编号> <平台> <命令…>  几个浏览器都装了取数桥时，用登录这个账号的那个（TB_BROWSER，按工具记住）"""
    while argv:
        name, _, value = argv[0].partition("=")
        if name not in GLOBAL_OPTIONS:
            break
        if not value:
            if len(argv) < 2:
                break
            value, argv = argv[1], argv[2:]
        else:
            argv = argv[1:]
        os.environ[GLOBAL_OPTIONS[name]] = value
    return argv


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    argv = _take_globals(list(sys.argv[1:] if argv is None else argv))
    if not argv or argv[0] in ("-h", "--help"):
        from .core import modules
        print("用法：tb <平台> <命令...>    例：tb sycm doctor\n已打开的工具：" + "、".join(modules.enabled())
              + "\n打开 / 关闭工具：tb modules\n检查插件：tb plugin"
              "\n给 AI 客户端用的 MCP 服务：tb mcp\n切换账号：tb account（读取指定账号的数据：tb --account <账号名称> <平台> <命令>）"
              "\n指定店铺（一个账号可查看多个店铺时）：tb --shop <店铺编号> <平台> <命令>"
              "\n几个浏览器都装了取数桥时指定用哪个：tb --browser <账号名或插件编号> <平台> <命令>（按工具记住，tb browser 查看）"
              "\n运行日志：tb log（遇到问题时运行 tb log export，并将生成的 zip 文件发送给开发者）"
              "\n分析方法：tb guide（自定义分析要求保存在 tb guide --where 显示的文件夹中，优先使用）")
        return 0
    if argv[0] == "--list":
        from .core import modules
        print("\n".join(modules.enabled()))
        return 0
    if argv[0] == "log":
        from .core import runlog
        return runlog.main(argv[1:])
    if argv[0] == "guide":
        from .core import guides
        return guides.main(argv[1:])
    # tb mcp：本地 MCP 服务。交付包的启动脚本固定跑 tb <平台> …，所以 tb <平台> mcp 也是它
    if argv[0] == "mcp" or (argv[0] in PLATFORMS and argv[1:2] == ["mcp"]):
        from . import mcp_server
        return mcp_server.main(argv[argv.index("mcp") + 1:])
    from .core import runlog
    runlog.begin(argv)
    code = 1
    try:
        code = _dispatch(argv)
        return code
    except SystemExit as e:   # argparse、平台命令行用 sys.exit 退出
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        raise
    except KeyboardInterrupt:
        code = 130
        raise
    except BaseException as e:
        runlog.failure(e)
        raise
    finally:
        runlog.finish(code)


def _dispatch(argv: list[str]) -> int:
    if argv[0] == "modules":
        from .core import modules
        return modules.main(argv[1:])
    if argv[0] == "plugin":
        return _plugin()
    if argv[0] == "account":
        from .core import accounts
        return accounts.main(argv[1:])
    if argv[0] == "browser":
        from .core import browsers
        return browsers.main(argv[1:])
    name, rest = argv[0], argv[1:]
    if name not in PLATFORMS:
        print(f"❌ 不认识的平台：{name}。可用：{'、'.join(PLATFORMS)}", file=sys.stderr)
        return 1
    from .core import modules
    if name not in modules.enabled():
        print(f"❌ {modules.not_enabled_hint(name)}", file=sys.stderr)
        return 1
    result = importlib.import_module(PLATFORMS[name]).main(rest)
    return 0 if result is None else result

if __name__ == "__main__":
    sys.exit(main())
