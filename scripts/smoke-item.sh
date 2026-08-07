#!/bin/bash
# 商品板块冒烟测试 —— 把 19 个命令挨个跑一遍，只判「能不能跑通、有没有数」，不判数字对不对。
#
#   scripts/smoke-item.sh <商品ID> [日期 YYYY-MM-DD]
#
# 判定：
#   OK    有数据行            —— 命令活着
#   EMPTY 跑通了但一行数据都没有 —— 可疑！可能真没数据，也可能参数猜错了
#                                  （item-refund 的退款原因表就这样空了两天）
#   FAIL  报错
#   风控  立刻中止整个脚本，绝不重试
#
# 输出全落在临时目录，不进仓库。真实商品 ID 只出现在你敲的这条命令里。

set -uo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYCM="$SKILL_DIR/scripts/sycm.sh"

ITEM_ID="${1:-}"
DATE="${2:-$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d yesterday +%Y-%m-%d)}"

if [[ -z "$ITEM_ID" ]]; then
  echo "用法: $0 <商品ID> [日期 YYYY-MM-DD]" >&2
  echo "商品ID 不知道就先跑: $SYCM item-search 你的款名" >&2
  exit 1
fi

HOUR=$(date +%H)
if [[ "$HOUR" -ge 1 && "$HOUR" -lt 6 ]]; then
  echo "现在是 ${HOUR} 点，夜间 1:00-6:00 禁跑（护栏规矩）。" >&2
  exit 1
fi

OUT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/sycm-smoke-XXXXXX")"
echo "商品 ID : $ITEM_ID"
echo "日期    : $DATE"
echo "输出目录: $OUT_DIR"
echo

N_OK=0; N_EMPTY=0; N_FAIL=0
EMPTY_LIST=(); FAIL_LIST=()

run() {
  local label="$1"; shift
  local log="$OUT_DIR/${label}.txt"
  printf '%-22s ' "$label"

  "$SYCM" "$@" >"$log" 2>&1
  local rc=$?

  if [[ $rc -eq 2 ]] || grep -qE '风控|滑块|验证码|RiskTriggered' "$log"; then
    echo "🛑 风控 —— 立刻停手，今天别再跑了"
    echo
    echo "现场:"; sed -n '1,15p' "$log"
    exit 2
  fi

  if [[ $rc -ne 0 ]]; then
    echo "❌ FAIL (rc=$rc)  $log"
    sed -n '1,3p' "$log" | sed 's/^/                       /'
    N_FAIL=$((N_FAIL+1)); FAIL_LIST+=("$label")
    return
  fi

  # 数据行 = 含数字、且不是注释行。表头一般没数字，所以不另外扣。
  # 注意别写成 -le 1：只有一个商品集时 spu-list 正好 1 行，会被误判成空表。
  local rows
  rows=$(grep -vE '^\s*(#|$)' "$log" | grep -cE '[0-9]' || true)
  if [[ "$rows" -lt 1 ]]; then
    echo "⚠️  EMPTY (跑通但没数据)  $log"
    N_EMPTY=$((N_EMPTY+1)); EMPTY_LIST+=("$label")
  else
    echo "✅ OK   ${rows} 行"
    N_OK=$((N_OK+1))
  fi
}

echo "── 单品级（阶段 1 + 2，共 13 个）──"
run item-360          item-360          --item-id "$ITEM_ID" --date "$DATE"
run item-sku-list     item-sku-list     --item-id "$ITEM_ID" --date "$DATE"
run item-sku-by-size  item-sku-list     --item-id "$ITEM_ID" --date "$DATE" --by 尺码
run item-flow-source  item-flow-source  --item-id "$ITEM_ID" --date "$DATE"
run item-refund       item-refund       --item-id "$ITEM_ID" --date "$DATE"
run item-detail       item-detail       --item-id "$ITEM_ID" --date "$DATE"
run item-price        item-price        --item-id "$ITEM_ID" --date "$DATE"
run item-title        item-title        --item-id "$ITEM_ID" --date "$DATE"
run item-content      item-content      --item-id "$ITEM_ID" --date "$DATE"
run item-service      item-service      --item-id "$ITEM_ID" --date "$DATE"
run item-bundle       item-bundle       --item-id "$ITEM_ID" --date "$DATE"
run item-profile      item-profile      --item-id "$ITEM_ID" --date "$DATE"
run item-loss-risk    item-loss-risk    --item-id "$ITEM_ID" --date "$DATE"

echo
echo "── 店铺级（阶段 3 + 4，共 6 个）──"
run spu-list          spu-list          --date "$DATE"
# 连带分析单日必挂（服务端 code=1002 4004:），给它 7 天窗口
WEEK_AGO="$(date -v-6d -j -f %Y-%m-%d "$DATE" +%Y-%m-%d 2>/dev/null \
            || date -d "$DATE -6 days" +%Y-%m-%d)"
run item-relate       item-relate       --date "$WEEK_AGO" --end-date "$DATE"
run video-list        video-list        --date "$DATE"
run macro-monitor     macro-monitor
run problem-alarm     problem-alarm
run interval-analysis interval-analysis --date "$DATE"

echo
echo "════════════════════════════════════════"
echo "OK ${N_OK} ｜ EMPTY ${N_EMPTY} ｜ FAIL ${N_FAIL}"
[[ ${#EMPTY_LIST[@]} -gt 0 ]] && echo "空表: ${EMPTY_LIST[*]}"
[[ ${#FAIL_LIST[@]}  -gt 0 ]] && echo "报错: ${FAIL_LIST[*]}"
echo
echo "全部输出: $OUT_DIR"
echo
echo "⚠️  EMPTY 不等于「没问题」。页面上那块要是有数，就是我参数猜错了 —— 请把命令名告诉我。"

[[ $N_FAIL -gt 0 ]] && exit 1
exit 0
