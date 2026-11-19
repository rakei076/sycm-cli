"""单品诊断报告的「深挖」：问题预警（排雷）、标题搜索词、详情页（同行对标 + 逐屏）、主图视频、SKU、关联搭配、退款原因、
服务体验、内容、价格、访客画像。都来自生意参谋（商品 360 的各个页签和问题预警），每块单独取；取不到的记进 errors，报告照出。
一共约 20 个请求。"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from ..cli import _value_of
from ..item import (ALARM_COUNTS, CODE_VALUE_CN, CONTENT_COLUMNS, DETAIL_METRICS, DETAIL_RATE_FIELDS, SERVICE_PAIRS,
                    SERVICE_RATE_FIELDS, TITLE_REC_GROUPS, VIDEO_COLUMNS, fetch_item_bundle, fetch_item_content,
                    fetch_item_detail, fetch_item_price, fetch_item_profile, fetch_item_rows, fetch_item_service,
                    fetch_item_title, fetch_item_video, fetch_problem_alarm, flatten_content_rows, flatten_detail_floors)

PROFILE_DIMS = {"gender": "性别", "age": "年龄", "purchase_level": "预测消费层级"}
REFUND_DAYS = 30        # 退款原因看最近 30 天（按付款时间），样本多一些


def _r(v: Any, n: int = 4) -> Any:
    return round(v, n) if isinstance(v, float) else v


def title_block(raw: dict[str, Any]) -> dict[str, Any]:
    """标题里每个词引来多少搜索访客。没引来搜索的词，平台连这一列都不给（不是 0）。"""
    words = [{"word": str(w.get("searchWord") or ""), "seUv": _value_of(w.get("guideSeUv")),
              "cv": _r(_value_of(w.get("payRate")))} for w in raw.get("words") or []]
    words.sort(key=lambda w: -(w["seUv"] or 0))
    rec = {cn: [{"word": r.get("word"), "hot": _r(r.get("hot_pctile")), "compete": _r(r.get("compete_pctile"))}
                for r in ((raw.get("recommend") or {}).get(key) or [])[:10]] for key, cn in TITLE_REC_GROUPS.items()}
    return {"words": words, "dead": [w["word"] for w in words if w["seUv"] is None],
            "recommend": {k: v for k, v in rec.items() if v}}


def detail_block(raw: dict[str, Any]) -> dict[str, Any]:
    """核心概况（本品 / 同行均值 / 同行优秀，口径是详情页：分母是详情页曝光人数）+ 逐屏。"""
    overview = raw.get("overview") or {}
    core = [{"key": code, "name": cn, "me": _r(cell.get("value")), "avg": _r(cell.get("rivalAvg")),
             "good": _r(cell.get("rivalGood")), "rate": code in DETAIL_RATE_FIELDS}
            for code, cn in DETAIL_METRICS.items() if isinstance(cell := overview.get(code), dict)]
    floors = [{"path": f["_path"], "uv": _value_of(f.get("itemExposeUv")), "cartUv": _value_of(f.get("itemCartUv")),
               "loss": _r(_value_of(f.get("itemLossRate")))} for f in flatten_detail_floors(raw.get("floors") or [])]
    return {"core": core, "floors": floors}


def sku_block(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = [{"sku": str(_value_of(r.get("skuName")) or ""), "cart": _value_of(r.get("cartCnt")),
            "amt": _r(_value_of(r.get("payAmt"))), "itm": _value_of(r.get("payItmCnt")),
            "byr": _value_of(r.get("payByrCnt"))} for r in rows if isinstance(r, dict)]
    return sorted(out, key=lambda r: (-(r["amt"] or 0), -(r["cart"] or 0)))


def refund_block(reasons: list[dict[str, Any]], skus: list[dict[str, Any]]) -> dict[str, Any]:
    """退款原因（一笔退款可能打上几个原因，各行不能相加）和各 SKU 退款。按原订单付款时间算。"""
    v = lambda r, k: _r(_value_of(r.get(k)))
    return {"reasons": [{"type": v(r, "rfdReasonTypeCn"), "reason": v(r, "rfdReasonNameCn"), "byr": v(r, "itemSucRfdByr"),
                         "lost": v(r, "lossByrCnt"), "amt": v(r, "itemRfdAmt"), "rate": v(r, "payAmtRfdRate")}
                        for r in reasons if isinstance(r, dict)],
            "skus": [{"sku": v(r, "skuName"), "byr": v(r, "itemSkuSucRfdByr"), "amt": v(r, "itemSkuRfdAmt"),
                      "rate": v(r, "payAmtRfdRate")} for r in skus if isinstance(r, dict) and v(r, "itemSkuSucRfdByr")]}


def service_block(data: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for own, peer, cn in SERVICE_PAIRS:
        cell = data.get(own)
        if isinstance(cell, dict):      # 服务端按权限少回指标是常态，缺的不列
            other = data.get(peer) if peer else None
            out.append({"name": cn, "me": _r(cell.get("value")), "avg": _r(other.get("value")) if isinstance(other, dict) else None,
                        "rate": own in SERVICE_RATE_FIELDS})
    return out


def content_block(raw: Any) -> dict[str, Any]:
    rows = flatten_content_rows((raw.get("data") if isinstance(raw, dict) else raw) or [])
    total = next((r for r in rows if r["_label"].startswith("合计")), None)
    items = [r for r in rows if r is not total][:5]
    pick = lambda r: {cn: _r(_value_of(r.get(code))) for code, cn in CONTENT_COLUMNS}
    return {"count": len(items), "total": pick(total) if total else None,
            "items": [{"name": r["_label"], **pick(r)} for r in items]}


def price_block(raw: dict[str, Any]) -> dict[str, Any]:
    info, seg = raw.get("info") or {}, raw.get("segment") or {}
    mine = str(seg.get("priceSegId") or "")
    bands = []
    for b in raw.get("bands") or []:
        g = lambda k: _value_of(b.get(k))
        row = {"name": g("priceSegName"), "byr": g("payByrCnt"), "share": _r(g("tradeIndexRatio")),
               "supply": _r(g("SupplyRatioIndex")), "growth": g("tradeGrowthRate"), "mine": str(g("priceSegId")) == mine}
        if any(row[k] not in (None, "", "None") for k in ("byr", "share", "supply", "growth")):
            bands.append(row)      # 没有市场类权限时整张表是空的，不列
    return {"list_price": _r(info.get("price")), "unit_price": _r(seg.get("itemUnitPrice1")),
            "band": seg.get("priceSegName"), "cate": (info.get("cateName") or "").replace("&gt;", ">"), "bands": bands}


def profile_rows(rows: list[dict[str, Any]], dim: str) -> list[dict[str, Any]]:
    names = CODE_VALUE_CN.get(dim, {})
    out = []
    for r in rows:
        m = r.get("itmUv") or {}
        value = str(_value_of(r.get("attrValue")))
        out.append({"value": names.get(value, value), "n": m.get("value"), "share": _r(m.get("ratio"))})
    return out if any(r["n"] for r in out) else []


def alarm_block(raw: dict[str, Any], item_id: str) -> dict[str, Any]:
    """问题预警是全店实时的：质量问题 / 缺货 / 高价限流各几个，本品在不在缺货明细里。"""
    stats = raw.get("statistics") or {}
    counts = stats.get("data") or {}
    stock = raw.get("stockout") or {}
    rows = (stock.get("data") if isinstance(stock, dict) else stock) or []
    return {"updated": stats.get("updateTime"), "counts": {cn: counts.get(code) for code, cn in ALARM_COUNTS},
            "stockout_me": any(str(item_id) in json.dumps(r, ensure_ascii=False) for r in rows)}


def _num_or_none(v: Any) -> Any:
    v = _value_of(v)
    return _r(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def video_block(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """本品自己的视频：曝光 → 点击 → 有效播放 → 完播 → 成交。平台对空值回 {}，这里一律记成 None。"""
    out = []
    for r in rows:
        row = {cn: _num_or_none(r.get(code)) for code, cn, _ in VIDEO_COLUMNS}
        row["平均播放秒数"] = _num_or_none(r.get("playSecondsPerTimeNew"))
        out.append(row)
    return out


def bundle_block(raw: dict[str, Any]) -> dict[str, Any]:
    """系统的连带推荐（买了这个款的人还买了什么）和掌柜自己配的搭配。"""
    def rows(lst: Any) -> list[dict[str, Any]]:
        out = []
        for r in lst or []:
            item, cell = r.get("item") or {}, r.get("bundlePayCnt") or {}
            out.append({"id": str(item.get("itemId") or ""), "title": item.get("title") or "",
                        "cnt": _num_or_none(cell.get("value")), "share": _r(cell.get("ratio"))})
        return out[:10]
    return {"system": rows(raw.get("system")), "seller": rows(raw.get("seller")), "configured": bool(raw.get("seller"))}


def busiest_day(daily: list[dict[str, Any]]) -> date | None:
    """访客画像只认单日、访客太少就不出：挑两个周期里访客最多的一天。"""
    rows = [r for r in daily if (r.get("uv") or 0) > 0]
    return date.fromisoformat(max(rows, key=lambda r: r["uv"])["d"]) if rows else None


def collect_deep(cookies, item_id: str, start: date, end: date, daily: list[dict[str, Any]], attempt) -> dict[str, Any]:
    """attempt(part, fn, default)：取不到就记错、给默认值（见 collect._try）。"""
    a, b = start.isoformat(), end.isoformat()
    win = dict(item_id=item_id, start_date=a, end_date=b, cookies=cookies)
    out: dict[str, Any] = {
        "title": attempt("标题搜索词", lambda: title_block(fetch_item_title(**win)), None),
        "detail": attempt("详情页（同行对标、逐屏）", lambda: detail_block(fetch_item_detail(**win)), None),
        "sku": attempt("SKU 销售", lambda: sku_block(fetch_item_rows("item-sku-list", want=30, **win)[0]), None),
        "service": attempt("服务体验", lambda: service_block(fetch_item_service(**win)), None),
        "content": attempt("内容", lambda: content_block(fetch_item_content(**win)), None),
        "price": attempt("价格", lambda: price_block(fetch_item_price(**win)), None),
        "alarm": attempt("问题预警", lambda: alarm_block(fetch_problem_alarm(cookies=cookies, day=b), item_id), None),
        "video": attempt("主图视频", lambda: video_block(fetch_item_video(**win)), None),
        "bundle": attempt("关联搭配", lambda: bundle_block(fetch_item_bundle(**win)), None),
    }
    r0 = (end - timedelta(days=REFUND_DAYS - 1)).isoformat()
    refund_win = dict(item_id=item_id, start_date=r0, end_date=b, cookies=cookies)
    out["refund"] = attempt("退款原因", lambda: {
        **refund_block(fetch_item_rows("item-refund-reason", want=20, **refund_win)[0],
                       fetch_item_rows("item-refund-sku", want=20, **refund_win)[0]),
        "period": [r0, b]}, None)
    day = busiest_day(daily)
    if day:
        dims = {}
        for dim, cn in PROFILE_DIMS.items():
            rows = attempt(f"访客画像（{cn}）", lambda: profile_rows(fetch_item_profile(
                item_id=item_id, date=day.isoformat(), profile_type=dim, crowds_type="itmUv", cookies=cookies), dim), [])
            if rows:
                dims[cn] = rows
        out["profile"] = {"date": day.isoformat(), "dims": dims}
    return out


def summary(deep: dict[str, Any]) -> dict[str, Any]:
    """给 AI 的要点（facts.深挖要点）。"""
    pct = lambda v: "-" if v is None else f"{v * 100:.2f}%"
    num = lambda v: "-" if v is None else (f"{v:.1f}" if isinstance(v, float) else str(v))
    out: dict[str, Any] = {}
    t = deep.get("title")
    if t:
        out["标题"] = {"词数": len(t["words"]), "零引导词": t["dead"],
                     "引来搜索的词": [f"{w['word']}（搜索访客 {w['seUv']}）" for w in t["words"] if w["seUv"]][:8]}
    d = deep.get("detail")
    if d and d["core"]:
        out["详情页同行对标（口径：分母是详情页曝光人数）"] = [
            f"{c['name']}：本品 {pct(c['me']) if c['rate'] else num(c['me'])}，同行均值 {pct(c['avg']) if c['rate'] else num(c['avg'])}，"
            f"同行优秀 {pct(c['good']) if c['rate'] else num(c['good'])}" for c in d["core"]
            if c["key"] in ("itemLossRate", "itemAvgStayTime", "itemCartConvertRate", "itemPayConvertRate")]
    if d and d["floors"]:
        out["详情页逐屏"] = [f"{f['path']}：曝光 {f['uv']} 人，跳失率 {pct(f['loss'])}" for f in d["floors"]]
    skus = deep.get("sku") or []
    total = sum(s["amt"] or 0 for s in skus)
    if skus and total:
        out["SKU"] = {"SKU 数": len(skus), "没卖出的 SKU 数": sum(1 for s in skus if not s["amt"]),
                     "成交最多的 SKU": f"{skus[0]['sku']}（占支付金额 {skus[0]['amt'] / total * 100:.0f}%）"}
    rf = deep.get("refund")
    if rf and rf["reasons"]:
        out["退款原因"] = [f"{r['type']}·{r['reason']}：{r['byr']} 人退款，其中 {r['lost'] or 0} 人转去竞店" for r in rf["reasons"][:5]]
    sv = deep.get("service") or []
    if sv:
        out["服务体验（本品 / 同类商品平均）"] = [f"{s['name']}：{pct(s['me']) if s['rate'] else num(s['me'])} / "
                                         f"{pct(s['avg']) if s['rate'] else num(s['avg'])}" for s in sv]
    c = deep.get("content")
    if c is not None:
        out["内容"] = f"关联了 {c['count']} 条短视频" if c["count"] else "没有关联任何短视频或内容"
    pr = deep.get("price")
    if pr:
        out["价格"] = {"挂牌价": pr["list_price"], "实际件单价": pr["unit_price"], "所属价格带": pr["band"], "类目": pr["cate"],
                     "类目价格带大盘": "有" if pr["bands"] else "没有（要市场类权限）"}
    al = deep.get("alarm")
    if al:
        out["问题预警（全店、实时）"] = "、".join(f"{k} {v if v is not None else '-'} 个" for k, v in al["counts"].items()) + \
            ("；**本品在缺货名单里**" if al["stockout_me"] else "；本品不在缺货名单里")
    vd = deep.get("video")
    if vd is not None:
        out["主图视频"] = [f"曝光 {v['曝光人数']} 人，曝光点击率 {pct(v['曝光点击率'])}，有效播放率 {pct(v['有效播放率'])}，"
                       f"完播率 {pct(v['完播率'])}，平均播放 {num(v['平均播放秒数'])} 秒" for v in vd] or "这个商品没有视频数据"
    bd = deep.get("bundle")
    if bd:
        out["关联搭配"] = ("掌柜推荐搭配已配置" if bd["configured"] else "**没配置掌柜推荐搭配**") + \
            ("；系统连带推荐：" + "、".join(f"{x['id']}（{pct(x['share'])}）" for x in bd["system"][:5]) if bd["system"] else "；系统连带推荐没有数据")
    pf = deep.get("profile")
    if pf and pf["dims"]:
        out["访客画像"] = {"日期": f"{pf['date']}（两个周期里访客最多的一天；画像只认单日，访客太少的日子平台不给）",
                       **{dim: "、".join(f"{r['value']} {pct(r['share'])}" for r in rows[:4]) for dim, rows in pf["dims"].items()}}
    return out
