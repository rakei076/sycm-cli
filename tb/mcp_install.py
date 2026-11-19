"""tb mcp install / uninstall：把本包的 MCP 服务写进常见 AI 客户端的配置（Claude Code、Codex、Cursor、Claude Desktop）。

每个客户端都指向包里的启动脚本（scripts/<命令>.sh 或 .cmd）+ 参数 mcp；启动脚本自己找 uv / Python、装依赖。
只改本服务这一项：别的服务、别的设置原样保留。装之前先在终端里把服务起一次（--check），依赖提前装好，
免得客户端第一次启动时边下载边超时（Codex 默认只等 10 秒）。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .mcp_server import ROOT, server_key
from .platforms import PLATFORMS

IS_WIN = os.name == "nt"
# Codex 只把白名单里的环境变量传给 MCP 服务；这些是 uv 下载依赖、走代理时要用的，有就带过去
PASS_ENV = ["UV_DEFAULT_INDEX", "UV_INDEX_URL", "UV_PYTHON_INSTALL_MIRROR", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
            "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"]
CLIENTS = ("claude-code", "codex", "cursor", "claude-desktop")


# 以前每个单独包各写一个 shopdata-<工具>；现在都是 shopdata，安装时顺手删掉旧的，免得同一个服务出现两次
OLD_KEYS = [f"shopdata-{n}" for n in PLATFORMS]


def launcher() -> Path:
    """包里的启动脚本 scripts/tb.sh|.cmd。"""
    p = ROOT / "scripts" / f"tb{'.cmd' if IS_WIN else '.sh'}"
    if not p.exists():
        raise SystemExit(f"找不到启动脚本 {p}")
    return p


def command(script: Path) -> tuple[str, list[str]]:
    """Node 写的客户端（Claude Code、Cursor、Claude Desktop）在 Windows 上不能直接起 .cmd，要套 cmd /c。"""
    return ("cmd", ["/c", str(script), "mcp"]) if IS_WIN else (str(script), ["mcp"])


# ---------- Codex：~/.codex/config.toml ----------

def codex_path(home: Path) -> Path:
    return Path(os.environ.get("CODEX_HOME") or home / ".codex") / "config.toml"


def _drop_toml_table(text: str, key: str) -> str:
    """去掉 [mcp_servers.<key>] 这张表（连同它的子表），其余原样保留。"""
    head = re.compile(r'^\s*\[\s*mcp_servers\s*\.\s*(?:"%s"|%s)\s*(?:\.[^\]]*)?\]\s*$' % (re.escape(key), re.escape(key)))
    out, skipping = [], False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("["):
            skipping = bool(head.match(line))
        if not skipping:
            out.append(line)
    return "".join(out)


def codex_install(home: Path, key: str, script: Path) -> Path:
    path = codex_path(home)
    text = _drop_toml_table(path.read_text(encoding="utf-8") if path.exists() else "", key).rstrip()
    block = (f"[mcp_servers.{key}]\n"
             f"command = {json.dumps(str(script), ensure_ascii=False)}\n"   # JSON 字符串就是合法的 TOML 基本字符串
             f'args = ["mcp"]\n'
             f"startup_timeout_sec = 120\n"
             f"tool_timeout_sec = 600\n"
             f'env = {{ PYTHONUTF8 = "1" }}\n'
             f"env_vars = {json.dumps(PASS_ENV)}\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((text + "\n\n" if text else "") + block, encoding="utf-8")
    return path


def codex_uninstall(home: Path, key: str) -> Path | None:
    path = codex_path(home)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    new = _drop_toml_table(text, key)
    if new == text:
        return None
    path.write_text(new.rstrip() + "\n" if new.strip() else "", encoding="utf-8")
    return path


# ---------- Cursor、Claude Desktop：JSON 里的 mcpServers ----------

def json_paths(client: str, home: Path) -> list[Path]:
    if client == "cursor":
        return [home / ".cursor" / "mcp.json"]
    if sys.platform == "darwin":
        return [home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"]
    if IS_WIN:
        appdata = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
        local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
        # 商店（MSIX）装的 Claude Desktop 实际读的是这一份；设置里「Edit Config」打开的是 APPDATA 那份
        return [appdata / "Claude" / "claude_desktop_config.json",
                local / "Packages" / "Claude_pzs8sxrjxfjjc" / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json"]
    return [home / ".config" / "Claude" / "claude_desktop_config.json"]


def json_install(path: Path, key: str, cmd: str, args: list[str]) -> Path:
    data = json.loads(path.read_text(encoding="utf-8") or "{}") if path.exists() else {}
    data.setdefault("mcpServers", {})[key] = {"command": cmd, "args": args, "env": {"PYTHONUTF8": "1"}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def json_uninstall(path: Path, key: str) -> Path | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8") or "{}")
    if key not in data.get("mcpServers", {}):
        return None
    del data["mcpServers"][key]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


# ---------- Claude Code：用它自己的命令行 ----------

def claude_code(args: list[str]) -> subprocess.CompletedProcess | None:
    exe = shutil.which("claude")
    if not exe:
        return None
    return subprocess.run([exe, "mcp", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")


# ---------- 入口 ----------

def detected(client: str, home: Path) -> bool:
    """这台电脑上有没有这个客户端（只给装了的写配置）。"""
    if client == "claude-code":
        return shutil.which("claude") is not None
    if client == "codex":
        return shutil.which("codex") is not None or codex_path(home).parent.exists()
    if client == "cursor":
        return (home / ".cursor").exists()
    return any(p.parent.exists() for p in json_paths("claude-desktop", home))


def install(clients: list[str], home: Path, script: Path) -> list[str]:
    key, (cmd, args) = server_key(), command(script)
    done = []
    for old in OLD_KEYS:
        remove_key(clients, home, old)
    for c in clients:
        if c == "claude-code":
            claude_code(["remove", "-s", "user", key])
            r = claude_code(["add", "-s", "user", key, "--", cmd, *args])
            done.append(f"Claude Code：{'已添加（用户级，所有项目可用）' if r and r.returncode == 0 else '没加上：' + ((r.stderr or r.stdout).strip() if r else '找不到 claude 命令')}")
        elif c == "codex":
            done.append(f"Codex：已写入 {codex_install(home, key, script)}")
        else:
            paths = [p for p in json_paths(c, home) if c == "cursor" or p.parent.exists()]
            done += [f"{'Cursor' if c == 'cursor' else 'Claude Desktop'}：已写入 {json_install(p, key, cmd, args)}" for p in paths]
    return done


def remove_key(clients: list[str], home: Path, key: str) -> list[str]:
    done = []
    for c in clients:
        if c == "claude-code":
            r = claude_code(["remove", "-s", "user", key])
            if r and r.returncode == 0:
                done.append("Claude Code：已移除")
        elif c == "codex":
            p = codex_uninstall(home, key)
            if p:
                done.append(f"Codex：已从 {p} 移除")
        else:
            done += [f"已从 {p} 移除" for p in (json_uninstall(x, key) for x in json_paths(c, home)) if p]
    return done


def uninstall(clients: list[str], home: Path) -> list[str]:
    return remove_key(clients, home, server_key())


def main(argv: list[str], home: Path | None = None) -> int:
    home = home or Path.home()
    action = argv[0] if argv else ""
    if action not in ("install", "uninstall"):
        print("用法：tb mcp install [客户端…] [--only 模块,模块]   把本包的 MCP 服务写进 AI 客户端的配置（不写客户端 = 本机装了的都配；"
              "--only 只打开这几个工具，如 --only sycm,alimama）\n"
              "      tb mcp uninstall [客户端…] 移除\n客户端：" + "、".join(CLIENTS))
        return 0 if not action else 1
    rest = list(argv[1:])
    if "--only" in rest:
        i = rest.index("--only")
        names = [n.strip() for n in (rest[i + 1] if i + 1 < len(rest) else "").split(",") if n.strip()]
        del rest[i:i + 2]
        from .core import modules
        try:
            print("只打开：" + "、".join(modules.choose(names)), file=sys.stderr)
        except ValueError as e:
            print(f"❌ {e}", file=sys.stderr)
            return 1
    wanted = [a for a in rest if not a.startswith("-")]
    bad = [a for a in wanted if a not in CLIENTS]
    if bad:
        print(f"不认识的客户端：{'、'.join(bad)}。可选：{'、'.join(CLIENTS)}", file=sys.stderr)
        return 1
    clients = wanted or [c for c in CLIENTS if detected(c, home)]
    if action == "uninstall":
        lines = uninstall(clients, home)
        print("\n".join(lines) or "没有找到要移除的配置。")
        return 0
    if not clients:
        print("这台电脑上没找到 Claude Code、Codex、Cursor 或 Claude Desktop。装好其中一个后再运行；"
              "也可以指定客户端，例如：tb mcp install codex", file=sys.stderr)
        return 1
    script = launcher()
    print(f"先把服务起一次（第一次要下载依赖，可能要一两分钟）：{script} mcp --check", file=sys.stderr)
    cmd, args = command(script)
    r = subprocess.run([cmd, *args, "--check"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("服务起不来，先解决这个再配置客户端：\n" + (r.stderr or r.stdout).strip()[-2000:], file=sys.stderr)
        return 1
    print(r.stdout.strip())
    for line in install(clients, home, script):
        print("· " + line)
    from .core import modules
    print(f"完成。重新打开 AI 客户端后，就能看到「{server_key()}」，已打开的工具：{'、'.join(modules.enabled())}。"
          "要用别的工具：scripts/tb.sh modules enable <模块>。移除：scripts/tb.sh mcp uninstall")
    return 0
