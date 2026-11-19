"""工具模块：包里只带用户要的工具，别的需要时再下载装上（tb modules enable <模块>）。

- 装了没有：看 tb/platforms/ 下有没有这个工具的代码目录。
- 打开了没有：装了的默认都打开；scripts/tb.sh modules disable 可以先关掉（不删），选择记在包根目录的 modules.json。
- 下载：模块包的文件名和校验值记在包里的 tb/modules_manifest.json（打包时写），先试码云、再试 GitHub（每个工具在自己的仓库）；
  校验值对不上不装。下载不了时，可以手动下载模块包，用 scripts/tb.sh modules install <文件> 装。
"""
from __future__ import annotations

import hashlib
import importlib
import io
import json
import os
import urllib.request
import zipfile
from pathlib import Path

from ..platforms import PLATFORMS

ROOT = Path(__file__).resolve().parents[2]          # 包根目录（tb/ 的上一层）
CHOICE_FILE = ROOT / "modules.json"
MANIFEST_FILE = ROOT / "tb" / "modules_manifest.json"
MIRROR_ENV = "TB_MODULE_MIRROR"                      # 另加一个下载地址（排在最前，测试和自建镜像用），{file} 换成文件名

# 每个模块的代码目录（tb/platforms/ 下）
DIRS = {"sycm": ("sycm",), "alimama": ("alimama",), "dmp": ("dmp",), "qianniu": ("qianniu",), "voc": ("voc",)}
# 每个模块一句话：列表、推荐时给用户看
ABOUT = {
    "sycm": "生意参谋：店铺大盘、商品、交易、退款、客服；日检、周复盘、单品诊断报告",
    "alimama": "万相台：广告花费、ROI、计划和关键词报表、在投计划",
    "dmp": "达摩盘：人群资产体检、人群画像、竞品对比、同店对标",
    "qianniu": "千牛：差评巡检、退款售后、待发货、物流、商品限流",
    "voc": "竞品评价：竞品的评价、问大家和买家秀，痛点报告（要淘宝买家账号）",
}


def label(name: str) -> str:
    return ABOUT.get(name, name).split("：")[0]


def installed() -> list[str]:
    return [n for n in PLATFORMS if all((ROOT / "tb" / "platforms" / d).is_dir() for d in DIRS[n])]


def _read_choice() -> list[str] | None:
    try:
        names = json.loads(CHOICE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return names if isinstance(names, list) else None


def enabled() -> list[str]:
    """装了并且没关掉的模块，按注册表的顺序。"""
    have, chosen = installed(), _read_choice()
    return [n for n in have if chosen is None or n in chosen]


def downloadable() -> list[str]:
    """下载清单里有的模块（能现场下载）。只公开了部分工具，清单里只写公开的那几个。"""
    try:
        return [n for n in PLATFORMS if n in json.loads(MANIFEST_FILE.read_text(encoding="utf-8")).get("modules", {})]
    except (OSError, ValueError):
        return []


def offered() -> list[str]:
    """这个包里能用的模块：装了的，加上能下载的。"""
    have, dl = installed(), downloadable()
    return [n for n in PLATFORMS if n in have or n in dl]


def disabled() -> list[str]:
    """能用但还没打开的模块：没装但能下载的，和装了但关掉的。"""
    on = enabled()
    return [n for n in offered() if n not in on]


def display(name: str) -> str:
    from .platform import Platform
    mod = importlib.import_module(PLATFORMS[name].rsplit(".", 1)[0] + ".platform")
    return next((v.display for v in vars(mod).values() if isinstance(v, Platform)), name)


def _save(names: list[str]) -> None:
    CHOICE_FILE.write_text(json.dumps([n for n in PLATFORMS if n in names], ensure_ascii=False) + "\n", encoding="utf-8")


def _check(names: list[str]) -> list[str]:
    ok = offered()
    bad = [n for n in names if n not in ok]
    if bad:
        raise ValueError(f"这个包里没有：{'、'.join(bad)}，也不能下载。可用：{'、'.join(ok)}")
    return names


# ---------- 下载和安装 ----------

class DownloadFailed(RuntimeError):
    pass


def _manifest() -> dict:
    try:
        return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise DownloadFailed("这个包没有模块下载清单（tb/modules_manifest.json），没法自动下载。请下载包含这个工具的完整包。")


def _urls(name: str) -> list[str]:
    """这个模块包的下载地址：清单里写好的（先码云再 GitHub，各工具在自己的仓库），前面可以用环境变量另加一个。"""
    info = _manifest()["modules"].get(name) or {}
    extra = [os.environ[MIRROR_ENV].replace("{file}", info.get("file", ""))] if os.environ.get(MIRROR_ENV) else []
    return extra + list(info.get("urls", []))


def _allowed(name: str, member: str) -> bool:
    """模块包里只能有这个模块自己的文件：代码目录、说明、参考文档、启动脚本。"""
    p = member.replace("\\", "/")
    if p.startswith("/") or ".." in p.split("/"):
        return False
    return (any(p.startswith(f"tb/platforms/{d}/") for d in DIRS[name])
            or p in (f"tools/{name}.md", f"scripts/{name}.sh", f"scripts/{name}.cmd")
            or p.startswith(("references/", "docs/")))


def install_zip(name: str, data: bytes) -> None:
    """校验并装上一个模块包。"""
    info = _manifest()["modules"].get(name) or {}
    digest = hashlib.sha256(data).hexdigest()
    if digest != info.get("sha256"):
        raise DownloadFailed(f"「{label(name)}」模块包的校验值不对（文件可能不完整或被改过），没有安装。")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        members = [m for m in zf.namelist() if not m.endswith("/")]
        bad = [m for m in members if not _allowed(name, m)]
        if bad:
            raise DownloadFailed(f"「{label(name)}」模块包里有不该有的文件（{bad[0]}），没有安装。")
        for m in members:
            target = ROOT / m
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(m))
            if m.endswith(".sh"):
                target.chmod(0o755)


def download(name: str, log=print) -> None:
    file = (_manifest()["modules"].get(name) or {}).get("file")
    if not file:
        raise DownloadFailed(f"下载清单里没有「{label(name)}」模块。")
    errors = []
    for url in _urls(name):
        log(f"… 正在下载「{label(name)}」模块：{url}")
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                install_zip(name, r.read())
            return
        except DownloadFailed:
            raise
        except Exception as e:   # 网络问题：换下一个地址
            errors.append(f"{url}：{e}")
    manual = "；".join(_urls(name)[-2:])
    raise DownloadFailed(f"「{label(name)}」模块下载不了（{errors[-1] if errors else '没有下载地址'}）。\n"
                         f"  可以在浏览器里下载 {file}（{manual}），然后运行：{cmd(f'modules install {name} <下载的文件>')}\n"
                         "  如果是在 AI 助手（如 Codex）的终端里运行的，它的沙箱可能不让联网：改用 MCP，或在你自己打开的终端里运行。")


# ---------- 开关 ----------

def enable(names: list[str], log=print) -> list[str]:
    """打开这些模块，没装的先下载装上。"""
    for n in _check(names):
        if n not in installed():
            download(n, log)
    chosen = _read_choice()
    if chosen is not None:
        _save(chosen + names)
    return enabled()


def choose(names: list[str], log=print) -> list[str]:
    """只打开这几个（tb mcp install --only 用），没装的先下载。"""
    if not _check(names):
        raise ValueError("至少要打开一个模块。")
    enable(names, log)
    _save(names)
    return enabled()


def disable(names: list[str]) -> list[str]:
    _check(names)
    left = [n for n in enabled() if n not in names]
    if not left:
        raise ValueError("至少要留一个模块打开。")
    _save(left)
    return enabled()


def cmd(args: str) -> str:
    """给用户看的命令：包里没有 tb 这个命令，用包里的启动脚本。"""
    return f"scripts/tb.sh {args}（Windows：scripts\\tb.cmd {args}）"


def not_enabled_hint(name: str) -> str:
    how = "会自动下载装上" if name not in installed() else "它已经装着，只是关掉了"
    return (f"「{label(name)}」模块还没打开。要用的话运行：{cmd('modules enable ' + name)}（{how}），"
            "AI 助手里要完全退出再打开才能看到它的工具。")


def main(argv: list[str]) -> int:
    import sys
    action, names = (argv[0] if argv else "list"), argv[1:]
    log = lambda m: print(m, file=sys.stderr)
    try:
        if action == "enable" and names:
            enable(names, log)
            print(f"✅ 已打开：{'、'.join(label(n) for n in names)}。在 AI 助手里用的话，完全退出再打开一次。")
        elif action == "disable" and names:
            disable(names)
            print(f"✅ 已关闭：{'、'.join(label(n) for n in names)}（没有删除，随时可以再打开）。")
        elif action == "install" and len(names) == 2 and names[0] in PLATFORMS:
            install_zip(names[0], Path(names[1]).expanduser().read_bytes())
            enable([names[0]], log)
            print(f"✅ 已装上并打开：{label(names[0])}。")
        elif action != "list":
            print("用法：scripts/tb.sh modules [list]  |  modules enable <模块...>  |  modules disable <模块...>"
                  "  |  modules install <模块> <模块包文件>", file=sys.stderr)
            return 2
    except (ValueError, DownloadFailed, OSError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    on, have, ok = enabled(), installed(), offered()
    print("全部工具（打开的才能用；没装的打开时会自动下载）：")
    for n in ok:
        state = "✅ 已打开" if n in on else ("⏸ 已关掉" if n in have else "⬇ 没装  ")
        print(f"  {state}  {n:<8} {ABOUT.get(n, '')}")
    if len(on) < len(ok):
        print("打开：" + cmd(f"modules enable {next(n for n in ok if n not in on)}"))
    return 0
