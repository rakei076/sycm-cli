"""单品诊断报告第 3 步：检查 AI 的分析，把数据和分析排成单文件网页（数据内嵌，断网能开，手机能看，跟随系统深浅色）。"""
from __future__ import annotations

import hashlib
import json
from html import escape
from pathlib import Path
from typing import Any

from ....core.errors import TbError
from . import xlsx
from .build import aliases, check, view

TEMPLATE = Path(__file__).with_name("template.html")
GUIDE = "references/item-report-guide.md"
# 网页只嵌七页用得到的（流量来源、深挖、竞品只进数据文件和配套表格，给 AI 写分析用）
PAGE_KEYS = ("meta", "daily", "shop_daily", "total", "bench", "best", "floor", "plan", "analysis", "errors", "anomalies", "masked")


def render(data: dict[str, Any], analysis: dict[str, Any], *, mask: bool = False) -> str:
    return page(view(data, analysis, mask=mask))


def page(v: dict[str, Any]) -> str:
    # 内嵌在 <script> 里：</ 和两个 JS 换行符要转义
    blob = json.dumps({k: v[k] for k in PAGE_KEYS}, ensure_ascii=False)
    blob = blob.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    title = v["analysis"].get("title") or "单品诊断与 45 天「量·率·速」增长方案"
    if v["masked"]:
        title += "（强脱敏版）"
    html = TEMPLATE.read_text(encoding="utf-8")
    return html.replace("__TITLE__", escape(title), 1).replace("/*__DATA__*/null", blob, 1)


def _load(path: Path, what: str) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as ex:
        raise TbError(f"{what} {path.name} 不是合法的 JSON：第 {ex.lineno} 行第 {ex.colno} 列，{ex.msg}。", stage="读取文件") from None
    if not isinstance(obj, dict):
        raise TbError(f"{what} {path.name} 最外层要是一个 JSON 对象。", stage="读取文件")
    return obj


def data_path_for(analysis: Path) -> Path:
    return analysis.with_name(analysis.name.replace(".analysis.json", ".data.json"))


def load_pair(analysis_file: str, data_file: str | None = None) -> tuple[dict[str, Any], dict[str, Any], Path]:
    """读数据文件和 AI 写的分析，检查分析能不能用。返回（数据、分析、数据文件路径）。"""
    a_path = Path(analysis_file).resolve()
    d_path = Path(data_file).resolve() if data_file else data_path_for(a_path)
    if not a_path.exists():
        raise TbError(f"找不到分析文件 {a_path}。", stage="读取文件")
    if not d_path.exists():
        hint = "文件名里的中文在这个终端里变成了乱码，请改用程序生成的 ASCII 文件名。" if "?" in str(d_path) else "先运行 item-report 取数，或用 --data 指定。"
        raise TbError(f"找不到数据文件 {d_path}。", stage="读取文件", hint=hint)
    data, analysis = _load(d_path, "数据文件"), _load(a_path, "分析文件")
    problems = check(analysis, data)
    if problems:
        raise TbError("分析文件还不能用：\n" + "\n".join("- " + p for p in problems), stage="检查分析",
                      hint=f"照 {GUIDE} 改好 {a_path.name} 再运行。")
    return data, analysis, d_path


def write_html(analysis_file: str, data_file: str | None = None, *, mask: bool = False) -> Path:
    data, analysis, d_path = load_pair(analysis_file, data_file)
    v = view(data, analysis, mask=mask)
    if mask:   # 脱敏版的文件名也不带商品 ID
        tag = hashlib.sha1(d_path.name.encode()).hexdigest()[:6]
        out = d_path.with_name(f"report-{data['meta']['end']}-masked-{tag}.html")
        write_mapping(view(data, analysis), out.with_suffix(".mapping.txt"))
    else:
        out = d_path.with_name(d_path.name.replace(".data.json", ".html"))
    out.write_text(page(v), encoding="utf-8")
    xlsx.write(v, out.with_suffix(".xlsx"))
    return out


def write_mapping(v: dict[str, Any], path: Path) -> Path:
    """脱敏版的代号对照（只给自己看）：哪个代号是哪个商品。"""
    titles = {r["id"]: r.get("title") or "" for r in v["bench"]}
    for r in (((v.get("compete") or {}).get("单品洞察") or {}).get("可参照的成功商品")) or []:
        titles.setdefault(r["id"], r.get("标题") or "")
    lines = ["这份代号对照只给自己看，不要和脱敏报告一起发出去。", ""]
    lines += [f"{code}\t{real}\t{titles.get(real, '')}" for real, code in aliases(v).items() if real.isdigit()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
