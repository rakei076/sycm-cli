#!/bin/bash
# 全库敏感词扫描:词表在 .privacy-words(gitignore,永不提交)
# 用法: scripts/privacy-scan.sh   零命中=exit 0
set -u
cd "$(dirname "$0")/.."
[ -f .privacy-words ] || { echo "⚠️ 缺 .privacy-words 词表,跳过"; exit 0; }
pattern=$(grep -v '^\s*$' .privacy-words | paste -sd'|' -)
if git grep -nE "$pattern" -- . ':!.privacy-words' 2>/dev/null; then
  echo "❌ 隐私扫描命中,禁止提交/同步"; exit 1
fi
echo "✅ 隐私扫描零命中"
