#!/bin/bash
# sycm-cli wrapper — AI 代理友好的调用入口
# Usage: ~/.claude/skills/sycm-cli/scripts/sycm.sh <subcommand> [args...]

set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 路径 1：uv（推荐，自动管理依赖）
if command -v uv >/dev/null 2>&1; then
  exec uv run --with browser-cookie3 --with curl-cffi --with websocket-client python "$SKILL_DIR/sycm_cli.py" "$@"
fi

# 路径 2：python3 + 已装依赖
if command -v python3 >/dev/null 2>&1; then
  if python3 -c "import browser_cookie3, curl_cffi, websocket" 2>/dev/null; then
    exec python3 "$SKILL_DIR/sycm_cli.py" "$@"
  fi
  cat >&2 <<EOF
[sycm-cli] 缺 Python 依赖（browser_cookie3, curl_cffi, websocket-client）

任选一种安装方式：

  方案 A（推荐）：装 uv，自动管理虚拟环境
    curl -LsSf https://astral.sh/uv/install.sh | sh
    重开终端，再次运行此命令

  方案 B：用 pip 装到当前 Python 环境
    pip3 install --user -r "$SKILL_DIR/requirements.txt"

EOF
  exit 1
fi

cat >&2 <<EOF
[sycm-cli] 系统未安装 Python 3 或 uv

请先装 uv：
  curl -LsSf https://astral.sh/uv/install.sh | sh

重开终端后再次运行此命令。
EOF
exit 1
