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
if command -v uv >/dev/null 2>&1; then
  exec uv run -q --no-project --with browser-cookie3 --with curl-cffi --with websocket-client python -m tb sycm "$@"
elif command -v python3 >/dev/null 2>&1; then
  if ! python3 -c "import browser_cookie3, curl_cffi, websocket" 2>/dev/null; then
    echo "首次运行，正在把依赖安装到本目录 .python-packages ..." >&2
    mkdir -p "$SKILL_DIR/.python-packages"
    python3 -m pip install -q --target "$SKILL_DIR/.python-packages" -r "$SKILL_DIR/requirements.txt"
    export PYTHONPATH="$SKILL_DIR:$SKILL_DIR/.python-packages"
  fi
  exec python3 -m tb sycm "$@"
else
  echo "未找到 uv 或 python3。请先安装 uv（https://docs.astral.sh/uv/）或 Python 3.10+。" >&2
  exit 1
fi
