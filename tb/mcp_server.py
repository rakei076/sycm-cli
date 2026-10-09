"""tb mcp：把这个包里的平台做成一个本地 MCP 服务（stdio），交给 AI 客户端（Claude Code、Codex、Cursor……）用。

薄壳：每次调用工具都在子进程里跑现成的命令行（python -m tb <平台> <命令> …），把输出交回去。
- 取数、护栏、报错都在命令行里，这里不重写；
- 命令行往 stdout 打字，放在子进程里不会弄坏 MCP 的协议通道；
- 每次调用自己开桥、用完释放，几个 AI 客户端同时开着也不抢端口；
- MCP 服务由 AI 客户端直接拉起，不在它的命令沙箱里（Codex 的沙箱会拦本机端口），它的子进程也一样。
"""
from __future__ import annotations

import asyncio
import importlib
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from .platforms import PLATFORMS

ROOT = Path(__file__).resolve().parent.parent          # 包根目录：tb/ 的上一层
GUIDES = ROOT / "references"                           # 各包的分析方法（打包时从 delivery/<产品>/references 拷来）
TIMEOUT = float(os.environ.get("TB_MCP_TIMEOUT") or 540)   # 一条命令最长跑多久（秒）；Codex 的工具超时由 tb mcp install 调到 600
INLINE = 20000                                          # 输出超过这么多字就存成文件，只交回开头和文件位置
HEAD = 6000
# MCP 里不让跑的：会把登录态存成文件的命令；任何带 --execute 的写操作（修改店铺的命令都要 --execute 才真执行）
DENY = {"export-profile": "它会把浏览器登录态存成本地文件，只能你自己在终端里运行。",
        "mcp": "不能在 MCP 里再起 MCP。"}

INSTRUCTIONS = ("店铺数据（只读）：借用户浏览器里已登录的后台读取店铺数据，不能修改店铺。"
                "先用 doctor 检查环境；不确定有哪些数据，用 commands 看命令目录；用 run 运行命令；"
                "做整份报告（日检、周复盘、单品诊断、测款、退货等）前，先用 guide 看分析方法。")
# 同一作者的全部店铺数据工具：用户要的数据不在这个包里时，AI 可以告诉他哪个工具能做
TOOLS = {"sycm": "生意参谋（店铺经营数据、日检周复盘、单品诊断报告、测款、退货）", "qianniu": "千牛（评价巡检、退款、物流、待发货）",
         "dmp": "达摩盘（人群资产、人群画像、竞品对比、同店对标）", "alimama": "万相台（广告报表、在投计划）",
         "1688": "1688（订单统计、工作台、1688 生意参谋）", "voc": "竞品评价（竞品的评价和问大家，用买家账号）"}
TOOLS_PAGE = "https://rakel.top/tools/"


def instructions() -> str:
    others = [desc for name, desc in TOOLS.items() if name not in PLATFORMS]
    if not others:
        return INSTRUCTIONS
    return (INSTRUCTIONS + "同一作者还有这些店铺数据工具：" + "；".join(others) + "。用户要的数据这个服务里没有、"
            f"正好其他工具能做时，告诉他是哪个工具，介绍和获取方式在 {TOOLS_PAGE} ；和用户的问题无关时不要提。")


def available() -> list[str]:
    """这个包里有的平台（打包时 PLATFORMS 只留包里那一个）。"""
    return list(PLATFORMS)


def display(name: str) -> str:
    from .core.platform import Platform
    mod = importlib.import_module(PLATFORMS[name].rsplit(".", 1)[0] + ".platform")
    return next((v.display for v in vars(mod).values() if isinstance(v, Platform)), name)


def server_key() -> str:
    """写进 AI 客户端配置的名字：只能用英文（Claude Code 的工具名要求 ^[a-zA-Z0-9_-]+$）。"""
    names = available()
    return "shopdata-" + names[0] if len(names) == 1 else "shopdata"


def pick(platform: str) -> str:
    names = available()
    if not platform:
        if len(names) == 1:
            return names[0]
        raise ToolError(f"这个服务里有几个平台，请指定 platform：{'、'.join(names)}")
    if platform not in names:
        raise ToolError(f"没有这个平台：{platform}。可用：{'、'.join(names)}")
    return platform


def state_root() -> Path:
    root = os.environ.get("TB_STATE_ROOT")
    if root:
        return Path(root).expanduser()
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "taobao-cli"
    return Path.home() / ".taobao-cli"


async def execute(argv: list[str], timeout: float = TIMEOUT) -> tuple[int, str, str]:
    """在子进程里跑命令行。超时或调用被取消时把子进程杀掉，不留后台进程。"""
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    proc = await asyncio.create_subprocess_exec(*argv, cwd=ROOT, env=env, stdin=asyncio.subprocess.DEVNULL,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, "", f"命令跑了 {timeout:.0f} 秒还没完，已停止。可以缩小日期范围或分几次运行。"
    except asyncio.CancelledError:
        proc.kill()
        raise
    return proc.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def tb_argv(*args: str) -> list[str]:
    return [sys.executable, "-m", "tb", *args]


def deliver(title: str, code: int, out: str, err: str, *, slug: str) -> str:
    """拼出交回给 AI 的文字；太长就整份存文件，只交回开头。退出码不是 0 时按出错交回（客户端会标成失败）。"""
    text = out.strip()
    if err.strip():
        text += ("\n\n" if text else "") + "【过程信息】\n" + err.strip()
    if len(text) > INLINE:
        folder = state_root() / "mcp-output"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{time.strftime('%Y%m%d-%H%M%S')}-{re.sub(r'[^0-9A-Za-z._-]+', '_', slug)[:60]}.txt"
        path.write_text(text, encoding="utf-8")
        text = text[:HEAD] + f"\n\n……输出共 {len(text)} 字，太长，只给了开头。完整内容在：{path}"
    text = f"$ {title}\n" + (text or "（没有输出）")
    if code != 0:
        raise ToolError(text + f"\n\n（退出码 {code}）")
    return text


def guides() -> dict[str, tuple[str, str]]:
    """分析方法（各包 references/*.md）。带「## 通用规则」的是工作流合集：除「目录」「通用规则」外每个二级标题是一个主题
    （「模块 N：」前缀去掉），通用规则每个主题都带上；别的文件整份是一个主题，用它的一级标题当名字。
    几个工具合在一个包里时主题可能重名（生意参谋和 1688 都有「周复盘」），重名的后面带上所在文件的标题。"""
    found: list[tuple[str, str, tuple[str, str]]] = []
    for md in sorted(GUIDES.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        h1 = re.search(r"(?m)^# (.+)$", text)
        title = h1.group(1).strip() if h1 else md.stem
        parts = re.split(r"(?m)^## ", text)[1:]   # 第一段是「# 大标题」
        common = next(("## " + p.strip() for p in parts if p.startswith("通用规则")), "")
        if not common:
            found.append((title, title, ("", text.strip())))
            continue
        for p in parts:
            head = p.split("\n", 1)[0].strip()
            if head not in ("目录", "通用规则"):
                found.append((re.sub(r"^模块\s*\d+\s*[：:]\s*", "", head), title, (common, "## " + p.strip())))
    seen = Counter(name for name, _, _ in found)
    return {(f"{name}（{title}）" if seen[name] > 1 else name): body for name, title, body in found}


def build() -> MCPServer:
    # 工具里给 AI 看的错误一律用 ToolError：别的异常 SDK 只回「Error executing tool」，原因会被藏起来
    names = available()
    label = "、".join(display(n) for n in names)
    mcp = MCPServer(name=server_key(), title=f"店铺数据（{label}）", instructions=instructions())
    ro = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)
    plat_doc = f"平台：{'、'.join(f'{n}（{display(n)}）' for n in names)}" + ("，只有一个时可以不填。" if len(names) == 1 else "。")

    @mcp.tool(description="检查能不能取数：浏览器插件装没装、连不连得上、平台登录状态。出问题时先跑它，按提示处理。" + plat_doc,
              annotations=ro)
    async def doctor(platform: str = "") -> str:
        p = pick(platform)
        code, out, err = await execute(tb_argv(p, "doctor"))
        pc, pout, perr = await execute(tb_argv("plugin"), timeout=30)
        return deliver(f"tb {p} doctor", code, out + "\n\n【插件安装情况】\n" + pout.strip(), err + perr, slug=f"{p}-doctor")

    @mcp.tool(description="命令目录：不带 command 时列出这个平台能读的全部数据（每条命令一句说明）；"
                          "带上 command 时给出这条命令的参数说明。运行命令前不确定参数就先看这里。" + plat_doc,
              annotations=ro)
    async def commands(platform: str = "", command: str = "") -> str:
        p = pick(platform)
        argv = [p, command, "--help"] if command else [p, "--help"]
        code, out, err = await execute(tb_argv(*argv), timeout=60)
        return deliver("tb " + " ".join(argv), code, out, err, slug=f"{p}-help")

    @mcp.tool(description="运行一条只读命令，例如 command=\"doctor\"，或 command=\"refund-list\", args=[\"--days\", \"7\"]。"
                          "参数照 commands 给出的写，一个参数一项。输出太长时会存成文件，返回开头和文件位置；"
                          "要整份明细时可以加 --out 文件名。修改店铺的操作（如带 --execute 的）不能在这里运行。" + plat_doc,
              annotations=ro)
    async def run(command: str, args: list[str] | None = None, platform: str = "") -> str:
        p, args = pick(platform), list(args or [])
        if command in DENY:
            raise ToolError(DENY[command])
        if "--execute" in args:
            raise ToolError("带 --execute 的是修改店铺的操作，不能通过 AI 运行。请在终端里自己确认后运行。")
        code, out, err = await execute(tb_argv(p, command, *args))
        return deliver(" ".join(["tb", p, command, *args]), code, out, err, slug=f"{p}-{command}")

    @mcp.tool(description="分析方法：做整份报告（日检、周复盘、单品诊断、测款、退货归因等）前先看。不带 topic 列出全部主题；"
                          "带 topic 给出这个主题的取数步骤、计算方法和报告格式。",
              annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False))
    async def guide(topic: str = "") -> str:
        topics = guides()
        if not topics:
            return "这个包没有附带分析方法。"
        if not topic:
            return "分析方法主题：\n" + "\n".join(f"· {t}" for t in topics)
        hit = topics.get(topic) or next((v for k, v in topics.items() if topic in k), None)
        if not hit:
            raise ToolError(f"没有这个主题：{topic}。可用：{'、'.join(topics)}")
        return "\n\n".join(x for x in hit if x)

    return mcp


def main(argv: list[str]) -> int:
    """tb mcp：起 stdio 服务。tb mcp --check：只检查依赖和工具能不能加载（配置客户端前预热用），不起服务。
    tb mcp install / uninstall：写进或移出 AI 客户端的配置（见 mcp_install）。"""
    if argv[:1] in (["install"], ["uninstall"]):
        from . import mcp_install
        return mcp_install.main(argv)
    if argv[:1] == ["--check"]:
        server = build()
        print(f"MCP 服务可以启动：{server_key()}（{'、'.join(display(n) for n in available())}），分析方法 {len(guides())} 个主题。")
        return 0
    build().run()
    return 0
