"""单品诊断报告第 1 步：取数，算好对比，存成 data.json 交给 AI 写分析。

生意参谋的单品接口只认 1/7/15/30 天的窗口，所以报告是「分析周期（最近 N 天）对比对比周期（紧挨着的前 N 天）」，N = 7/15/30。
全部只读 GET，一共约 8～11 个请求：
- 商品趋势 /cc/item/sale/trend.json：传一个日期，回这个商品截止那天 30 天的每日指标（N=30 时再往前取一次）
- 店铺趋势 /portal/coreIndex/new/trend/v3.json：店铺 30 天每日指标，同上
- 单品汇总 /cc/item/sale/overview.json：两个周期各一次（周期内的访客、买家是去重的，转化率以它为准）
- 流量来源 /flow/item/source/tree/support.json：两个周期各一次
- 商品排行 /cc/item/view/top.json：分析周期，最多 3 页（每页 20 个），同店对标用；
  另外按商品 ID 筛、每天查一次（2N 次）：商品趋势里没有搜索引导访客，只能这样拿每天的数
- 商品类目 /cc/item/price/info.json：同店对标表要类目名，和本品同一级类目的每个叶子类目查一次
商品趋势取不到就停；其他几块取不到记进 errors，报告照出、在「数据缺口」里写明。
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Any

from ....core.errors import LoginExpired, Redirected, RiskStopped, TbError
from ..cli import _api_get, _content_data_or_error, _fetch_order_portal, _value_of, fetch_preset, load_taobao_cookies
from ..item import REFERER_ARCHIVES, fetch_item_cate, fetch_item_preset
from .deep import collect_deep, summary as deep_summary

TREND_PATH = "/cc/item/sale/trend.json"
SHOP_TREND_PATH = "/portal/coreIndex/new/trend/v3.json"
BEIJING = timezone(timedelta(hours=8))
BENCH_PAGES = 3          # 商品排行每页最多 20 个
PERIODS = ("对比周期", "分析周期")

# 商品趋势和单品汇总共用一套字段码
ITEM = {"uv": "itmUv", "pv": "itmPv", "amt": "payAmt", "itm": "payItmCnt", "byr": "payByrCnt", "cv": "payRate",
        "cart": "itemCartCnt", "cartByr": "itemCartByrCnt", "clt": "itemCltByrCnt", "newb": "newPayByrCnt",
        "oldb": "payOldByrCnt", "bounce": "itmBounceRate", "stay": "itmStayTime", "rfd": "rfdSucAmt", "charge": "fCharge"}
SHOP = {"uv": "uv", "amt": "payAmt", "byr": "payByrCnt", "cv": "payRate", "aov": "payPct"}
FLOW = {"uv": "uv", "pv": "pv", "byr": "payByrCnt", "itm": "payItmCnt", "amt": "payAmt", "cv": "payRate",
        "cartByr": "cartByrCnt", "clt": "cltItmCnt"}
BENCH = {"uv": "itmUv", "amt": "payAmt", "byr": "payByrCnt", "itm": "payItmCnt", "cv": "payRate", "aov": "payPct",
         "cart": "itemCartCnt", "clt": "itemCltByrCnt", "bounce": "itmBounceRate", "stay": "stayTimeAvg",
         "seUv": "seGuideUv", "seCv": "seGuidePayRate", "rfd": "sucRefundAmt"}
SEARCH, RECOMMEND, PAID = "reward.5080", "reward.5081", "22"   # 流量来源里「经营优势/搜索」「经营优势/推荐」「付费推广」的节点
# data.json 里的英文键是什么（给 AI 和看数据的人）
FIELDS = {"uv": "访客数", "pv": "浏览量", "amt": "支付金额", "itm": "支付件数", "byr": "支付买家数", "cv": "支付转化率",
          "aov": "客单价", "cart": "加购件数", "cartByr": "加购人数", "cartRate": "加购率（加购人数÷访客数）",
          "cartPerUv": "加购件数÷访客数（商品排行没有加购人数）",
          "clt": "收藏人数", "newb": "支付新买家数", "oldb": "支付老买家数", "bounce": "详情页跳出率",
          "stay": "平均停留时长（秒）", "rfd": "成功退款金额（按退款完结时间）", "charge": "推广花费",
          "seUv": "搜索引导访客数", "seByr": "搜索引导支付买家数", "seCv": "搜索引导支付转化率",
          "seShare": "搜索引导访客占比（搜索引导访客 ÷ 访客）", "paidShare": "付费访客占比", "rfdRate": "退款率（成功退款金额 ÷ 支付金额）",
          "top": "一级类目 ID", "cateName": "叶子类目名", "topName": "一级类目名"}


def _r(v: Any, n: int = 4) -> Any:
    return round(v, n) if isinstance(v, float) else v


def _ratio(a: Any, b: Any) -> float | None:
    return a / b if isinstance(a, (int, float)) and b else None


def derive(row: dict[str, Any]) -> dict[str, Any]:
    """补上客单价、加购率，小数统一保留 4 位。加购率按人算（= 生意参谋的「访问加购转化率」），
    一个人加购几百件的异常单不会把它拉歪。"""
    row["aov"] = _ratio(row.get("amt"), row.get("byr"))
    row["cartRate"] = _ratio(row.get("cartByr"), row.get("uv"))
    return {k: _r(v) for k, v in row.items()}


def trend_rows(series: dict[str, Any], end: date) -> list[dict[str, Any]]:
    """商品趋势：每个指标一个 30 天的列表，日期只给「MM-DD」，最后一天就是传进去的日期。"""
    labels = series.get("statDate") or []
    rows = []
    for i, label in enumerate(labels):
        d = end - timedelta(days=len(labels) - 1 - i)
        if label != d.strftime("%m-%d"):
            raise TbError(f"商品趋势的日期对不上：第 {i + 1} 天应是 {d:%m-%d}，平台给的是 {label}。",
                          endpoint=TREND_PATH, stage="整理商品趋势")
        row: dict[str, Any] = {"d": d.isoformat()}
        for key, field in ITEM.items():
            values = series.get(field) or []
            row[key] = values[i] if i < len(values) else None
        rows.append(derive(row))
    return rows


def shop_rows(series: dict[str, Any]) -> list[dict[str, Any]]:
    """店铺趋势：日期是毫秒时间戳（北京时间零点）。"""
    rows = []
    for i, ms in enumerate(series.get("statDate") or []):
        row: dict[str, Any] = {"d": datetime.fromtimestamp(ms / 1000, tz=BEIJING).date().isoformat()}
        for key, field in SHOP.items():
            values = series.get(field) or []
            row[key] = _r(values[i] if i < len(values) else None)
        rows.append(row)
    return rows


def overview_row(data: dict[str, Any]) -> dict[str, Any]:
    return derive({key: _value_of(data.get(field)) for key, field in ITEM.items()})


def flow_rows(tree: Any, path: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """流量来源树拉平：每个渠道一行，path 是「一级/二级/三级」。"""
    out = []
    for node in tree or []:
        name = str(_value_of(node.get("pageName")) or "")
        here = (*path, name)
        row: dict[str, Any] = {"id": str(_value_of(node.get("pageId")) or ""), "path": "/".join(here), "level": len(here)}
        row.update({key: _r(_value_of(node.get(field))) for key, field in FLOW.items()})
        out.append(row)
        out += flow_rows(node.get("children"), here)
    return out


def bench_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        item = r.get("item") if isinstance(r.get("item"), dict) else {}
        row: dict[str, Any] = {"id": str(_value_of(r.get("itemId")) or item.get("itemId") or ""),
                               "title": str(item.get("title") or ""), "cate": str(_value_of(r.get("cateId")) or ""),
                               "top": str(_value_of(r.get("cateLevel1Id")) or "")}
        row.update({key: _value_of(r.get(field)) for key, field in BENCH.items()})
        row["cartPerUv"] = _ratio(row["cart"], row["uv"])     # 商品排行没有加购人数，只能按件算
        out.append({k: _r(v) for k, v in row.items()})
    return out


def sum_days(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """按日相加（访客、买家没有去重）：单品汇总取不到时的退路，也是网页「结论摘要」整段的数。
    搜索引导访客有一天没取到，整段就不算（写 None），免得少算。"""
    total = {k: sum(r.get(k) or 0 for r in rows) for k in ("uv", "pv", "amt", "itm", "byr", "cart", "cartByr", "clt",
                                                          "newb", "oldb", "rfd", "charge")}
    for k in ("seUv", "seByr"):
        total[k] = None if any(r.get(k) is None for r in rows) else sum(r[k] for r in rows)
    total["cv"] = _ratio(total["byr"], total["uv"])
    total["bounce"] = _ratio(sum((r.get("bounce") or 0) * (r.get("uv") or 0) for r in rows), total["uv"])
    total["stay"] = _ratio(sum((r.get("stay") or 0) * (r.get("uv") or 0) for r in rows), total["uv"])
    total["seShare"], total["seCv"] = _ratio(total["seUv"], total["uv"]), _ratio(total["seByr"], total["seUv"])
    total["rfdRate"] = _ratio(total["rfd"], total["amt"])
    return derive(total)


# ---------- 取数 ----------

def windows(end: date, days: int) -> dict[str, tuple[date, date]]:
    return {"对比周期": (end - timedelta(days=2 * days - 1), end - timedelta(days=days)),
            "分析周期": (end - timedelta(days=days - 1), end)}


def _stamp() -> str:
    return str(int(time.time() * 1000))


def fetch_item_trend(cookies, item_id: str, day: date) -> list[dict[str, Any]]:
    params = {"_": _stamp(), "token": cookies.get("_tb_token_", ""), "itemId": item_id, "dateType": "day",
              "dateRange": f"{day}|{day}", "device": "0"}
    raw = _api_get(TREND_PATH, params, cookies, referer=REFERER_ARCHIVES)
    return trend_rows(raw.get("data") or {}, day)


def fetch_shop_trend(cookies, day: date) -> list[dict[str, Any]]:
    data = _content_data_or_error(_fetch_order_portal(SHOP_TREND_PATH, date_value=day.isoformat(), cookies=cookies))
    return shop_rows(data.get("self") or {})


def fetch_series(fetch, cookies, end: date, start: date) -> list[dict[str, Any]]:
    """趋势接口一次给 30 天；不够就再往前取一段。只留 start 之后的。"""
    rows = fetch(cookies, end)
    while rows and rows[0]["d"] > start.isoformat():
        earlier = fetch(cookies, date.fromisoformat(rows[0]["d"]) - timedelta(days=1))
        if not earlier:
            break
        rows = earlier + rows
    return [r for r in rows if r["d"] >= start.isoformat()]


def fetch_bench(cookies, start: date, end: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, BENCH_PAGES + 1):
        raw = fetch_preset("item-list", start_date=start.isoformat(), end_date=end.isoformat(),
                           page_no=page, page_size=20, cookies=cookies)
        data = raw.get("data") or {}
        got = data.get("data") or []
        rows += got
        if not got or len(rows) >= (data.get("recordCount") or 0):
            break
    return bench_rows(rows)


def fetch_item_search(cookies, item_id: str, day: date) -> dict[str, Any]:
    """某一天的搜索引导访客和支付买家。商品趋势里没有搜索的数，只能在商品排行里按商品 ID 筛出来、一天查一次。"""
    raw = fetch_preset("item-list", start_date=day.isoformat(), end_date=day.isoformat(), cookies=cookies,
                       extra={"keyword": item_id})
    rows = (raw.get("data") or {}).get("data") or []
    row = next((r for r in rows if str(_value_of(r.get("itemId"))) == item_id), {})
    return {"seUv": _value_of(row.get("seGuideUv")), "seByr": _value_of(row.get("seGuidePayByrCnt"))}


def add_search(daily: list[dict[str, Any]], search: dict[str, dict[str, Any]]) -> None:
    for r in daily:
        s = search.get(r["d"]) or {}
        r["seUv"], r["seByr"] = s.get("seUv"), s.get("seByr")
        r["seShare"] = _r(_ratio(r["seUv"], r["uv"]))


def cate_names(bench: list[dict[str, Any]], item_id: str, my_path: str, lookup) -> None:
    """同店对标表要显示类目名，商品排行只有类目 ID：和本品同一个一级类目的每个叶子类目，挑一个商品查一次类目全名
    （「一级>二级>叶子」）。本品的全名已经在商品 360 的价格信息里。"""
    me = next((r for r in bench if r["id"] == item_id), None)
    if not me:
        return
    paths: dict[str, list[str]] = {}
    for r in bench:
        if r["top"] == me["top"] and r["cate"] not in paths:
            paths[r["cate"]] = (my_path if r["cate"] == me["cate"] and my_path else lookup(r["id"])).split(">")
    for r in bench:
        parts = paths.get(r["cate"])
        if parts and parts[0]:
            r["cateName"], r["topName"] = parts[-1], parts[0]


def _try(errors: list[dict[str, str]], part: str, fn, default=None):
    """取不到的部分记下来、报告照出；登录失效、风控、被带去别的页面就整个停下。"""
    try:
        return fn()
    except (LoginExpired, RiskStopped, Redirected):
        raise
    except (TbError, RuntimeError) as ex:
        errors.append({"part": part, "message": str(ex).splitlines()[0]})
        return default


def collect(item_id: str, days: int, end: date, compete: dict[str, Any] | None = None) -> dict[str, Any]:
    cookies = load_taobao_cookies()
    wins = windows(end, days)
    start = wins["对比周期"][0]
    errors: list[dict[str, str]] = []
    daily = fetch_series(lambda c, d: fetch_item_trend(c, item_id, d), cookies, end, start)
    if not daily:
        raise TbError(f"商品 {item_id} 没有取到每日数据。", endpoint=TREND_PATH, stage="取商品趋势",
                      hint="确认商品 ID 是当前登录店铺的商品。")
    shop = _try(errors, "店铺趋势", lambda: fetch_series(fetch_shop_trend, cookies, end, start), [])
    halves, flow = {}, {}
    for name, (a, b) in wins.items():
        ov = _try(errors, f"单品汇总（{name}）", lambda: fetch_item_preset(
            "item-sale-overview", item_id=item_id, start_date=a.isoformat(), end_date=b.isoformat(), cookies=cookies))
        rows = [r for r in daily if a.isoformat() <= r["d"] <= b.isoformat()]
        halves[name] = ({**overview_row(ov.get("data") or {}), "source": "生意参谋单品汇总（周期内去重）"} if ov
                        else {**sum_days(rows), "source": "按日相加（访客、买家没有去重）"})
        tree = _try(errors, f"流量来源（{name}）", lambda: fetch_item_preset(
            "item-flow-source", item_id=item_id, start_date=a.isoformat(), end_date=b.isoformat(), cookies=cookies))
        flow[name] = flow_rows((tree or {}).get("data"))
    a, b = wins["分析周期"]
    bench = _try(errors, "商品排行（同店对标）", lambda: fetch_bench(cookies, a, b), [])
    ly = (last_year(a), last_year(b))
    ov = _try(errors, "单品汇总（去年同期）", lambda: fetch_item_preset(
        "item-sale-overview", item_id=item_id, start_date=ly[0].isoformat(), end_date=ly[1].isoformat(), cookies=cookies))
    year_ago = overview_row(ov.get("data") or {}) if ov else {}
    deep = collect_deep(cookies, item_id, a, b, daily, lambda part, fn, default: _try(errors, part, fn, default))
    my_path = (deep.get("price") or {}).get("cate") or ""
    _try(errors, "同店商品的类目名", lambda: cate_names(bench, item_id, my_path, lambda iid: fetch_item_cate(item_id=iid, cookies=cookies)))
    search = _try(errors, "每天的搜索引导访客", lambda: {r["d"]: fetch_item_search(cookies, item_id, date.fromisoformat(r["d"]))
                                                   for r in daily}, {})
    add_search(daily, search)
    data = {
        "meta": {"item_id": item_id, "days": days, "end": end.isoformat(),
                 "periods": {k: [a.isoformat(), b.isoformat()] for k, (a, b) in wins.items()},
                 "generated": datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M"), "source": "生意参谋", "fields": FIELDS},
        "daily": daily, "shop_daily": shop, "halves": halves, "flow": flow, "bench": bench,
        # 去年同期：商品去年这几天没在卖（访客为 0）就不放
        "last_year": {**year_ago, "period": [d.isoformat() for d in ly]} if year_ago.get("uv") else None,
        "deep": deep, "compete": compete, "errors": errors,
    }
    data["anomalies"] = anomalies(daily)
    target = next((r for r in bench if r["id"] == item_id), None) or {}
    parts = my_path.split(">")
    data["meta"].update({"title": target.get("title") or "", "cate": target.get("cate") or "", "top": target.get("top") or "",
                         "cateName": parts[-1], "topName": parts[0]})
    data["facts"] = facts(data)
    return data


def anomalies(daily: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    """一个人平均买或加购 limit 件以上的日子：批发、测试单或拍错，会把件数和含这天的合计拉歪。"""
    out = []
    for r in daily:
        for what, people, pieces in (("买", r.get("byr"), r.get("itm")), ("加购", r.get("cartByr"), r.get("cart"))):
            if people and pieces and pieces / people >= limit:
                out.append({"d": r["d"], "what": what, "people": people, "pieces": pieces, "per": round(pieces / people)})
    return out


# ---------- 算好的对比（给 AI 写分析用，报告里也直接用） ----------

def pct(v: Any) -> str:
    return "-" if v is None else f"{v * 100:.2f}%"


def change(a: Any, b: Any, *, rate: bool = False) -> str:
    """对比周期 a → 分析周期 b。比率类写百分点，其余写变化百分比。"""
    if a is None or b is None:
        return "-"
    if rate:
        return f"{(b - a) * 100:+.2f} 个百分点"
    if not a:
        return "从 0 起" if b else "持平"
    return f"{(b / a - 1) * 100:+.1f}%"


def node(rows: list[dict[str, Any]], node_id: str) -> dict[str, Any]:
    return next((r for r in rows if r["id"] == node_id), {})


def channel_shares(flow: dict[str, list[dict[str, Any]]], halves: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """各周期的搜索、付费访客占商品访客的比例（一位访客可能从几个渠道进来，各渠道加起来会超过 100%）。"""
    out = {}
    for name in PERIODS:
        uv = halves[name].get("uv")
        rows = flow.get(name) or []
        se = node(rows, SEARCH)
        out[name] = {"seUv": se.get("uv"), "seCv": se.get("cv"), "seShare": _ratio(se.get("uv"), uv),
                     "paidShare": _ratio(node(rows, PAID).get("uv"), uv), "recShare": _ratio(node(rows, RECOMMEND).get("uv"), uv)}
    return out


def facts(data: dict[str, Any]) -> dict[str, Any]:
    h = data["halves"]
    a, b = h["对比周期"], h["分析周期"]
    days = data["meta"]["days"]
    ch = channel_shares(data["flow"], h)
    rows = [("访客数", "uv", False), ("支付金额", "amt", False), ("支付买家数", "byr", False), ("支付件数", "itm", False),
            ("支付转化率", "cv", True), ("客单价", "aov", False), ("加购率", "cartRate", True), ("加购人数", "cartByr", False),
            ("收藏人数", "clt", False), ("详情页跳出率", "bounce", True), ("平均停留时长（秒）", "stay", False),
            ("支付新买家数", "newb", False), ("支付老买家数", "oldb", False), ("推广花费", "charge", False),
            ("成功退款金额", "rfd", False)]
    show = lambda v, rate: pct(v) if rate else ("-" if v is None else round(v, 2))
    core = [{"指标": label, "对比周期": show(a.get(k), rate), "分析周期": show(b.get(k), rate),
             "变化": change(a.get(k), b.get(k), rate=rate)} for label, k, rate in rows]
    per = data["meta"]["periods"]
    se = {k: sum_days([r for r in data["daily"] if per[k][0] <= r["d"] <= per[k][1]]) for k in PERIODS}
    core.append({"指标": "搜索引导访客数", "对比周期": show(se["对比周期"]["seUv"], False), "分析周期": show(se["分析周期"]["seUv"], False),
                 "变化": change(se["对比周期"]["seUv"], se["分析周期"]["seUv"])})
    for label, k in (("搜索引导访客占比", "seShare"), ("搜索引导转化率", "seCv")):
        core.append({"指标": label, "对比周期": pct(se["对比周期"][k]), "分析周期": pct(se["分析周期"][k]),
                     "变化": change(se["对比周期"][k], se["分析周期"][k], rate=True)})
    for label, k in (("付费访客占比", "paidShare"), ("推荐访客占比", "recShare")):
        core.append({"指标": label, "对比周期": pct(ch["对比周期"][k]), "分析周期": pct(ch["分析周期"][k]),
                     "变化": change(ch["对比周期"][k], ch["分析周期"][k], rate=True)})
    out: dict[str, Any] = {
        "周期": {k: " ~ ".join(v) for k, v in data["meta"]["periods"].items()},
        "核心对比": core,
        "支付金额拆解": {"说明": "支付金额 = 访客数 × 支付转化率 × 客单价，下面是三个因子各自的变化",
                     "访客数": change(a.get("uv"), b.get("uv")), "支付转化率": change(a.get("cv"), b.get("cv")),
                     "客单价": change(a.get("aov"), b.get("aov")), "支付金额": change(a.get("amt"), b.get("amt"))},
        "推广花费占支付金额": {k: pct(_ratio(h[k].get("charge"), h[k].get("amt"))) for k in PERIODS},
        "整段": whole(data["daily"]),
        "首末对比": first_last(data["daily"]),
        "基线": baseline(data),
    }
    odd = data.get("anomalies") or []
    if odd:
        out["异常提醒"] = {"说明": "这几天一个人买或加购了很多件（批发、测试单或拍错），件数、加购件数和含这几天的合计不能直接比",
                       "日期": [f"{a['d']}：{a['people']} 人{a['what']}了 {a['pieces']} 件（平均每人 {a['per']} 件）" for a in odd]}
    shop = data.get("shop_daily") or []
    if shop:
        per = data["meta"]["periods"]
        amt = {k: sum(r.get("amt") or 0 for r in shop if per[k][0] <= r["d"] <= per[k][1]) for k in PERIODS}
        out["店铺"] = {"店铺支付金额变化": change(amt["对比周期"], amt["分析周期"]),
                     "本品占店铺支付金额": {k: pct(_ratio(h[k].get("amt"), amt[k])) for k in PERIODS}}
    out["同店位置"] = bench_position(data["bench"], data["meta"]["item_id"], days)
    ly = data.get("last_year")
    if ly:
        out["去年同期"] = {"周期": " ~ ".join(ly["period"]), "访客数": change(ly.get("uv"), b.get("uv")),
                       "支付金额": change(ly.get("amt"), b.get("amt")), "支付转化率": change(ly.get("cv"), b.get("cv"), rate=True),
                       "客单价": change(ly.get("aov"), b.get("aov"))}
    if data.get("deep"):
        out["深挖要点"] = deep_summary(data["deep"])
    return out


def whole(daily: list[dict[str, Any]]) -> dict[str, Any]:
    """两个周期连起来的整段（网页「结论摘要」的数）：按日相加，访客、买家没有去重。"""
    t = sum_days(daily)
    return {"日期": f"{daily[0]['d']} ~ {daily[-1]['d']}（{len(daily)} 天）", "说明": "两个周期连起来按日相加，访客、买家没有去重",
            "支付转化率": pct(t["cv"]), "加购率": pct(t["cartRate"]), "搜索引导访客占比": pct(t["seShare"]),
            "搜索引导转化率": pct(t["seCv"]), "退款率": pct(t["rfdRate"]), "详情页跳出率": pct(t["bounce"]),
            "平均停留时长（秒）": None if t["stay"] is None else round(t["stay"], 1)}


FIRST_LAST = [("访客数", "uv", False), ("支付金额", "amt", False), ("支付买家数", "byr", False), ("支付转化率", "cv", True),
              ("加购率", "cartRate", True), ("客单价", "aov", False), ("搜索引导访客数", "seUv", False),
              ("搜索引导访客占比", "seShare", True), ("详情页跳出率", "bounce", True), ("平均停留时长（秒）", "stay", False),
              ("支付新买家数", "newb", False), ("支付老买家数", "oldb", False)]


def first_last(daily: list[dict[str, Any]]) -> dict[str, Any]:
    """第一天和最后一天（网页「首末对比」表）。单日波动大，只当佐证。"""
    a, b = daily[0], daily[-1]
    show = lambda v, rate: pct(v) if rate else ("-" if v is None else round(v, 2))
    return {"说明": f"{a['d']}（第一天）和 {b['d']}（最后一天）比；单日波动大，只当佐证，主要看两个周期的对比",
            "指标": [{"指标": label, a["d"]: show(a.get(k), rate), b["d"]: show(b.get(k), rate),
                    "变化": change(a.get(k), b.get(k), rate=rate)} for label, k, rate in FIRST_LAST]}


def last_year(d: date) -> date:
    """去年的同一天（2 月 29 日退到 28 日）。"""
    try:
        return d.replace(year=d.year - 1)
    except ValueError:
        return d.replace(year=d.year - 1, day=28)


def baseline(data: dict[str, Any]) -> dict[str, Any]:
    """45 天方案和模拟器的起点：分析周期的日均访客、日均支付金额，周期转化率、客单价。"""
    b = data["halves"]["分析周期"]
    days = data["meta"]["days"]
    a0, a1 = data["meta"]["periods"]["分析周期"]
    se = sum_days([r for r in data["daily"] if a0 <= r["d"] <= a1])["seUv"]
    return {"日均访客": _r((b.get("uv") or 0) / days, 2), "日均支付金额": _r((b.get("amt") or 0) / days, 2),
            "支付转化率": b.get("cv"), "客单价": b.get("aov"), "加购率": b.get("cartRate"), "详情页跳出率": b.get("bounce"),
            "日均搜索引导访客": None if se is None else _r(se / days, 2)}


def bench_position(bench: list[dict[str, Any]], item_id: str, days: int) -> dict[str, Any]:
    if not bench:
        return {"说明": "没有取到商品排行"}
    me = next((r for r in bench if r["id"] == item_id), None)
    out: dict[str, Any] = {"取回商品数": len(bench)}
    if not me:
        out["说明"] = "本品不在取回的商品排行里（只取了按支付金额排前 60 的商品）"
        return out
    rank = lambda key: sorted(bench, key=lambda r: r.get(key) or 0, reverse=True).index(me) + 1
    out["本品支付金额排名"] = f"{rank('amt')}/{len(bench)}"
    out["本品访客排名"] = f"{rank('uv')}/{len(bench)}"
    floor = max(20, (me.get("uv") or 0) * 0.1)      # 访客太少的商品转化率不稳，不拿来当标杆
    group = [r for r in bench if r.get("top") == me.get("top")]
    same = [r for r in group if r["id"] != item_id and (r.get("uv") or 0) >= floor]
    out["同类目商品"] = f"和本品同一个一级类目的 {len(group)} 个（含本品），访客够多、能当标杆的 {len(same)} 个"
    out["标杆门槛"] = f"同一级类目、访客 ≥ {floor:.0f}"
    ranked = sorted(group, key=lambda r: r.get("cv") or 0, reverse=True)
    out["本品转化率在同类目的排名"] = f"{ranked.index(me) + 1}/{len(group)}"
    if same:
        out["同类目转化率中位数（访客够多的）"] = pct(median(r.get("cv") or 0 for r in same))
        best = max(same, key=lambda r: r.get("cv") or 0)
        out["同店最佳"] = {"id": best["id"], "类目": best.get("cateName") or best.get("cate"), "支付转化率": pct(best.get("cv")),
                       "加购率（加购件数÷访客）": pct(best.get("cartPerUv")), "访客数": best.get("uv"), "客单价": best.get("aov")}
    out["本品"] = {"类目": me.get("cateName") or me.get("cate"), "支付转化率": pct(me.get("cv")),
                 "加购率（加购件数÷访客）": pct(me.get("cartPerUv"))}
    return out
