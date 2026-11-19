"""sycm item-report：单品诊断报告。三步：取数存 data.json → AI 按分析指南写 analysis.json → 生成单文件网页。

七页：诊断总览、趋势图表、同店对标、下滑归因、45 天方案、目标模拟器、数据缺口（照客户样板的排版和写法）。
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from ....core.errors import TbError

GUIDE = "references/item-report-guide.md"


def register(subparsers: Any, yesterday: str) -> None:
    p = subparsers.add_parser("item-report", help="单品诊断报告：先取数，AI 写分析后出网页（定性、首末对比、同店对标、下滑归因、45 天方案、模拟器）")
    p.add_argument("--item-id", help="商品 ID（当前登录店铺的商品）")
    p.add_argument("--search", help="按货号/标题关键词找商品（命中唯一才继续）")
    p.add_argument("--days", type=int, choices=(7, 15, 30), default=7,
                   help="看最近 2×N 天，前 N 天和后 N 天比（默认 7：最近 14 天）")
    p.add_argument("--end", default=yesterday, help="分析周期的最后一天 YYYY-MM-DD（默认昨天）")
    p.add_argument("--compete", help="达摩盘竞品对比文件（dmp compete-item --out 存的 JSON），放进数据文件给 AI 写归因用")
    p.add_argument("--out", default="reports", help="数据和报告的输出目录（默认 reports/）")
    p.add_argument("--analysis", help="AI 写好的分析文件；给了就直接生成网页")
    p.add_argument("--data", help="数据文件（默认和分析文件同名的 .data.json）")
    p.add_argument("--mask", action="store_true", help="生成脱敏版：隐去商品和店铺身份，金额、访客等折成指数（发给别人看用）")
    p.add_argument("--track", action="store_true",
                   help="执行跟踪（周复盘）：配 --analysis，从方案 D1 起逐天拿实际数和每日门槛比，出一份填好实际数的跟踪表")
    p.set_defaults(func=cmd_item_report)


def load_compete(path: str, item_id: str) -> dict[str, Any]:
    """达摩盘 compete-item --out 存的是 {摘要, 原始}；只要摘要。本品得是这次的商品。"""
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise TbError(f"找不到竞品对比文件 {path}。", stage="读取竞品对比") from None
    except json.JSONDecodeError as ex:
        raise TbError(f"竞品对比文件 {path} 不是合法的 JSON（第 {ex.lineno} 行）。", stage="读取竞品对比") from None
    summary = obj.get("摘要", obj) if isinstance(obj, dict) else None
    if not isinstance(summary, dict) or "本品" not in summary or "竞品" not in summary:
        raise TbError(f"{path} 不是达摩盘竞品对比的文件。", stage="读取竞品对比",
                      hint="用 dmp compete-item --item 本品ID --rival 竞品ID --out 文件.json 生成。")
    if str(summary["本品"]) != str(item_id):
        raise TbError(f"竞品对比文件里的本品是 {summary['本品']}，和这次要诊断的 {item_id} 不是同一个商品。", stage="读取竞品对比")
    return summary


def cmd_item_report(args: argparse.Namespace) -> None:
    if args.track:
        if not args.analysis:
            raise TbError("--track 要配 --analysis <分析文件>：用里面的 45 天方案当对照。")
        from . import track
        from .render import load_pair
        data, analysis, d_path = load_pair(args.analysis, args.data)
        t = track.run(data, analysis)
        out = track.write_xlsx(t, d_path.with_name(d_path.name.replace(".data.json", f"-track-{t['through']}.xlsx")))
        print(track.render_text(t))
        print(f"\n填好实际数的执行跟踪表：{out}")
        return
    if args.analysis:
        from .render import write_html
        print(f"报告已生成：{write_html(args.analysis, args.data, mask=args.mask)}")
        return
    from ..cli import load_taobao_cookies
    from ..item import resolve_item_id
    from .collect import collect
    try:
        end = date.fromisoformat(args.end)
    except ValueError:
        raise TbError(f"--end 要写成 YYYY-MM-DD，收到的是 {args.end}。") from None
    if end >= date.today():
        raise TbError("--end 要是已经过完的一天（今天的数据还不全）。")
    item_id = resolve_item_id(args, cookies=load_taobao_cookies())
    if not item_id.isdigit():
        raise TbError(f"商品 ID 应该是一串数字，收到的是 {item_id}。")
    compete = load_compete(args.compete, item_id) if args.compete else None
    data = collect(item_id, args.days, end, compete)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = (out / f"item-{item_id}-{end}-{args.days}d.data.json").resolve()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    analysis = path.with_name(path.name.replace(".data.json", ".analysis.json"))
    for e in data["errors"]:
        print(f"⚠ 没取到：{e['part']}（{e['message']}）")
    print(f"第 1 步完成，数据已保存：{path}")
    print(f"第 2 步（AI 来做）：读 {GUIDE}，根据数据写分析，存为 {analysis}")
    print(f"第 3 步：item-report --analysis {analysis}（发给别人看的加 --mask 出脱敏版）")
