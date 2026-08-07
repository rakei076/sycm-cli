#!/bin/bash
# 全库敏感词扫描:词表在 .privacy-words(gitignore,永不提交)
# 用法: scripts/privacy-scan.sh   零命中=exit 0
set -u
cd "$(dirname "$0")/.."
[ -f .privacy-words ] || { echo "⚠️ 缺 .privacy-words 词表,跳过"; exit 0; }
rc=0

# 1) 词表命中(店名等)
pattern=$(grep -v '^\s*$' .privacy-words | paste -sd'|' -)
if git grep -nE "$pattern" -- . ':!.privacy-words' 2>/dev/null; then
  echo "❌ 敏感词命中"; rc=1
fi

# 2) 真实商品ID / userId：12 位以上纯数字。占位符 123456789 是 9 位,天然不命中。
#    2026-08-07 加:原来只查店名,真实商品ID全靠人自觉,漏一个就进公开库了。
if git grep -nEo '\b[0-9]{12,}\b' -- . ':!.privacy-words' 2>/dev/null | grep -v '123456789'; then
  echo "❌ 疑似真实商品ID/userId(12位以上数字)。文档与测试一律用占位 123456789"; rc=1
fi

# 3) 运行时数据文件不该被跟踪
if git ls-files | grep -iE '\.(xlsx|har|csv)$|^(out|data|runtime)/'; then
  echo "❌ 运行时数据文件进了 git"; rc=1
fi

[ "$rc" -eq 0 ] && echo "✅ 隐私扫描零命中"
exit "$rc"
