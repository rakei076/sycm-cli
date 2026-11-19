"""单品诊断报告第 3 步的计算：检查 AI 写的分析、算 45 天方案的门槛曲线和模拟器预设、按需脱敏，拼成网页要用的数据。"""
from __future__ import annotations

import copy
import re
from datetime import date, timedelta
from typing import Any

from .collect import sum_days

DEFAULT_PLAN_DAYS = 45
# 目标里的倍数（相对基线）和比率的合理范围
TARGETS = {"uv": ("倍数", 0.3, 5.0), "se": ("倍数", 0.3, 5.0), "aov": ("倍数", 0.3, 3.0), "cv": ("比率", 0.0, 1.0),
           "cartRate": ("比率", 0.0, 1.0), "bounce": ("比率", 0.0, 1.0)}
CN = "一二三四五六七八九十"
# 脱敏：每类绝对数按本品分析周期的日均值折成 100
FAMILIES = {"uv": ("uv", "pv", "seUv"), "amt": ("amt", "rfd", "charge"), "aov": ("aov",),
            "byr": ("byr", "newb", "oldb", "cartByr", "clt", "seByr"), "itm": ("itm", "cart")}
COMPETE_ABSOLUTE = {"整体IPV", "整体成交笔数", "付费点击量", "当天引导成交笔数", "点击量", "成交笔数"}
# 达摩盘单品体检里照留的（比例和投产）；其余是本品的绝对量（金额、点击、浏览、客单价）
HEALTH_RATIOS = {"占店铺成交", "搜索点击率", "收藏加购率", "支付转化率", "连带率", "复购率", "广告投产"}


def check(analysis: dict[str, Any], data: dict[str, Any]) -> list[str]:
    """AI 的分析缺什么、写错什么。返回问题清单（空 = 可以出报告）。"""
    problems = []

    def need_text(path: str, v: Any):
        if not isinstance(v, str) or not v.strip():
            problems.append(f"{path} 要写成一段文字")

    need_text("verdict", analysis.get("verdict"))
    for key, inner in (("wounds", ("title", "points")), ("causes", ("title", "evidence", "actions"))):
        items = analysis.get(key)
        if not isinstance(items, list) or not items:
            problems.append(f"{key} 至少要有一条")
            continue
        for i, it in enumerate(items):
            missing = inner if not isinstance(it, dict) else [f for f in inner if not it.get(f)]
            problems += [f"{key}[{i}].{f} 没有填" for f in missing]
    gaps = analysis.get("gaps")
    if gaps is not None and (not isinstance(gaps, list) or not all(isinstance(g, dict) and g.get("dim") for g in gaps)):
        problems.append("gaps 要写成列表，每条是 {dim: 维度, fields: 需要字段, use: 用途}")
    plan = analysis.get("plan")
    if not isinstance(plan, dict):
        return problems + ["plan（45 天方案）没有填"]
    if plan.get("start"):
        try:
            date.fromisoformat(str(plan["start"]))
        except ValueError:
            problems.append("plan.start 要写成 YYYY-MM-DD（不写就从报告生成那天算起）")
    days = plan.get("days", DEFAULT_PLAN_DAYS)
    if not isinstance(days, int) or not 7 <= days <= 120:
        problems.append("plan.days 要是 7～120 之间的整数")
        days = DEFAULT_PLAN_DAYS
    phases = plan.get("phases")
    if not isinstance(phases, list) or not phases:
        return problems + ["plan.phases 至少要有一个阶段"]
    expect = 1
    for i, p in enumerate(phases):
        if not isinstance(p, dict) or not isinstance(p.get("from"), int) or not isinstance(p.get("to"), int):
            problems.append(f"plan.phases[{i}] 要有整数 from、to（第几天到第几天）")
            continue
        if p["from"] != expect or p["to"] < p["from"]:
            problems.append(f"plan.phases[{i}] 应该从第 {expect} 天开始、接着上一阶段，不能空档或重叠")
        expect = p["to"] + 1
        targets = p.get("targets")
        if not isinstance(targets, dict) or not {"uv", "cv", "aov"} <= set(targets):
            problems.append(f"plan.phases[{i}].targets 要有 uv、cv、aov")
            continue
        for k, v in targets.items():
            kind, lo, hi = TARGETS.get(k, (None, 0, 0))
            if kind is None:
                problems.append(f"plan.phases[{i}].targets.{k} 不认识（只能是 {'、'.join(TARGETS)}）")
            elif not isinstance(v, (int, float)) or not lo < v <= hi:
                unit = "相对基线的倍数，如 1.2 表示 +20%" if kind == "倍数" else "0～1 之间的小数，如 0.035 表示 3.5%"
                problems.append(f"plan.phases[{i}].targets.{k} = {v!r} 不对：要写{unit}")
    if expect - 1 != days:
        problems.append(f"plan.phases 的最后一天是 {expect - 1}，要和 plan.days（{days}）对上")
    if not plan.get("actions"):
        problems.append("plan.actions（动作清单）至少要有一条")
    for i, a in enumerate(plan.get("actions") or []):
        if not isinstance(a, dict) or not a.get("what"):
            problems.append(f"plan.actions[{i}].what 没有填")
    return problems


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def plan_calc(plan: dict[str, Any], base: dict[str, Any], earlier: dict[str, Any], start: date) -> dict[str, Any]:
    """按阶段目标，从基线线性爬坡算出每天的门槛；再给出「量·率·速」目标表、每个阶段的目标和模拟器预设。
    日均支付金额 = 日均访客 × 支付转化率 × 客单价，用相对基线的倍数算（基线没成交时退回按绝对值算）。"""
    uv0, amt0, cv0, aov0 = base["日均访客"], base["日均支付金额"], base["支付转化率"] or 0, base["客单价"]
    se0 = base.get("日均搜索引导访客")
    aov_ref = aov0 or earlier.get("aov")

    def gmv(t: dict[str, float]) -> float | None:
        if amt0 and cv0:
            return amt0 * t["uv"] * (t["cv"] / cv0) * t["aov"]
        return uv0 * t["uv"] * t["cv"] * aov_ref * t["aov"] if aov_ref else None

    start_point = {"uv": 1.0, "se": 1.0, "cv": cv0, "aov": 1.0, "cartRate": base.get("加购率"), "bounce": base.get("详情页跳出率")}
    phases = plan["phases"]
    ramp, stages, given, prev = [], [], set(), start_point
    for n, p in enumerate(phases, 1):
        t1 = {**prev, **p["targets"]}
        given |= set(p["targets"])
        span = p["to"] - p["from"] + 1
        for k in range(p["from"], p["to"] + 1):
            frac = (k - p["from"] + 1) / span
            t = {key: _lerp(prev[key], t1[key], frac) for key in ("uv", "cv", "aov")}
            ramp.append({"d": k, "date": (start + timedelta(days=k - 1)).isoformat(), "phase": n,
                         "uv": round(uv0 * t["uv"], 2), "cv": round(t["cv"], 5), "gmv": _round(gmv(t))})
        stages.append({"n": n, "name": p.get("name") or f"阶段{n}", "theme": p.get("theme") or "", "from": p["from"], "to": p["to"],
                       "dates": [(start + timedelta(days=p[k] - 1)).isoformat() for k in ("from", "to")],
                       "uv": _round(uv0 * t1["uv"]), "se": _round(se0 * t1["se"]) if "se" in given and se0 is not None else None,
                       "cv": t1["cv"], "cartRate": t1["cartRate"] if "cartRate" in given else None,
                       "bounce": t1["bounce"] if "bounce" in given else None,
                       "aov": _round(aov0 * t1["aov"]) if aov0 else None, "gmv": _round(gmv(t1))})
        prev = t1
    final, g = prev, gmv(prev)
    rows = [("量", "商品访客", "uv", uv0, uv0 * final["uv"])]
    if "se" in given and se0 is not None:
        rows.append(("量", "搜索引导访客/日", "uv", se0, se0 * final["se"]))
    rows.append(("率", "支付转化率", "rate", cv0, final["cv"]))
    if "cartRate" in given:
        rows.append(("率", "加购率", "rate", base.get("加购率"), final["cartRate"]))
    if "bounce" in given:
        rows.append(("率", "跳失率", "rate", base.get("详情页跳出率"), final["bounce"]))
    rows += [("速", "客单价", "aov", aov0, aov0 * final["aov"] if aov0 else None),
             ("速", "日均支付金额", "amt", amt0, g), ("速", "月化支付金额", "amt", amt0 * 30, g * 30 if g is not None else None)]
    days, last = base["天数"], phases[-1]["to"]
    presets = [{"name": "恢复基线", "uv": 1.0, "cv": cv0, "aov": 1.0}]
    if earlier.get("uv") and uv0:
        presets.append({"name": f"回到前 {days} 天水平", "uv": round(earlier["uv"] / days / uv0, 4), "cv": earlier.get("cv") or 0,
                        "aov": round(earlier["aov"] / aov0, 4) if earlier.get("aov") and aov0 else 1.0})
    prev = start_point
    for n, p in enumerate(phases, 1):
        prev = {**prev, **p["targets"]}
        presets.append({"name": f"阶段{CN[n - 1] if n <= len(CN) else n}目标" + (f"(D{last})" if n == len(phases) else ""),
                        "uv": prev["uv"], "cv": prev["cv"], "aov": prev["aov"]})
    return {"start": start.isoformat(), "end": (start + timedelta(days=last - 1)).isoformat(), "days": last,
            "ramp": ramp, "stages": stages, "presets": presets,
            "targets": [{"维度": dim, "指标": label, "单位": unit, "基线": _round(x), "目标": _round(y)} for dim, label, unit, x, y in rows],
            "final_gmv": _round(g), "base_gmv": amt0, "base_uv": uv0, "base_cv": cv0, "base_aov": aov0 or aov_ref,
            "threshold_cv": phases[0]["targets"]["cv"]}


def _round(v: Any) -> Any:
    return round(v, 4) if isinstance(v, float) else v


def view(data: dict[str, Any], analysis: dict[str, Any], *, mask: bool = False) -> dict[str, Any]:
    """网页和配套表格要的全部数据（网页只嵌 render.PAGE_KEYS 这几项）。"""
    days = data["meta"]["days"]
    base = {**data["facts"]["基线"], "天数": days}
    plan = analysis["plan"]
    start = date.fromisoformat(plan["start"]) if plan.get("start") else date.fromisoformat(data["meta"]["generated"][:10])
    bench, floor = peers(copy.deepcopy(data.get("bench") or []), data["meta"]["item_id"])
    best = max((r for r in bench if r["peer"]), key=lambda r: r.get("cv") or 0, default=None)
    out = {"meta": data["meta"], "daily": data["daily"], "shop_daily": data.get("shop_daily") or [], "halves": data["halves"],
           "total": sum_days(data["daily"]), "bench": bench, "best": best["id"] if best else None, "floor": floor, "flow": data["flow"],
           "deep": copy.deepcopy(data.get("deep") or {}), "compete": copy.deepcopy(data.get("compete")),
           "errors": data.get("errors") or [], "anomalies": copy.deepcopy(data.get("anomalies") or []), "analysis": analysis,
           "plan": plan_calc(plan, base, data["halves"]["对比周期"], start), "masked": mask}
    return masked(out) if mask else out


def peers(bench: list[dict[str, Any]], item_id: str) -> tuple[list[dict[str, Any]], float]:
    """同店对标：和本品同一个一级类目的商品（表里会混着几个叶子类目）；访客够多的才能当转化率标杆。
    和 collect.bench_position 同一个门槛。"""
    me = next((r for r in bench if r["id"] == item_id), None)
    floor = max(20, ((me or {}).get("uv") or 0) * 0.1)
    for r in bench:
        r["me"] = r["id"] == item_id
        r["same"] = bool(me) and r.get("top") == me.get("top")
        r["peer"] = r["same"] and not r["me"] and (r.get("uv") or 0) >= floor
    return bench, floor


# ---------- 脱敏 ----------

def masked(v: dict[str, Any]) -> dict[str, Any]:
    """强脱敏：商品、店铺身份隐去；金额、访客、买家、件数折成指数（本品分析周期日均 = 100）；比率、趋势、结构照留。"""
    v = copy.deepcopy(v)
    days = v["meta"]["days"]
    later = v["halves"]["分析周期"]
    ref = {"uv": (later.get("uv") or 0) / days, "amt": (later.get("amt") or 0) / days, "aov": later.get("aov") or 0,
           "byr": (later.get("byr") or 0) / days, "itm": (later.get("itm") or 0) / days}
    for fam, keys in FAMILIES.items():
        if not ref[fam]:     # 分析周期为 0 时退到每日最大值
            ref[fam] = max((r.get(keys[0]) or 0 for r in v["daily"]), default=0)
    scale = {k: (100 / ref[fam] if ref[fam] else 1.0) for fam, keys in FAMILIES.items() for k in keys}

    def apply(row: dict[str, Any]) -> None:
        for k, f in scale.items():
            if isinstance(row.get(k), (int, float)) and not isinstance(row.get(k), bool):
                row[k] = round(row[k] * f, 1)

    for row in [*v["daily"], *v["shop_daily"], *v["halves"].values(), v["total"], *v["bench"],
                *[r for rows in v["flow"].values() for r in rows]]:
        apply(row)
    alias = aliases(v)          # 要在换掉商品 ID 之前算
    _mask_deep(v["deep"], scale, alias)
    codes: dict[str, str] = {}  # 同店对标表的类目名换成类目A、B……（页头的本品类目照留）
    for row in v["bench"]:
        if row.get("cateName"):
            row["cateName"] = codes.setdefault(row["cateName"], "类目" + (chr(ord("A") + len(codes)) if len(codes) < 26 else f"Z{len(codes) - 25}"))
        row.pop("topName", None)
        code = alias[row["id"]]        # 照客户样板：本品写「本品（类目）」，其他写「同店对标商品B」
        row["title"] = f"本品（{v['meta'].get('cateName') or code}）" if code == "商品A" else "同店对标" + code
        row["id"] = code
    if v["best"]:
        v["best"] = alias[v["best"]]
    v["floor"] = round(v["floor"] * scale["uv"], 1)
    meta = v["meta"]
    meta["title"], meta["item_id"] = "本品（商品A）", alias.get(meta["item_id"], "商品A")
    # 方案里的绝对值也折成指数
    p = v["plan"]
    f_uv, f_amt, f_aov = scale["uv"], scale["amt"], scale["aov"]
    for r in p["ramp"]:
        r["uv"] = round(r["uv"] * f_uv, 1)
        r["gmv"] = None if r["gmv"] is None else round(r["gmv"] * f_amt, 1)
    for t in p["targets"]:
        f = {"uv": f_uv, "amt": f_amt, "aov": f_aov}.get(t["单位"])
        if f:
            t["基线"], t["目标"] = [None if x is None else round(x * f, 1) for x in (t["基线"], t["目标"])]
    for st in p["stages"]:
        for k, f in (("uv", f_uv), ("se", f_uv), ("aov", f_aov), ("gmv", f_amt)):
            st[k] = None if st[k] is None else round(st[k] * f, 1)
    for k, f in (("final_gmv", f_amt), ("base_gmv", f_amt), ("base_uv", f_uv), ("base_aov", f_aov)):
        p[k] = None if p[k] is None else round(p[k] * f, 1)
    for a in v["anomalies"]:      # 只留「平均每人几件」
        a.pop("people", None), a.pop("pieces", None)
    if v["compete"]:
        v["compete"] = _mask_compete(v["compete"], alias)
    v["analysis"] = _replace_ids(v["analysis"], alias)
    v["errors"] = [{**e, "message": _replace_text(e["message"], alias)} for e in v["errors"]]
    return v


def aliases(v: dict[str, Any]) -> dict[str, str]:
    """本品 → 商品A，同店其他商品按支付金额排 → 商品B、C……；达摩盘竞品 → 竞品1、2……"""
    me = v["meta"]["item_id"]
    alias = {me: "商品A"}
    others = sorted((r for r in v["bench"] if r["id"] != me), key=lambda r: -(r.get("amt") or 0))
    for n, r in enumerate(others):
        alias[r["id"]] = "商品" + (chr(ord("B") + n) if n < 25 else f"Z{n - 24}")
    for n, rid in enumerate((v.get("compete") or {}).get("竞品") or [], 1):
        alias[str(rid)] = f"竞品{n}"
    refs = (((v.get("compete") or {}).get("单品洞察") or {}).get("可参照的成功商品")) or []
    for n, r in enumerate(refs, 1):
        alias.setdefault(r["id"], f"参照商品{n}")
        if len(r.get("标题") or "") >= 6:
            alias.setdefault(r["标题"], alias[r["id"]])
    titles = {r["title"]: alias[r["id"]] for r in v["bench"] if len(r.get("title") or "") >= 6}
    if len(v["meta"].get("title") or "") >= 6:
        titles[v["meta"]["title"]] = "商品A"
    return {**titles, **alias}


def _replace_text(s: str, alias: dict[str, str]) -> str:
    """商品 ID、完整标题换成代号；没登记的长数字（别的商品 ID）直接隐去。"""
    for real in sorted(alias, key=len, reverse=True):
        s = s.replace(real, alias[real])
    return re.sub(r"\d{10,}", "（商品ID已隐去）", s)


def _replace_ids(x: Any, alias: dict[str, str]) -> Any:
    if isinstance(x, str):
        return _replace_text(x, alias)
    if isinstance(x, list):
        return [_replace_ids(i, alias) for i in x]
    if isinstance(x, dict):
        return {k: _replace_ids(i, alias) for k, i in x.items()}
    return x


def _mask_compete(c: dict[str, Any], alias: dict[str, str]) -> dict[str, Any]:
    """达摩盘竞品对比：绝对量（IPV、笔数、点击量、人数）不给值只留变化；比率、结构、客群占比照留。"""
    def hide(block: dict[str, Any]) -> None:
        for label, vals in block.items():
            if label in COMPETE_ABSOLUTE:
                for cell in vals.values():
                    cell["本期"] = cell["对比期"] = "（脱敏）"
    for name in ("控比", "经营指标", "推广指标"):
        hide(c.get(name) or {})
    for key in ("分渠道指标（广告域归因）", "分渠道指标（全域归因）"):
        for row in c.get(key) or []:
            hide(row.get("指标") or {})
    aud = c.get("客群分析")
    if aud:
        aud["人数（按性别标签合计）"] = {k: "（脱敏）" for k in aud.get("人数（按性别标签合计）") or {}}
    ins = c.get("单品洞察")
    if ins:      # 本品自己的诊断、归因里的绝对数（金额、展示量、类目排名）隐去，比例和倍数照留
        for d in ins.get("单品诊断") or []:
            d["结论"] = [mask_numbers(t) for t in d.get("结论") or []]
        for a in ins.get("变化归因") or []:
            a["结论"] = mask_numbers(a.get("结论") or "")
            a["原因"] = [mask_numbers(t) for t in a.get("原因") or []]
        for x in ins.get("单品指标") or []:
            if "率" not in (x.get("指标") or "") and "ROI" not in (x.get("指标") or ""):
                x["本品"] = "（脱敏）"
        for m in ((ins.get("单品体检") or {}).get("指标")) or []:
            if m["指标"] not in HEALTH_RATIOS:
                m["本品"] = "（脱敏）"
        if ins.get("成长诊断"):
            ins["成长诊断"] = mask_numbers(ins["成长诊断"])
    return _replace_ids(_rekey(c, alias), alias)


# 数字后面跟着这些的照留（是比例、倍数、天数），其余的数（金额、人数、展示量、排名）隐去
_KEEP_AFTER = r"(?!\s*(?:%|倍|天|周|个月|月|年|个百分点|[\d.,]))"


def mask_numbers(text: str) -> str:
    return re.sub(r"(?<![\d.,])\d[\d,]*(?:\.\d+)?" + _KEEP_AFTER, "（脱敏）", text)


def _mask_deep(deep: dict[str, Any], scale: dict[str, float], alias: dict[str, str]) -> None:
    """深挖部分：数量折成和别处一样的指数；标题分词只留统计（词本身会露出品牌）；挂牌价隐去只留价格带；画像只留占比；
    搭配里的同店商品换代号。"""
    f = lambda key, v: round(v * scale[key], 1) if isinstance(v, (int, float)) and not isinstance(v, bool) else v
    for row in deep.get("video") or []:
        for k in ("曝光人数", "点击人数", "有效播放人数"):
            row[k] = f("uv", row.get(k))
        row["当日成交人数"], row["当日成交金额"] = f("byr", row.get("当日成交人数")), f("amt", row.get("当日成交金额"))
    bd = deep.get("bundle")
    if bd:
        for r in bd["system"] + bd["seller"]:
            r["title"] = alias.get(r["id"], "同店商品")
            r["id"], r["cnt"] = alias.get(r["id"], ""), f("itm", r["cnt"])
    t = deep.get("title")
    if t:
        deep["title"] = {"masked": True, "count": len(t["words"]), "dead": len(t["dead"]),
                         "guided": len(t["words"]) - len(t["dead"]), "recommend": t["recommend"]}
    d = deep.get("detail")
    if d:
        for c in d["core"]:
            if not c["rate"] and c["key"] != "itemAvgStayTime":
                c["me"], c["avg"], c["good"] = f("uv", c["me"]), f("uv", c["avg"]), f("uv", c["good"])
        for fl in d["floors"]:
            fl["uv"], fl["cartUv"] = f("uv", fl["uv"]), f("uv", fl["cartUv"])
    for r in deep.get("sku") or []:
        r["amt"], r["cart"], r["itm"], r["byr"] = f("amt", r["amt"]), f("itm", r["cart"]), f("itm", r["itm"]), f("byr", r["byr"])
    rf = deep.get("refund")
    if rf:
        for r in rf["reasons"]:
            r["byr"], r["lost"], r["amt"] = f("byr", r["byr"]), f("byr", r["lost"]), f("amt", r["amt"])
        for r in rf["skus"]:
            r["byr"], r["amt"] = f("byr", r["byr"]), f("amt", r["amt"])
    for r in deep.get("service") or []:
        if not r["rate"]:
            r["me"], r["avg"] = f("byr", r["me"]), f("byr", r["avg"])
    c = deep.get("content")
    if c:
        unit = {"商品点击次数": "uv", "粉丝点击次数": "uv", "引导收藏次数": "byr", "引导加购件数": "itm", "种草成交人数": "byr", "种草成交金额": "amt"}
        for n, row in enumerate([c["total"], *c["items"]]):
            if row:
                for k, key in unit.items():
                    row[k] = f(key, row.get(k))
                if "name" in row:
                    row["name"] = f"内容{n}"
    pr = deep.get("price")
    if pr:
        pr["list_price"] = pr["unit_price"] = None
    pf = deep.get("profile")
    if pf:
        for rows in pf["dims"].values():
            for r in rows:
                r["n"] = None


def _rekey(x: Any, alias: dict[str, str]) -> Any:
    """字典的键也可能是商品 ID（竞品对比按商品 ID 分列）。"""
    if isinstance(x, list):
        return [_rekey(i, alias) for i in x]
    if isinstance(x, dict):
        return {alias.get(k, k): _rekey(i, alias) for k, i in x.items()}
    return x
