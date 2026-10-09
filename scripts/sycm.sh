#!/bin/bash
# sycm-cli 入口（macOS / Linux / Windows Git Bash）
# 用法：scripts/sycm.sh <子命令> [参数...]   例：scripts/sycm.sh doctor
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$SKILL_DIR${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
# 第三方库 wmi（Windows 上 browser-cookie3 带进来的）会打印 SyntaxWarning
export PYTHONWARNINGS="ignore::SyntaxWarning"
case "$(uname -s 2>/dev/null || true)" in
  MINGW*|MSYS*|CYGWIN*)
    winpath() { command -v cygpath >/dev/null 2>&1 && cygpath -w "$1" || printf '%s' "$1"; }
    export TB_STATE_ROOT="$(winpath "$SKILL_DIR/.runtime")"
    export PYTHONPATH="$(winpath "$SKILL_DIR");$(winpath "$SKILL_DIR/.python-packages")"
    ;;
esac
cd "$SKILL_DIR"
# 从 AI 客户端（Claude Desktop 等图形界面程序）启动时 PATH 很短：uv 常装在这些地方
if ! command -v uv >/dev/null 2>&1; then
  for d in "$HOME/.local/bin" "$HOME/.cargo/bin" /opt/homebrew/bin /usr/local/bin; do
    if [ -x "$d/uv" ]; then export PATH="$d:$PATH"; break; fi
  done
fi
NET_HINT="如果这条命令是在 AI 助手（如 Codex）里运行的：它的沙箱默认不让联网、也不让开本机端口。请改用 MCP：在你自己打开的终端里运行一次 mcp install（例如 scripts/<工具>.sh mcp install，Windows 用 scripts\\<工具>.cmd mcp install），完全退出并重开 Codex，之后让它通过 MCP 取数；也可以直接在你自己打开的终端里运行这条命令。"
DEPS=(--with browser-cookie3 --with curl-cffi --with websocket-client --with "mcp~=2.3" --with openpyxl --with pillow --with jinja2)
if command -v uv >/dev/null 2>&1; then
  # 依赖没装好（第一次运行）：先单独下载，失败时说清原因，别让人对着 uv 的网络报错发愣
  if ! uv run -q --no-project --offline "${DEPS[@]}" python -c "" >/dev/null 2>&1; then
    echo "首次运行：正在下载依赖（需要联网，约 1 分钟，只需一次）..." >&2
    if ! uv run -q --no-project "${DEPS[@]}" python -c ""; then
      echo "依赖下载失败：这台电脑现在连不上 Python 软件源（pypi.org）。" >&2
      echo "$NET_HINT" >&2
      exit 1
    fi
  fi
  exec uv run -q --no-project "${DEPS[@]}" python -m tb sycm "$@"
elif command -v python3 >/dev/null 2>&1; then
  if ! python3 -c "import browser_cookie3, curl_cffi, websocket, mcp, openpyxl, PIL, jinja2" 2>/dev/null; then
    echo "首次运行，正在把依赖安装到本目录 .python-packages ..." >&2
    mkdir -p "$SKILL_DIR/.python-packages"
    if ! python3 -m pip install -q --target "$SKILL_DIR/.python-packages" -r "$SKILL_DIR/requirements.txt"; then
      echo "依赖安装失败：这台电脑现在连不上 Python 软件源（pypi.org）。" >&2
      echo "$NET_HINT" >&2
      exit 1
    fi
    export PYTHONPATH="$SKILL_DIR:$SKILL_DIR/.python-packages"
  fi
  exec python3 -m tb sycm "$@"
else
  echo "未找到 uv 或 python3。请先安装 uv（https://docs.astral.sh/uv/）或 Python 3.10+。" >&2
  exit 1
fi
