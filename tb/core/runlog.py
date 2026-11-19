"""运行日志：每次运行 tb，往本机追加几行记录；出了问题导出一个包发给开发者，按记录定位原因。

记在 <整台电脑共用的目录>/logs/<日期>.jsonl（paths.machine_root），一行一件事，同一次运行的行带同一个 run 编号，保留 14 天：
  start   命令、版本、系统
  connect 取数方式、插件版本、浏览器
  account 这条命令换成 / 认定的账号
  req     每个请求：接口、参数（令牌类去掉）、状态码、耗时、字节数、重试次数、插件报的当时登录的账号和发射台页面
  shop    回包里认出的店铺编号
  error   出过的错（类型、阶段、提示）；崩溃时带堆栈
  say     打在终端里的过程信息（stderr；stdout 是数据，不记）
  end     退出码、耗时、请求数
不记 cookie、令牌、回包内容（经营数据不出这台电脑）。

tb log           看最近几次运行
tb log export    把最近 7 天的命令行日志 + 插件日志 + 环境信息打成 zip，放桌面
"""
from __future__ import annotations

import argparse
import json
import os
import platform as _platform
import re
import sys
import time
import traceback
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .paths import machine_root, state_root

KEEP_DAYS = 14
SECRET = re.compile(r"token|sign|csrf|xsrf|_m_h5_tk|cookie|password|passwd|secret", re.I)
MAX_VALUE = 200

_run: dict[str, Any] | None = None


def folder() -> Path:
    """整台电脑一份：几份工具、几个 AI 助手跑的命令都记在这里，导出时一次拿全。"""
    return machine_root() / "logs"


def _clean(value: Any) -> Any:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= MAX_VALUE else text[:MAX_VALUE] + f"…（共 {len(text)} 字）"


def clean_params(params: dict | None) -> dict:
    """请求参数去掉令牌类（名字带 token / sign / csrf 等的只记「有」），太长的截断。"""
    return {k: ("（已去掉）" if SECRET.search(str(k)) else _clean(v)) for k, v in (params or {}).items()}


def clean_url(url: str) -> str:
    """只留域名和路径：参数另外按 clean_params 记。"""
    return url.split("?", 1)[0]


def version() -> str:
    """包的版本：打包时写进 SKILL.md 开头的 version:；开发目录里没有就报 dev。"""
    skill = Path(__file__).resolve().parents[2] / "SKILL.md"
    try:
        m = re.search(r'(?m)^version:\s*"?([^"\n]+)"?', skill.read_text(encoding="utf-8"))
    except OSError:
        m = None
    return m.group(1).strip() if m else "dev"


def _write(row: dict) -> None:
    try:
        folder().mkdir(parents=True, exist_ok=True)
        with open(folder() / f"{datetime.now():%Y-%m-%d}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass   # 日志写不进去不能影响取数


def _prune() -> None:
    cut = (datetime.now() - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    try:
        for f in folder().glob("*.jsonl"):
            if f.stem < cut:
                f.unlink()
    except OSError:
        pass


class _Tee:
    """stderr 照常打到终端，同时一行行记进日志。"""

    def __init__(self, stream):
        self.stream, self._buf = stream, ""

    def write(self, s):
        n = self.stream.write(s)
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                event("say", text=_clean(line.strip()))
        return n

    def flush(self):
        self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def begin(argv: list[str]) -> None:
    """一次运行开始：记下命令和环境，接管 stderr。"""
    global _run
    _run = {"id": uuid.uuid4().hex[:8], "t0": time.time(), "requests": 0}
    _prune()
    event("start", argv=[_clean(a) for a in argv], version=version(), python=_platform.python_version(),
          os=f"{_platform.system()} {_platform.release()}", pid=os.getpid())
    if not isinstance(sys.stderr, _Tee):
        sys.stderr = _Tee(sys.stderr)


def event(kind: str, **fields) -> None:
    if _run is None:
        return   # 不是从 tb 总入口跑的（如单元测试直接调平台函数）：不记
    if kind == "req":
        _run["requests"] += 1
    _write({"t": datetime.now().isoformat(timespec="milliseconds"), "run": _run["id"], "kind": kind, **fields})


def failure(exc: BaseException) -> None:
    """崩溃（不是工具自己报的错）：记下堆栈的最后几层。"""
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    event("error", type=type(exc).__name__, message=_clean(str(exc)), trace="".join(tb[-6:])[-3000:])


def finish(code: int) -> None:
    global _run
    if _run is None:
        return
    event("end", code=code, seconds=round(time.time() - _run["t0"], 2), requests=_run["requests"])
    if isinstance(sys.stderr, _Tee):
        sys.stderr.flush()
        sys.stderr = sys.stderr.stream
    _run = None


# ---------------- tb log ----------------

def _rows(days: int) -> list[dict]:
    cut = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    out = []
    for f in sorted(folder().glob("*.jsonl")) if folder().exists() else []:
        if f.stem < cut:
            continue
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def runs(rows: list[dict]) -> list[dict]:
    """按 run 编号归成一次次运行：命令、开始时间、退出码、请求数、账号、店铺、第一个错误。"""
    by: dict[str, dict] = {}
    for r in rows:
        x = by.setdefault(r.get("run", "?"), {"run": r.get("run"), "t": r.get("t"), "argv": [], "code": None,
                                              "requests": 0, "accounts": [], "shops": [], "jumps": 0, "instances": [], "error": ""})
        k = r.get("kind")
        if k == "start":
            x["argv"] = r.get("argv") or []
        elif k == "end":
            x["code"], x["requests"] = r.get("code"), r.get("requests", 0)
        elif k == "req":
            nick = ((r.get("who") or {}).get("nick")) or ""
            if nick and nick not in x["accounts"]:
                x["accounts"].append(nick)
            if r.get("instance") and r["instance"] not in x["instances"]:
                x["instances"].append(r["instance"])
        elif k == "account":
            if r.get("nick") and r["nick"] not in x["accounts"]:
                x["accounts"].append(r["nick"])
        elif k == "shop":
            if r.get("shop") not in x["shops"]:
                x["shops"].append(r.get("shop"))
        elif k == "shop_jump":
            x["jumps"] += 1
        elif k == "error" and not x["error"]:
            x["error"] = r.get("message", "")
    return list(by.values())


def cmd_list(args) -> int:
    rows = runs(_rows(args.days))[-args.limit:]
    if not rows:
        print("最近没有运行记录。")
        return 0
    for x in rows:
        code = "未结束或已中断" if x["code"] is None else ("成功" if x["code"] == 0 else f"失败（{x['code']}）")
        extra = "".join([f"  账号：{'、'.join(x['accounts'])}" if x["accounts"] else "",
                         f"  店铺：{'、'.join(map(str, x['shops']))}" if x["shops"] else "",
                         f"  请求 {x['requests']} 次" if x["requests"] else "",
                         f"  返回其他店铺 {x['jumps']} 次" if x["jumps"] else "",
                         f"  ⚠️ 由 {len(x['instances'])} 个取数桥插件处理" if len(x["instances"]) > 1 else ""])
        print(f"{(x['t'] or '?')[5:19].replace('T', ' ')}  [{x['run']}]  tb {' '.join(x['argv'])}  {code}{extra}")
        if x["error"]:
            print(f"    错误：{x['error'].splitlines()[0][:150]}")
    print(f"\n日志位置：{folder()}。遇到问题时，请运行 tb log export，并将生成的 zip 文件发送给开发者。")
    return 0


def _plugin_journal() -> tuple[dict | None, str]:
    """向浏览器插件要它的本地日志（任务、账号操作）和存了哪些账号（只有名字、昵称、编号）。连不上就说明原因。"""
    from . import accounts, bridge, transport
    try:
        server = bridge.BridgeServer(accounts.ACCOUNT)
    except bridge.BridgeError as e:
        return None, str(e)
    server.start()
    try:
        if not transport._wait_for_extension(server, 30):
            return None, "30 秒内未能连接取数桥插件（Chrome 未打开，或插件未安装、已停用）"
        res = server.submit({"journal": True}, 30)
        if res.get("error"):
            return None, str(res["error"])
        res.pop("id", None)
        return {"extension_version": server.extension_version, **res}, ""
    except bridge.BridgeError as e:
        return None, str(e)
    finally:
        server.stop()


def _environment() -> dict:
    from . import extension
    try:
        installs = extension.find_installed()
        ok, note = extension.status(installs)
        found = [vars(x) for x in installs]
    except Exception as e:   # 环境信息拿不全也要把日志导出来
        found, ok, note = [], False, f"查不了：{e}"
    return {"time": datetime.now().isoformat(timespec="seconds"), "version": version(),
            "python": sys.version, "os": _platform.platform(), "state_root": str(state_root()),
            "machine_root": str(machine_root()), "tool_folder": str(Path(__file__).resolve().parents[2]),
            "plugin_installs": found, "plugin_status": {"ok": ok, "note": note},
            "env": {k: v for k, v in os.environ.items() if re.match(r"^(TB|SYCM|ALIMAMA|QIANNIU|DMP|VOC)_", k) and not SECRET.search(k)}}


def _desktop() -> Path:
    for p in (Path.home() / "Desktop", Path.home() / "桌面"):
        if p.is_dir():
            return p
    return Path.cwd()


def cmd_export(args) -> int:
    import zipfile
    journal, why = _plugin_journal()
    dest = Path(args.out).expanduser() if args.out else _desktop()
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"店铺数据工具-日志-{datetime.now():%Y%m%d-%H%M%S}.zip"
    cut = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(folder().glob("*.jsonl")) if folder().exists() else []:
            if f.stem >= cut:
                z.write(f, f"命令行日志/{f.name}")
        z.writestr("插件日志.json", json.dumps(journal if journal else {"未获取": why}, ensure_ascii=False, indent=1))
        z.writestr("环境.json", json.dumps(_environment(), ensure_ascii=False, indent=1, default=str))
    print(f"✅ 日志已导出：{path}")
    if not journal:
        print(f"   ⚠️ 未能获取插件日志（{why}），仅导出了命令行日志。", file=sys.stderr)
    print("   请将该文件发送给开发者。文件包含命令记录、错误信息、账号昵称和店铺编号，不包含密码、登录信息和经营数据。")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="tb log", description="运行日志：查看最近几次运行，或导出日志供开发者排查问题。")
    sp = ap.add_subparsers(dest="cmd")
    ls = sp.add_parser("list", help="查看最近几次运行（默认）")
    ls.add_argument("--days", type=int, default=3)
    ls.add_argument("--limit", type=int, default=20)
    ex = sp.add_parser("export", help="将日志打包为 zip 文件（默认保存到桌面），用于发送给开发者")
    ex.add_argument("--days", type=int, default=7)
    ex.add_argument("--out", help="保存位置（默认为桌面）")
    if not argv or argv[0].startswith("-") and argv[0] not in ("-h", "--help"):
        argv = ["list", *argv]   # tb log --days 1 = tb log list --days 1
    args = ap.parse_args(argv)
    return cmd_export(args) if args.cmd == "export" else cmd_list(args)
