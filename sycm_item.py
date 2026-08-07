"""生意参谋「商品」板块命令。只读。

与主模块的关系：参数拼装、护栏、cookie 读取全部复用 sycm_cli，
本模块只放商品域的 preset 定义与命令实现。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from sycm_cli import (
    _api_get,
    _infer_cc_date_type,
    _num,
    FIELDS_DICT,
    _print_scalar_block,
    _field_value,
    _dig,
    _sleep_humanlike,
    _value_of,
    build_query_params,
    load_taobao_cookies,
)

REFERER_ARCHIVES = "https://sycm.taobao.com/cc/item_archives"


def _now_ms() -> str:
    return str(int(time.time() * 1000))


def _yesterday() -> str:
    return (date.today() - timedelta(days=1)).isoformat()


def search_items(keyword: str, *, cookies: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """按商品标题 / 商品ID / 商品URL / 货号搜商品。无日期参数，是目录搜索。"""
    cookies = cookies or load_taobao_cookies()
    params = {
        "_": _now_ms(),
        "token": cookies.get("_tb_token_", ""),
        "keyword": keyword,
    }
    data = _api_get("/cc/common/item/search.json", params, cookies,
                    referer=REFERER_ARCHIVES)
    rows = data.get("data") or []
    # 跳过没有 id 的行：itemId="" 会被 resolve_item_id 当成有效值返回，
    # 后续请求就少了 itemId 参数，可能返回全店数据而不是这个单品。
    return [
        {
            "itemId": str(r["id"]),
            "itemNO": r.get("itemNO") or "",
            "title": r.get("title") or "",
            "price": r.get("price"),
            "stockCnt": r.get("stockCnt"),
            "url": r.get("url") or "",
        }
        for r in rows
        if r.get("id") not in (None, "")
    ]


def cmd_item_search(args: argparse.Namespace) -> None:
    rows = search_items(args.keyword)
    if args.out:
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2))
        print(f"已写入 {args.out}", file=sys.stderr)
        return
    if args.raw:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        print(f"# 没搜到商品：{args.keyword}")
        return
    print(f"# 搜到 {len(rows)} 个商品（关键词：{args.keyword}）")
    print("商品ID\t货号\t价格\t库存\t标题")
    for r in rows[: args.limit]:
        print(f"{r['itemId']}\t{r['itemNO']}\t{r['price']}\t{r['stockCnt']}\t{r['title'][:30]}")


def resolve_item_id(args: argparse.Namespace, *,
                     cookies: dict[str, str] | None = None) -> str:
    """从 --item-id 或 --search 解析出唯一 itemId。歧义时停，不猜。"""
    explicit = getattr(args, "item_id", None)
    if explicit:
        return str(explicit)

    keyword = getattr(args, "search", None)
    if not keyword:
        print("需要 --item-id <商品ID> 或 --search <货号/标题关键词>", file=sys.stderr)
        sys.exit(1)

    rows = search_items(keyword, cookies=cookies)
    if not rows:
        print(f"没搜到商品：{keyword}", file=sys.stderr)
        sys.exit(1)
    if len(rows) > 1:
        print(f"「{keyword}」命中 {len(rows)} 个商品，请用 --item-id 指定其中一个：",
              file=sys.stderr)
        for r in rows[:20]:
            print(f"  {r['itemId']}\t{r['itemNO']}\t{r['title'][:30]}", file=sys.stderr)
        if len(rows) > 20:
            print(f"  …… 还有 {len(rows) - 20} 个未列出（搜索最多返回 50 个）",
                  file=sys.stderr)
        sys.exit(1)
    return rows[0]["itemId"]


def _add_item_args(parser: Any, yesterday: str) -> None:
    """单品命令的公共参数。"""
    parser.add_argument("--item-id", help="商品 ID")
    parser.add_argument("--search", help="按货号/标题关键词搜（命中唯一才继续）")
    parser.add_argument("--date", default=yesterday, help="YYYY-MM-DD (默认昨天)")
    parser.add_argument("--end-date", help="结束日期（默认 = --date）")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--raw", action="store_true")
    parser.add_argument("--out")


ITEM_PRESETS: dict[str, dict[str, Any]] = {
    "item-sku-list": {
        "path": "/cc/item/sale/sku/list.json",
        "param_style": "cc-v2",
        "orderBy": "cartCnt",
        "indexCode": "cartCnt,payAmt,payItmCnt,payByrCnt",
        "extra_params": {"device": "0"},
        "referer": REFERER_ARCHIVES,
        "desc": "单品 SKU 组合销售明细（哪个尺码/颜色卖得动），认 --date",
        # 之前录到的 /cc/live/v2/item/sale/sku/list.json 是「实时」接口——网页
        # 时间选择器停在「实时」档时页面走的那一套，写死当天，忽略传入日期。
        # 实测（2026-08-05）纠正：换成不带 live/v2 的 /cc/item/sale/sku/list.json
        # 后，recent30（2026-07-06~08-04）与 recent7（2026-07-29~08-04）两次
        # 调用返回的数值不同，是认日期的。之前挂在这里的"本接口忽略日期"结论
        # 是错的，已删除。
        # 实测（2026-08-05）：indexCode 加上 currentStockCnt/sellRate/stockDays
        # 会被静默丢弃（不报错，行里就是没有这三个字段）——这个日期口径接口不
        # 支持库存类指标，那是 live 接口才有的即时快照字段，两边不能混用。
        # 实测（2026-08-05）：data 是分页信封 {recordCount, data}，行列表在
        # data.data（比 live 接口少一层，别照抄 data.data.data）。
        "list_path": "data.data",
        "show": ["skuName", "cartCnt", "payAmt", "payItmCnt", "payByrCnt"],
    },
    "item-sku-list-live": {
        "path": "/cc/live/v2/item/sale/sku/list.json",
        "param_style": "cc-v2",
        "orderBy": "cartCnt",
        "indexCode": "cartCnt,payAmt,payItmCnt,payByrCnt,currentStockCnt,sellRate,stockDays",
        "extra_params": {"device": "0"},
        "referer": REFERER_ARCHIVES,
        "desc": "单品 SKU 实时库存快照（现有库存/售罄率/库存可售天数），--date 会被忽略",
        # --live 专用：这就是当年被误当成「item-sku-list 的日期口径版本」而错误
        # 顶替过一次的实时接口（见 item-sku-list 的注释）。现在换回来只做它
        # 真正该做的事——库存快照，不再冒充认日期的销售明细。
        # 实测（2026-08-05，真实商品，itemId 已脱敏为占位）：比认日期的
        # /cc/item/sale/sku/list.json 多一层信封——
        # data:{updateTime, interval, data:{recordCount, data:[...]}, timestamp}，
        # 行列表在 data.data.data（三层），别照抄两层那个的 data.data。
        # 实测（2026-08-05）：把 dateRange 从当天换成 2026-07-01，updateTime
        # （墙钟时间）和所有行的数值都不变——是真·实时快照，不认 --date /
        # --end-date，传什么都没用。
        # 实测（2026-08-05）：currentStockCnt / sellRate / stockDays 三个字段
        # 在这个接口上是裸标量（不像 cartCnt/payAmt 那样包 {value,...}）；
        # _value_of 对裸标量和包装值都能正确取出，渲染层不用额外处理。
        "list_path": "data.data.data",
        "show": ["skuName", "cartCnt", "payAmt", "payItmCnt", "payByrCnt",
                 "currentStockCnt", "sellRate", "stockDays"],
    },
    "item-sku-attr": {
        "path": "/cc/item/sale/sku/attrDetail.json",
        "param_style": "cc-v2",
        "orderBy": "payAmt",
        "indexCode": "payAmt,payAmtRatio,payItmCnt,payByrCnt,payByrCntRatio",
        "extra_params": {"device": "0"},
        "referer": REFERER_ARCHIVES,
        "desc": "单品按属性聚合销售（尺码/颜色等维度，网页「属性分析」表），认 --date",
        # 实测（2026-08-05，attrName=尺码，recent30）：返回 6 行，与网页「商品
        # 360 → 销售分析 → 属性分析」表格逐格一致（XL 9497.79/64件/57人 等）。
        # attrName 的取值来自商品自身的属性名，不写死枚举——服务端不认的属性
        # 名会自己报错，交给它判断即可。
        "list_path": "data.data",
        "show": ["attrValue", "payAmt", "payAmtRatio", "payItmCnt",
                  "payByrCnt", "payByrCntRatio"],
    },
    "item-flow-source": {
        "path": "/flow/item/source/tree/support.json",
        "param_style": "cc-v2",
        "orderBy": "uv",
        "indexCode": "uv,pv,cltItmCnt,cartByrCnt,payByrCnt,payItmCnt,payAmt,payRate,payPct",
        "extra_params": {"flowBizType": "classic",
                          "activateBoost": "sourceChannel", "crowdType": "all"},
        "referer": REFERER_ARCHIVES,
        "desc": "单品流量来源树（访客从哪来、哪个渠道转化差）",
        "list_path": "data",
        "show": ["_path", "uv", "pv", "cltItmCnt", "cartByrCnt",
                  "payByrCnt", "payAmt", "payRate"],
    },
    "item-refund-reason": {
        "path": "/csp/api/refund/item/reason/list/v2.json",
        "param_style": "cc-v2",
        "orderBy": "itemSucRfdByr",
        # rfdIntervalLevel 是必填（缺了 code=1003，空字符串也被拒）。
        #
        # **值必须是 99，不是 "ALL"**（2026-08-06 从页面请求录得后实测确认：
        # 同一组参数下 ALL → 0 行、99 → 8 行）。"ALL" 服务端照收、不报错、
        # 静默返回空列表 —— 这就是下面那段「查了两天没查出来」的全部原因。
        # 是本项目第八次撞上「参数照收、结果静默变空」。
        #
        # 教训：当时我在文档里写「试过 rfdIntervalLevel」，其实只试了自己猜的
        # 那一个值就当成试过了。**猜的参数值必须去页面上录真值，不能只验"传了
        # 不报错"。**
        #
        # sku/list、prop/list 两个兄弟接口不需要这个参数（不传也 code=0），
        # 别顺手加过去。
        "extra_params": {"refundDateType": "pay", "caseScene": "ALL",
                          "rfdIdentifyType": "alg_identify",
                          "rfdIntervalLevel": "99"},
        # 历史：2026-08-05 这张表稳定返回 code=0 + 空列表，当时排查过
        # rfdIdentifyType / caseScene / refundDateType / orderBy / 多个日期窗口，
        # 全部仍空且不报错，结论只能定性为「未确定」。2026-08-06 从页面录到真实
        # 请求才发现真凶是 rfdIntervalLevel 的值 —— 见上。**当初排查方向没错，
        # 错在只试了自己猜的参数值就认为「试过了」。**
        "referer": REFERER_ARCHIVES,
        "desc": "单品退款原因分布",
        # 实测（2026-08-05）：这个接口的 data 本身就是行列表（没有 data.data
        # 分页信封），跟同域其它退款接口的形状不一样，别按同类接口的规律推。
        "list_path": "data",
        # rfdReasonNameCn 是中文原因名（rfdReasonName 是英文码）；金额字段是
        # itemRfdAmt —— itemSucRfdAmt 这个名字在响应里根本不存在，恒为 None。
        # rfdReasonTypeCn 分「内部原因 / 消费者原因」，是这张表最该先看的一列：
        # 内部原因才是自己能改的。
        # lossByrCnt = 因这个原因流失到竞店的人数（2026-08-06 与页面「流失至
        # 竞店人数」列核对）。比单纯的退款人数更有指向性：退了还留在店里、
        # 和退了直接去买别家，是两回事。
        # 注：每行还带 children（子原因，如「商品问题」下的描述不符/材质问题/
        # 做工问题/质量缺陷），本命令暂不展开，需要时用 --raw 看。
        "show": ["rfdReasonTypeCn", "rfdReasonNameCn", "itemSucRfdByr",
                  "lossByrCnt", "itemRfdAmt", "payAmtRfdRate"],
    },
    "item-refund-sku": {
        "path": "/cc/refund/item/sku/list.json",
        "param_style": "cc-v2",
        "orderBy": "itemSkuSucRfdByr",
        "extra_params": {"refundDateType": "pay"},
        "referer": REFERER_ARCHIVES,
        "desc": "单品各 SKU 退款（哪个尺码/颜色退得多）",
        "list_path": "data.data",
        # 实测（2026-08-05）：真实字段是 itemSkuRfdAmt，不是 itemSkuSucRfdAmt
        # （该名字不存在）。payAmtRfdRate / ordRfdRate 是平台自算的退款率，
        # 随行带着自己的分母（payOrdCnt / payAmt）一起返回，展示平台自己的
        # 比率没问题——项目规矩禁止的是我们自己拿错配的分子分母去算比率。
        "show": ["skuName", "itemSkuSucRfdByr", "itemSkuRfdAmt",
                  "payAmtRfdRate", "ordRfdRate"],
    },
    "item-refund-prop": {
        "path": "/cc/refund/item/prop/list.json",
        "param_style": "cc-v2",
        "orderBy": "itemPropRfdSucByr",
        "extra_params": {"refundDateType": "pay", "caseScene": "ALL"},
        "referer": REFERER_ARCHIVES,
        "desc": "单品各属性退款",
        "list_path": "data.data",
        # 实测（2026-08-05）：propName 是属性名（四行全是「尺码」），属性的
        # 具体值在 valueName（2XL / XL / 3XL / L）。只展示 propName 的话整张
        # 表看不出是哪个尺码退得多，命令的目的就落空了。
        "show": ["propName", "valueName", "itemPropRfdSucByr",
                  "itemPropRfdSucAmt"],
    },
    "item-diagnose-core": {
        "path": "/cc/diagnose/coreIndex.json",
        "param_style": "cc-v2",
        "orderBy": "payAmt",
        "extra_params": {"crowdType": "all"},
        "referer": REFERER_ARCHIVES,
        "desc": "单品诊断核心指标（本店值 + 环比 + 未核实的 cmpt 对比值）",
        "list_path": "data",
    },
    "item-sale-overview": {
        "path": "/cc/item/sale/overview.json",
        "param_style": "cc-v2",
        "orderBy": "payAmt",
        "extra_params": {"device": "0"},
        "referer": REFERER_ARCHIVES,
        "desc": "单品销售总览，认 --date",
        # 之前录到的 /cc/live/item/sale/overview.json 也是「实时」接口，同一个
        # bug 根源：侦查时页面停在「实时」时间档。实测（2026-08-05）纠正：换成
        # 不带 live/ 的 /cc/item/sale/overview.json 后，recent30
        # （2026-07-06~08-04，payAmt=31475.15）与 recent7（2026-07-29~08-04，
        # payAmt=8100.68）两次调用返回的数值不同，是认日期的。之前挂在这里的
        # "本接口忽略日期、只给实时快照"结论是错的，已删除。
        # 实测（2026-08-05）：data 本身就是指标的扁平 dict（跟 diagnose/coreIndex
        # 一个形状），没有 data.data 这层分页信封——每个字段是 {value, cycleCrc}，
        # 取 data.data 会拿到 None。
        "list_path": "data",
    },
}


def fetch_item_preset(name: str, *, item_id: str, start_date: str, end_date: str,
                       page_no: int = 1, page_size: int = 10,
                       cookies: dict[str, str] | None = None,
                       extra: dict[str, str] | None = None) -> dict[str, Any]:
    preset = ITEM_PRESETS[name]
    cookies = cookies or load_taobao_cookies()
    params = build_query_params(
        preset, start_date=start_date, end_date=end_date,
        page_no=page_no, page_size=page_size,
        token=cookies.get("_tb_token_", ""),
        extra={"itemId": item_id, **(extra or {})},
    )
    params["_"] = _now_ms()
    return _api_get(preset["path"], params, cookies, referer=preset["referer"])


def _record_count(raw: Any) -> int | None:
    """服务端说的总行数。data 是裸列表的接口（如退款原因）没有这个字段。"""
    data = (raw or {}).get("data")
    return data.get("recordCount") if isinstance(data, dict) else None


# 服务端每页真实上限。/cc/refund/item/sku/list.json 实测封顶 5 行 ——
# pageSize 传 100 也只回 5，传 5 翻三页才能取满 recordCount=12。
# 翻页要发额外请求，上限防跑飞。
_MAX_PAGES = 6


def fetch_item_rows(name: str, *, item_id: str, start_date: str, end_date: str,
                     want: int, cookies: dict[str, str],
                     sleep_first: bool = True) -> tuple[list[Any], int | None]:
    """取一张明细表，服务端每页封顶时自动翻页补齐到 want 行。

    2026-08-07 取证：`/cc/refund/item/sku/list.json` 无视 pageSize，每页最多
    回 5 行。原来只发一次请求、还把「本页行数」当「总行数」打印，于是 12 个
    SKU 只显示 5 个、表头写「共 5 行」——看的人根本不知道少了 7 个，
    还会拿这 5 行去和另外两张表对账，怎么对都对不上。
    """
    preset = ITEM_PRESETS[name]
    rows: list[Any] = []
    total: int | None = None
    for page in range(1, _MAX_PAGES + 1):
        if sleep_first or page > 1:
            _sleep_humanlike()
        sleep_first = True
        raw = fetch_item_preset(name, item_id=item_id, start_date=start_date,
                                 end_date=end_date, page_no=page,
                                 page_size=max(want, 10), cookies=cookies)
        total = _record_count(raw) if page == 1 else total
        page_rows = _dig(raw, preset["list_path"]) or []
        if not isinstance(page_rows, list):
            return page_rows, total          # 交给 _print_rows 报类型错
        rows.extend(page_rows)
        # 只在服务端明确给了 recordCount 时才翻页。没有总数就不翻 ——
        # 「本页比 pageSize 少」在这里不能当终止条件（服务端本来就无视
        # pageSize，永远只给 5 行），而盲翻会把同一页重复取回来。
        if not page_rows or total is None or len(rows) >= min(total, want):
            break
    else:
        # 撞上 _MAX_PAGES 封顶。必须说出来 —— 否则表头会照常建议
        # 「要全部请加 --limit N」，而加了也没用，等于给假指路。
        print(f"# 注意：{preset['path']} 每页只回几行，翻满 {_MAX_PAGES} 页后仍未取全"
              f"（已取 {len(rows)} 行，服务端说共 {total} 行）。加 --limit 也不会更多，"
              f"这是本地翻页上限，防止请求跑飞。", file=sys.stderr)
    return rows, total


# 表里我们自己拼出来的合成列，字典里没有（字典只收服务端字段码）。
_SYNTHETIC_COLS = {"_path": "来源路径"}


def _col_label(code: str) -> str:
    """表头用中文名。字典里没有的字段码原样打出来 —— 不猜中文名。

    2026-08-07：在此之前表头直打字段码，`attrValue / payAmtRatio / itemSkuRfdAmt`
    这种谁也看不懂。中文名和展示格式 fields.json 里本来就有（cn + fmt 两列），
    渲染层查字典就行，不该在代码里再抄一份。
    """
    if code in _SYNTHETIC_COLS:
        return _SYNTHETIC_COLS[code]
    entry = FIELDS_DICT.get(code)
    return (entry or {}).get("cn") or code


def _cell(value: Any, code: str | None = None) -> str:
    """一个单元格的展示文本。

    2026-08-07：本来这里自己写了一遍「比率打百分比 / 整数不带小数」的逻辑，
    和 sycm_cli._field_value 是同一件事的两份实现 —— 而且这边少了 epoch_ms
    和 Rate 后缀兜底两条分支，同一个字段在两种表里会渲染成不同样子。
    合成一个，这里只做转发。
    """
    return _field_value(code or "", value)


def _print_rows(preset: dict[str, Any], rows: Any, limit: int,
                 header: str, total: int | None = None) -> None:
    """打印一张明细表。rows 必须是 list——list_path 配错时常会取到 dict，
    之前直接 rows[:limit] 会甩出让人摸不着头脑的 KeyError: slice(...)。
    这里先校验类型，报清楚是哪个 preset、哪个 list_path、实际拿到什么类型，
    这样下次同类 bug 能一眼定位，不用再翻 traceback。"""
    if not isinstance(rows, list):
        print(f"# {header}", file=sys.stderr)
        print(
            f"取数失败：preset.path={preset.get('path', '?')} "
            f"list_path={preset.get('list_path', '?')!r} 没取到列表，"
            f"实际拿到 {type(rows).__name__}。多半是 list_path 配错了层级，"
            f"用 --raw 看真实响应形状再核对。",
            file=sys.stderr,
        )
        sys.exit(1)
    shown = min(len(rows), limit)
    if total is not None and total > shown:
        # 表头必须说服务端的总数。拿「本页行数」冒充「共 N 行」会让人以为看全了。
        print(f"# {header}  共 {total} 行，这里显示 {shown} 行"
              f"（要全部请加 --limit {total}）")
    else:
        print(f"# {header}  共 {len(rows)} 行")
    cols = preset["show"]
    print("\t".join(_col_label(c) for c in cols))
    for row in rows[:limit]:
        # 缺列打空白，不打字面量 "None"：流量来源树的行合法地会缺列
        # （父节点没有子渠道才有的指标），一屏 None 反而盖住真数据。
        print("\t".join(_cell(row.get(c), c) for c in cols))


def _run_item_list_cmd(name: str, args: argparse.Namespace, header_fmt: str,
                        *, extra: dict[str, str] | None = None,
                        header_kwargs: dict[str, Any] | None = None) -> None:
    cookies = load_taobao_cookies()
    item_id = resolve_item_id(args, cookies=cookies)
    end = args.end_date or args.date
    data = fetch_item_preset(name, item_id=item_id, start_date=args.date,
                              end_date=end, page_no=args.page,
                              page_size=args.limit, cookies=cookies, extra=extra)
    if args.out:
        Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"已写入 {args.out}", file=sys.stderr)
        return
    if args.raw:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    preset = ITEM_PRESETS[name]
    rows = _dig(data, preset["list_path"]) or []
    header = header_fmt.format(item_id=item_id, date=args.date, **(header_kwargs or {}))
    _print_rows(preset, rows, args.limit, header)
    if preset.get("caliber_note"):
        print(f"# {preset['caliber_note']}")


def cmd_item_sku_list(args: argparse.Namespace) -> None:
    by = getattr(args, "by", None)
    live = getattr(args, "live", False)
    if live:
        # currentStockCnt/sellRate/stockDays 只有这个实时接口才有；认日期的
        # /cc/item/sale/sku/list.json 实测会静默丢弃这三个字段（见该 preset
        # 注释），两边不能互相替代，所以要明确告诉用户日期参数不生效，别让人
        # 以为查到的是所选日期那天的库存。
        print("# 注意：--live 是当前实时库存快照，--date/--end-date 不生效——"
              "现有库存/售罄率/库存可售天数只有这个实时接口才有，认日期的接口"
              "拿不到这三个字段。", file=sys.stderr)
        _run_item_list_cmd("item-sku-list-live", args,
                            "SKU 实时库存快照  商品 {item_id}（当前快照，--date 已忽略）")
        return
    if by:
        _run_item_list_cmd("item-sku-attr", args,
                            "属性聚合（{attr}）  商品 {item_id}  {date}",
                            extra={"attrName": by}, header_kwargs={"attr": by})
        return
    _run_item_list_cmd("item-sku-list", args, "SKU 销售明细  商品 {item_id}  {date}")


def flatten_source_tree(rows: list[dict[str, Any]], depth: int = 0,
                         prefix: str = "") -> list[dict[str, Any]]:
    """把流量来源树递归展平，保留层级与路径。"""
    flat: list[dict[str, Any]] = []
    for row in rows or []:
        name = str(_value_of(row.get("pageName")) or "")
        path = f"{prefix} > {name}" if prefix else name
        node = {k: v for k, v in row.items() if k != "children"}
        node["_level"] = depth
        node["_path"] = path
        flat.append(node)
        children = row.get("children")
        if children:
            flat.extend(flatten_source_tree(children, depth + 1, path))
    return flat


def cmd_item_flow_source(args: argparse.Namespace) -> None:
    cookies = load_taobao_cookies()
    item_id = resolve_item_id(args, cookies=cookies)
    end = args.end_date or args.date
    data = fetch_item_preset("item-flow-source", item_id=item_id,
                              start_date=args.date, end_date=end,
                              page_no=args.page, page_size=args.limit,
                              cookies=cookies)
    if args.out:
        Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"已写入 {args.out}", file=sys.stderr)
        return
    if args.raw:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    preset = ITEM_PRESETS["item-flow-source"]
    rows = flatten_source_tree(_dig(data, preset["list_path"]) or [])
    _print_rows(preset, rows, args.limit,
                f"流量来源  商品 {item_id}  {args.date}")


REFUND_SECTIONS = [
    ("item-refund-reason", "退款原因"),
    ("item-refund-sku", "各 SKU 退款"),
    ("item-refund-prop", "各属性退款"),
]


def cmd_item_refund(args: argparse.Namespace) -> None:
    """一条命令拉齐退款原因 / SKU / 属性三张表。"""
    cookies = load_taobao_cookies()
    # --search 会先发一次搜索请求，那之后紧接着的第一次取数也要隔开。
    already_requested = not getattr(args, "item_id", None)
    item_id = resolve_item_id(args, cookies=cookies)
    end = args.end_date or args.date
    bundle: dict[str, Any] = {}
    totals: dict[str, int | None] = {}
    for name, _ in REFUND_SECTIONS:
        # 风控是本项目第一条护栏，突发流量正是触发方式；仓库里所有多请求路径
        # 都走 _sleep_humanlike（1.8~3.5s），CLI 的警告文案也是这么宣称的。
        rows, total = fetch_item_rows(name, item_id=item_id,
                                       start_date=args.date, end_date=end,
                                       want=args.limit, cookies=cookies,
                                       sleep_first=already_requested)
        already_requested = True
        bundle[name] = rows
        totals[name] = total
    if args.out:
        Path(args.out).write_text(json.dumps(bundle, ensure_ascii=False, indent=2))
        print(f"已写入 {args.out}", file=sys.stderr)
        return
    if args.raw:
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
        return
    print(f"# 单品退款归因  商品 {item_id}  {args.date} ~ {end}")
    print("# 口径：按原订单付款时间(refundDateType=pay)。这是退款事件归属，"
          "不是退货率——真实退货率要用同一付款批次的支付订单数作分母。")
    # 成熟度警告：各 SKU 表里展示的 payAmtRfdRate / ordRfdRate 是平台自算的
    # 支付时间口径退款率，fields.json 对这两个字段记着「近 7 天数值仍在爬升
    # (实测 T-6 仍未长完)」。本命令 --date 默认昨天，正落在这个禁区里。
    print("# 成熟度：payAmtRfdRate / ordRfdRate 是支付时间口径，近 7 天数值仍在"
          "爬升（实测 T-6 仍未长完）。--date 默认昨天正落在这个区间，"
          "别用近 7 天的退款率下结论，至少把窗口往前推 7 天再看。\n")
    for name, title in REFUND_SECTIONS:
        preset = ITEM_PRESETS[name]
        rows = bundle[name]
        _print_rows(preset, rows, args.limit, title, totals.get(name))
        if name == "item-refund-reason" and rows:
            # 2026-08-07 取证：rfdIdentifyType=alg_identify 会给一笔退款打上
            # 多个原因标签。同款同窗口实测：原因表退款单数合计 168，属性表只有
            # 122，而两张表的分母 payOrdCnt 都是 211（同一个订单集合）。
            # 所以三张子表的人数天然对不齐 —— 不是取数少了，是口径不同。
            print("# 口径：一笔退款会被算法打上多个原因标签，所以**各行不可相加**"
                  "——按原因求和会重复计数，得不到唯一退款人数。"
                  "要唯一人数请看「各属性退款」（同一订单只落一个尺码）。")
        if name == "item-refund-reason" and not rows:
            # 调查记录见 ITEM_PRESETS["item-refund-reason"] 的注释：同一次调用
            # 2026-08-05~06 这张表曾长期返回 0 行，真凶是 rfdIntervalLevel
            # 传了自己猜的 "ALL"（服务端照收不报错、静默返空），正确值是 99。
            # 已修。现在如果还空，就是这个商品/窗口真的没有归因数据了。
            print("# 注：本表为空。参数已按页面实际请求固定"
                  "（rfdIntervalLevel=99 / rfdIdentifyType=alg_identify / "
                  "refundDateType=pay），空表通常意味着该商品在这个时间窗口内"
                  "确实没有算法归因出的退款原因。可换更长的时间窗口再看。")
        print()


# coreIndex 的对比字段后缀。实测（2026-08-05，/cc/diagnose/coreIndex.json）：
# - payAmt 的同行值字段名是 payAmtItemCmpt，不是 payAmtCmpt。
# - uv 这个指标同行字段叫 itmUvCmpt（不是 uvCmpt），环比字段叫 itemUvCrc
#   （不是 uvCrc）——同一个指标三种词干（uv / itmUv / itemUv）混用，别按规律推。
_CMPT_ALIASES = {"payAmt": "payAmtItemCmpt", "uv": "itmUvCmpt"}
_CRC_ALIASES = {"uv": "itemUvCrc"}


def split_compare_fields(row: dict[str, Any]) -> dict[str, Any]:
    """把 <code> / <code>Crc / <code>Cmpt / <code>CmptCrc 四件套归并成一组。

    实测 coreIndex.json 的 40 个字段全部是 {"value": ...} 包裹（没有裸标量），
    所以这里用 _value_of 统一解包，而不是靠 isinstance 排除 dict——dict 才是
    正常指标形状，排除它就等于把所有指标都过滤掉了。
    """
    meta_keys = {"itemId", "statDate", "userId", "userType", "crowdType",
                 "dateType", "indexName", "indexRelaDiff"}
    base_codes = [
        k for k in row
        if k not in meta_keys
        and not k.endswith(("Crc", "Cmpt"))  # "CmptCrc" 已被 "Crc" 覆盖
        and not isinstance(row[k], list)
    ]
    grouped: dict[str, Any] = {}
    for code in base_codes:
        crc_key = _CRC_ALIASES.get(code, f"{code}Crc")
        cmpt_key = _CMPT_ALIASES.get(code, f"{code}Cmpt")
        grouped[code] = {
            "value": _value_of(row.get(code)),
            "crc": _value_of(row.get(crc_key)),
            "cmpt": _value_of(row.get(cmpt_key)),
            "cmptCrc": _value_of(row.get(f"{cmpt_key}Crc")),
        }
    grouped["_meta"] = {k: _value_of(row[k]) for k in meta_keys if k in row}
    return grouped


def cmd_item_360(args: argparse.Namespace) -> None:
    """单品总体面貌：诊断核心指标（带同行对比）+ 销售总览。"""
    cookies = load_taobao_cookies()
    already_requested = not getattr(args, "item_id", None)  # --search 先发过一次
    item_id = resolve_item_id(args, cookies=cookies)
    end = args.end_date or args.date
    if already_requested:
        _sleep_humanlike()
    core = fetch_item_preset("item-diagnose-core", item_id=item_id,
                              start_date=args.date, end_date=end,
                              cookies=cookies)
    _sleep_humanlike()
    overview = fetch_item_preset("item-sale-overview", item_id=item_id,
                                  start_date=args.date, end_date=end,
                                  cookies=cookies)
    bundle = {"core": core, "overview": overview}
    if args.out:
        Path(args.out).write_text(json.dumps(bundle, ensure_ascii=False, indent=2))
        print(f"已写入 {args.out}", file=sys.stderr)
        return
    if args.raw:
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
        return

    print(f"# 商品 360  商品 {item_id}  {args.date}"
          + (f" ~ {end}" if end != args.date else ""))
    # 取数层级一律走 preset["list_path"]，不再在命令里写字面量：本分支实测到的
    # 六个 bug 全是嵌套层级配错，层级只能有一个真相来源。
    core_row = _dig(core, ITEM_PRESETS["item-diagnose-core"]["list_path"])
    if isinstance(core_row, list):
        core_row = core_row[0] if core_row else {}
    grouped = split_compare_fields(core_row or {})
    # 实测（2026-08-05）：*Cmpt 不是同行的绝对值——本店 payAmt / uv 都是三四位
    # 数时，对应的 cmpt 只有零点几，量级对不上（cmpt 全落
    # 在 0-1）。它大概率是某种归一化/位次类对比指标，具体口径没验证过，标成
    # "同行"会断言一个我们证不了的口径，所以改成不下定义的中性名。
    print("\n## 核心指标（本店 / 环比 / cmpt对比值 / cmpt对比环比）")
    print("指标\t本店\t环比\tcmpt对比值\tcmpt对比环比")
    for code, g in grouped.items():
        if code == "_meta":
            continue
        # 比率类打成百分比：0.006628003314001657 这种裸小数没法读。
        # 判据用字段名后缀，不猜中文名——中文名没跟页面核过，不写。
        is_rate = code.endswith("Rate")
        fmt = _pct if is_rate else _num
        print(f"{code}\t{fmt(g['value'])}\t{_pct(g['crc'])}"
              f"\t{_num(g['cmpt'])}\t{_pct(g['cmptCrc'])}")
    print("\n注：cmpt对比值/cmpt对比环比 的口径未核实——不是同行的绝对值"
          "（数量级对不上本店值），具体代表什么暂时没验证，别当同行绝对值解读。")

    ov_preset = ITEM_PRESETS["item-sale-overview"]
    print(f"\n## 销售总览（{args.date}" + (f" ~ {end}" if end != args.date else "") + "）")
    # 实测 /cc/item/sale/overview.json 的 data 本身就是指标扁平 dict
    # （跟 diagnose/coreIndex 一个形状），没有 data.data 分页信封那层。
    ov = _dig(overview, ov_preset["list_path"])
    if isinstance(ov, list):
        ov = ov[0] if ov else {}
    if not isinstance(ov, dict):
        ov = {}
    # 列名和格式统一查 fields.json（2026-08-07）——原来这里按 k.endswith("Rate")
    # 猜比率、其余一律 _num，于是 statDate 打成毫秒时间戳、字段码原样上屏。
    _print_scalar_block(ov)


# ---------- 客群洞察 ----------
#
# 三个约束全部来自 2026-08-06 对 /cc/item/archive/profile.json 的实测：
#   1. profileType 必填。服务端报错会把白名单列全，下面 10 个照抄。
#      注意：报错原文会被截断（第一次只回到 "brand_pref" 就断了，真值是
#      "brand_prefer"），别拿截断的清单当全集。
#   2. crowdsType 3 个值，但只有 itmUv 回得出数据；另外两个恒空，原因未定。
#   3. **只认单日**。传 recent7/recent30 服务端照收 code=0，静默返空数组——
#      是本项目第五次遇到「参数照收、结果静默变空」，所以在客户端直接拦掉。

PROFILE_TYPES: dict[str, str] = {
    "crowd": "人群标签",
    "age": "年龄",
    "gender": "性别",
    "new_old": "新老客",
    "province": "省份",
    "city": "城市",
    "brand_prefer": "品牌偏好",
    "cate_prefer": "类目偏好",
    "purchase_level": "预测消费层级",
    "tq": "淘气值",
}

CROWD_TYPES: dict[str, str] = {
    "itmUv": "访问人群",
    "payByrCnt": "成交人群",
    "appSearchUv": "搜索人群",
}

# itmUv 之外的两种实测恒空。原因 2026-08-06 已查明（用户在页面上读到原文）：
#
#   「本店商品人群样本量小于 300 人，不统计客群画像」
#
# 是平台的样本量门槛，不是缺参数、也不是平台没这份数据。要命的是本接口
# **只认单日**（见下），没法靠拉长窗口把人数攒过 300 —— 所以支付人群 /
# 搜索人群画像实际上只有单日就能跑到 300+ 的大流量款才出得来。
CROWD_TYPES_WITH_DATA = ("itmUv",)

CROWD_SAMPLE_FLOOR = 300

# 代码值 → 中文。只放已跟页面核对过的：2026-08-06 用户截图核对「新老占比」
# 环形图，新客户 54.97% 对上 Y=54.97%，故 Y=新客户、N=老客户。
CODE_VALUE_CN: dict[str, dict[str, str]] = {
    "new_old": {"Y": "新客户", "N": "老客户"},
}

# 取值是代码、含义还没跟页面核对过的维度。宁可原样显示也不猜译。
# 目前为空 —— 有新的代码型维度先进这里，核对后再挪去 CODE_VALUE_CN。
UNVERIFIED_CODE_DIMS: dict[str, str] = {}

# 页面上同样取不到数的维度（已核对，不是 CLI 少传参数）。
# brand_prefer：2026-08-06 用户截图确认「浏览品牌偏好」十行占比全是 "-"。
PAGE_CONFIRMED_EMPTY_DIMS = ("brand_prefer",)


def fetch_item_profile(*, item_id: str, date: str, profile_type: str,
                        crowds_type: str,
                        cookies: dict[str, str] | None = None) -> list[dict[str, Any]]:
    cookies = cookies or load_taobao_cookies()
    params = {
        "_": _now_ms(),
        "token": cookies.get("_tb_token_", ""),
        "itemId": item_id,
        "dateRange": f"{date}|{date}",
        "dateType": "day",
        "device": "0",
        "profileType": profile_type,
        "crowdsType": crowds_type,
    }
    payload = _api_get("/cc/item/archive/profile.json", params, cookies,
                       referer=REFERER_ARCHIVES)
    return payload.get("data") or []


def _print_profile_table(rows: list[dict[str, Any]], dim: str,
                          crowds_type: str, limit: int) -> None:
    metric_cn = CROWD_TYPES[crowds_type]
    print(f"\n## {PROFILE_TYPES[dim]}（{dim}） — {metric_cn}")
    if not rows:
        if crowds_type in CROWD_TYPES_WITH_DATA:
            print("（无数据）")
        else:
            print(f"（空）原因：平台规则「本店商品人群样本量小于 "
                  f"{CROWD_SAMPLE_FLOOR} 人，不统计客群画像」（2026-08-06 页面原文）。"
                  f"本接口只认单日，没法靠拉长时间窗口攒够人数——{metric_cn}画像"
                  f"实际上只有单日就能到 {CROWD_SAMPLE_FLOOR}+ 的大流量款才出得来。"
                  f"这不是缺参数，也不等于该商品没有{metric_cn}。")
        return
    cn_map = CODE_VALUE_CN.get(dim, {})
    print(f"{'取值':<16}\t{metric_cn}\t占比")
    for row in rows[:limit]:
        value = str(_value_of(row.get("attrValue")))
        metric = row.get(crowds_type) or {}
        cnt = metric.get("value")
        ratio = metric.get("ratio")
        share = "-" if ratio is None else f"{ratio * 100:.2f}%"
        # 代码值补中文，原码保留在括号里 —— 别让人以后想核对时找不到原值
        label = f"{cn_map[value]}({value})" if value in cn_map else value
        print(f"{label}\t{'' if cnt is None else cnt}\t{share}")

    # 有标签但一个数都没有。不点明的话，一列 0 会被读成「没人偏好这些品牌」
    # ——那是完全相反的结论。
    if all(not (row.get(crowds_type) or {}).get("value") for row in rows):
        if dim in PAGE_CONFIRMED_EMPTY_DIMS:
            print(f"# 注意：本维度有标签但{metric_cn}全为 0 —— "
                  f"**页面上同样是空的（2026-08-06 已核对）**，是平台侧没有这份数据，"
                  f"不是 CLI 少传参数，也不等于「这些取值没有人」。")
        else:
            print(f"# 注意：本维度有标签但{metric_cn}数值全为 0 / 占比全空，"
                  f"是取不到数，不等于「这些取值没有人」。")

    if dim in UNVERIFIED_CODE_DIMS:
        print(f"# 注意：{dim} 的取值是代码（{UNVERIFIED_CODE_DIMS[dim]}），"
              f"具体哪个代表什么**未核对页面**，原值照显不擅自翻译。")


def cmd_item_profile(args: argparse.Namespace) -> None:
    end = args.end_date or args.date
    if end != args.date:
        print(f"客群洞察只认单日：服务端对多日区间照收 code=0 但静默返回空数组，"
              f"给不出可信结果。请只传 --date（收到 {args.date} ~ {end}）。",
              file=sys.stderr)
        sys.exit(1)

    crowds_type = getattr(args, "crowd", None) or "itmUv"
    if crowds_type not in CROWD_TYPES:
        print(f"未知人群口径 {crowds_type!r}，合法值：{', '.join(CROWD_TYPES)}",
              file=sys.stderr)
        sys.exit(1)

    dims = list(PROFILE_TYPES) if getattr(args, "all", False) else [args.by or "crowd"]
    for d in dims:
        if d not in PROFILE_TYPES:
            print(f"未知维度 {d!r}，合法值：{', '.join(PROFILE_TYPES)}",
                  file=sys.stderr)
            sys.exit(1)

    cookies = load_taobao_cookies()
    item_id = resolve_item_id(args, cookies=cookies)

    collected: dict[str, list[dict[str, Any]]] = {}
    for i, dim in enumerate(dims):
        if i:
            _sleep_humanlike()
        collected[dim] = fetch_item_profile(
            item_id=item_id, date=args.date, profile_type=dim,
            crowds_type=crowds_type, cookies=cookies)

    if args.out:
        Path(args.out).write_text(json.dumps(collected, ensure_ascii=False, indent=2))
        print(f"已写入 {args.out}", file=sys.stderr)
        return
    if args.raw:
        print(json.dumps(collected, ensure_ascii=False, indent=2))
        return

    print(f"# 客群洞察  商品 {item_id}  {args.date}"
          f"（{CROWD_TYPES[crowds_type]}）")
    for dim in dims:
        _print_profile_table(collected[dim], dim, crowds_type, args.limit)


# ---------- 潜在流失风险（客群洞察 / 客群细分）----------
#
# /mc/item/customers/lossrisk.json —— 注意路径前缀是 `/mc/`，这是第 7 个网关族
# （原先只记录了 /cc/、/flow/、/domain/、/csp/api/、/s_content/、/qos/ 六个）。
#
# 2026-08-06 实测：
#   - crowdType 必填，且真起作用（瞎编值回 0 条，ptl-loss 回 50 条）。服务端
#     不吐白名单，前端 39 个 JS bundle 里也搜不到这些值，**只确认了 ptl-loss**。
#     页面上「流失客户」「潜在客户」那些框应该还有别的 crowdType，没拿到就不写。
#   - 多日区间会**静默丢掉 customerCnt 这一列**（行还在，指标没了）——本项目
#     第六次遇到「参数照收、结果悄悄缩水」，所以要显式提示。

LOSS_CROWD_TYPES: dict[str, str] = {
    "ptl-loss": "潜在流失风险",
}


def fetch_item_loss_risk(*, item_id: str, start_date: str, end_date: str,
                          crowd_type: str, page_no: int = 1, page_size: int = 20,
                          cookies: dict[str, str] | None = None) -> dict[str, Any]:
    cookies = cookies or load_taobao_cookies()
    single_day = start_date == end_date
    params = {
        "_": _now_ms(),
        "token": cookies.get("_tb_token_", ""),
        "itemId": item_id,
        "dateRange": f"{start_date}|{end_date}",
        "dateType": "day" if single_day else _infer_cc_date_type(start_date, end_date),
        "page": str(page_no),
        "pageSize": str(page_size),
        "crowdType": crowd_type,
        "indexCode": "customerCnt",
    }
    payload = _api_get("/mc/item/customers/lossrisk.json", params, cookies,
                       referer=f"{REFERER_ARCHIVES}?activeKey=customer")
    return payload.get("data") or {}


def cmd_item_loss_risk(args: argparse.Namespace) -> None:
    crowd_type = getattr(args, "crowd_type", None) or "ptl-loss"
    if crowd_type not in LOSS_CROWD_TYPES:
        print(f"未知人群类型 {crowd_type!r}。目前只核实过："
              f"{', '.join(LOSS_CROWD_TYPES)}（页面上还有别的框，值没拿到就没写进来）",
              file=sys.stderr)
        sys.exit(1)

    cookies = load_taobao_cookies()
    item_id = resolve_item_id(args, cookies=cookies)
    end = args.end_date or args.date
    data = fetch_item_loss_risk(item_id=item_id, start_date=args.date,
                                 end_date=end, crowd_type=crowd_type,
                                 page_no=args.page, page_size=args.limit,
                                 cookies=cookies)
    if args.out:
        Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"已写入 {args.out}", file=sys.stderr)
        return
    if args.raw:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    rows = data.get("data") or []
    print(f"# {LOSS_CROWD_TYPES[crowd_type]}  商品 {item_id}  {args.date}"
          f"  共 {data.get('recordCount')} 条，本页 {len(rows)}")
    print("# 含义：你这个款的客户，预测会流向下面这些商品")

    if not rows:
        # 2026-08-07：原来这里会走到下面那句「多日区间丢指标」的提示上 ——
        # rows 空时 any() 也是 False，于是把「这个款压根没数据」误报成
        # 「你日期传错了」。两回事，不能混。
        print("排名\t预测流失人气\t店铺\t商品")
        print("（无数据）这个款没有潜在流失风险数据 —— 不是日期问题。"
              "这份数据要有足够的客户流向样本才出，冷门款/新款常年为空。")
        return

    has_metric = any("customerCnt" in r for r in rows)
    print("排名\t预测流失人气\t店铺\t商品")
    for r in rows[: args.limit]:
        cnt = _value_of(r.get("customerCnt"))
        shop = (r.get("shop") or {}).get("title") or ""
        title = (r.get("item") or {}).get("title") or ""
        print(f"{_value_of(r.get('rank'))}\t{'-' if cnt is None else cnt}"
              f"\t{shop}\t{title[:28]}")

    if not has_metric:
        print("# 注意：本次没有「预测流失人气」列 —— 多日区间时服务端会静默丢掉这个"
              "指标（行还在，数没了）。要看人气值请用**单日**（--date 与 --end-date 相同）。")
        return

    # 一屏几十行看不出「多少客户流去别家」。按店铺汇总，这才是要看的东西。
    by_shop: dict[str, int] = {}
    for r in rows:
        shop = (r.get("shop") or {}).get("title") or "（未知店铺）"
        by_shop[shop] = by_shop.get(shop, 0) + (_value_of(r.get("customerCnt")) or 0)
    print("# 按店铺汇总（本页）：" + "；".join(
        f"{s} {v}" for s, v in sorted(by_shop.items(), key=lambda kv: -kv[1])))


# ---------- 详情分析 ----------
#
# 2026-08-06 从页面 performance 记录里录到的真实参数。**这些值不能猜**：
# 服务端对 byrType / detailType 的瞎编值不报错，静默返回空——猜错会得到一个
# 永远空着、还看不出毛病的命令。
#
# 最值钱的是 overview 每个指标自带的 rivalAvg(同行均值) / rivalGood(同行优秀)。
# 这是真的同行对比，跟 item-360 那个量级对不上、口径不明的 *Cmpt 不是一回事。

DETAIL_BYR_TYPE = "all"

# 中文名照抄页面（2026-08-06 核对：曝光580/互动461/加购34/支付7/跳失533/
# 停留10.20/跳失率91.90%/加购转化5.86%/支付转化1.21% 与页面逐个一致）
DETAIL_METRICS: dict[str, str] = {
    "itemExposeUv": "曝光人数",
    "itemInteractUv": "互动人数",
    "itemCartUv": "加购人数",
    "itemCollectUv": "收藏人数",
    "itemOrderUv": "下单人数",
    "itemPayUv": "支付人数",
    "itemLossUv": "跳失人数",
    "itemLossRate": "跳失率",
    "itemAvgStayTime": "平均停留时长",
    "itemCartConvertRate": "加购转化率",
    "itemPayConvertRate": "支付转化率",
}

DETAIL_RATE_FIELDS = ("itemLossRate", "itemCartConvertRate", "itemPayConvertRate")


def _pct(v: Any) -> str:
    return "-" if v is None else f"{v * 100:.2f}%"


def _fetch_detail(path: str, *, item_id: str, start_date: str, end_date: str,
                   cookies: dict[str, str], extra: dict[str, str] | None = None) -> Any:
    params = {
        "_": _now_ms(),
        "token": cookies.get("_tb_token_", ""),
        "itemId": item_id,
        "dateRange": f"{start_date}|{end_date}",
        "dateType": "day" if start_date == end_date
                    else _infer_cc_date_type(start_date, end_date),
        "byrType": DETAIL_BYR_TYPE,
    }
    params.update(extra or {})
    return _api_get(path, params, cookies,
                    referer=f"{REFERER_ARCHIVES}?activeKey=pagedtl").get("data")


def flatten_detail_floors(rows: list[dict[str, Any]], prefix: str = "") -> list[dict[str, Any]]:
    """楼层是两级树（主图 → 主图视频/图集/尺码）。展平但保留从属路径。"""
    flat: list[dict[str, Any]] = []
    for row in rows or []:
        cn = str(_value_of(row.get("detailTypeCn"))
                 or _value_of(row.get("detailType")) or "")
        path = f"{prefix} > {cn}" if prefix else cn
        node = {k: v for k, v in row.items() if k != "children"}
        node["_path"] = path
        flat.append(node)
        flat += flatten_detail_floors(row.get("children") or [], prefix=path)
    return flat


def cmd_item_detail(args: argparse.Namespace) -> None:
    cookies = load_taobao_cookies()
    item_id = resolve_item_id(args, cookies=cookies)
    end = args.end_date or args.date

    overview = _fetch_detail("/cc/item/detail/analysis/overview.json",
                              item_id=item_id, start_date=args.date,
                              end_date=end, cookies=cookies) or {}
    _sleep_humanlike()
    floors = _fetch_detail("/cc/item/detail/analysis/list.json",
                            item_id=item_id, start_date=args.date,
                            end_date=end, cookies=cookies) or []

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"overview": overview, "floors": floors}, ensure_ascii=False, indent=2))
        print(f"已写入 {args.out}", file=sys.stderr)
        return
    if args.raw:
        print(json.dumps({"overview": overview, "floors": floors},
                          ensure_ascii=False, indent=2))
        return

    print(f"# 详情分析  商品 {item_id}  {args.date}")
    print("\n## 核心概况（本店 vs 同行）")
    print("指标\t本店\t同行均值\t同行优秀")
    for code, cn in DETAIL_METRICS.items():
        cell = overview.get(code)
        if not isinstance(cell, dict):
            continue
        fmt = _pct if code in DETAIL_RATE_FIELDS else _num
        print(f"{cn}\t{fmt(cell.get('value'))}\t{fmt(cell.get('rivalAvg'))}"
              f"\t{fmt(cell.get('rivalGood'))}")

    print("\n## 详情页逐屏（买家看到哪一屏走的）")
    print("楼层\t曝光人数\t加购人数\t跳失率")
    for row in flatten_detail_floors(floors)[: args.limit]:
        print(f"{row['_path']}\t{_num(_value_of(row.get('itemExposeUv')))}"
              f"\t{_num(_value_of(row.get('itemCartUv')))}"
              f"\t{_pct(_value_of(row.get('itemLossRate')))}")
    print("# 曝光人数从上到下递减是正常的（越往下看的人越少）；"
          "要看的是**哪一层掉得特别狠**。")


# ---------- 价格分析 ----------
#
# 2026-08-06 侦查（从价格分析页面 performance 记录录得）：
#   /cc/item/price/info.json          → 挂牌价 + 所属类目
#   /cc/item/price/getCateId.json     → 本款落在哪个价格带 + 实际件单价
#   /mc/item/price/band/info/v3.json  → 该类目各价格带的大盘（第 3 个 /mc/ 接口）
#
# 命令只做一件事：把「本款在哪一档」和「那一档的盘子有多大、涨得快不快」
# 摆在一起。分开看这两组数没有意义。
#
# 字段名照抄服务端：SupplyRatioIndex 是大写 S 开头（不是笔误，别顺手改）；
# tradeGrowthRate 服务端直接给字符串区间（"35190% ~ 35200%"），不是数字，
# 别拿去乘 100。

def _fetch_price(path: str, *, item_id: str, cookies: dict[str, str],
                  date_params: dict[str, str] | None = None) -> Any:
    params = {
        "_": _now_ms(),
        "token": cookies.get("_tb_token_", ""),
        "itemId": item_id,
    }
    params.update(date_params or {})
    return _api_get(path, params, cookies,
                    referer=f"{REFERER_ARCHIVES}?activeKey=price").get("data")


def cmd_item_price(args: argparse.Namespace) -> None:
    cookies = load_taobao_cookies()
    item_id = resolve_item_id(args, cookies=cookies)
    end = args.end_date or args.date
    dr = {"dateType": "day" if args.date == end
                       else _infer_cc_date_type(args.date, end),
          "dateRange": f"{args.date}|{end}"}

    info = _fetch_price("/cc/item/price/info.json",
                         item_id=item_id, cookies=cookies) or {}
    _sleep_humanlike()
    seg = _fetch_price("/cc/item/price/getCateId.json", item_id=item_id,
                        cookies=cookies, date_params=dr) or {}
    _sleep_humanlike()
    bands = _fetch_price("/mc/item/price/band/info/v3.json", item_id=item_id,
                          cookies=cookies, date_params=dr) or []

    payload = {"info": info, "segment": seg, "bands": bands}
    if args.out:
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"已写入 {args.out}", file=sys.stderr)
        return
    if args.raw:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    my_seg = str(seg.get("priceSegId") or "")
    print(f"# 价格分析  商品 {item_id}  {args.date}")
    print("\n## 本款价格定位")
    # 挂牌价和实际件单价常差很多（活动/优惠券），两个都要出，只看一个会误判
    print(f"挂牌价\t{_num(info.get('price'))}")
    print(f"实际件单价\t{_num(seg.get('itemUnitPrice1'))}")
    print(f"所属价格带\t{seg.get('priceSegName') or '-'}")
    print(f"所属类目\t{(info.get('cateName') or '-').replace('&gt;', '>')}")

    print("\n## 该类目各价格带大盘（← 是本款所在档）")
    print("价格带\t支付买家数\t交易指数占比\t供给指数\t交易增速")
    for b in bands:
        gv = lambda k: _value_of(b.get(k))
        mark = "  ←本款" if str(gv("priceSegId")) == my_seg else ""
        print(f"{gv('priceSegName')}\t{_num(gv('payByrCnt'))}"
              f"\t{_pct(gv('tradeIndexRatio'))}\t{_num(gv('SupplyRatioIndex'))}"
              f"\t{gv('tradeGrowthRate')}{mark}")
    print("# 交易指数占比 = 这一档吃掉了类目多大的成交盘子；供给指数越高说明这档卖家越挤。")


# ---------- 标题优化 ----------
#
# /cc/item/v2/getTitleWords.json 实测（2026-08-06）：没带来搜索引导的词，
# 行里**根本没有 guideSeUv 键**，不是 0，是缺列。渲染成 0 会让人以为
# 「有统计只是量少」，实际是这个词一次搜索都没引来 —— 意思完全不同。
#
# 这个模块唯一真正可执行的结论就是「标题里哪几个字是死的」，所以命令
# 直接把死词数算出来，不让人自己数。

TITLE_REC_GROUPS: dict[str, str] = {
    "rec_cate_words": "类目词",
    "rec_prop_words": "属性词",
    "rec_brand_words": "品牌词",
    "rec_tail_words": "长尾词",
}


def cmd_item_title(args: argparse.Namespace) -> None:
    cookies = load_taobao_cookies()
    item_id = resolve_item_id(args, cookies=cookies)
    end = args.end_date or args.date
    base = {
        "token": cookies.get("_tb_token_", ""),
        "itemId": item_id,
        "dateType": "day" if args.date == end
                    else _infer_cc_date_type(args.date, end),
        "dateRange": f"{args.date}|{end}",
        "device": "0",
    }

    words = _api_get("/cc/item/v2/getTitleWords.json",
                     dict(base, _=_now_ms()), cookies,
                     referer=f"{REFERER_ARCHIVES}?activeKey=title").get("data") or []
    _sleep_humanlike()
    rec = _api_get("/cc/item/title/v2/word/recommend.json",
                   dict(base, _=_now_ms()), cookies,
                   referer=f"{REFERER_ARCHIVES}?activeKey=title").get("data") or {}

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"words": words, "recommend": rec}, ensure_ascii=False, indent=2))
        print(f"已写入 {args.out}", file=sys.stderr)
        return
    if args.raw:
        print(json.dumps({"words": words, "recommend": rec},
                          ensure_ascii=False, indent=2))
        return

    dead = [w for w in words if "guideSeUv" not in w]
    print(f"# 标题优化  商品 {item_id}  {args.date}")
    print(f"\n## 标题分词效果（{len(words)} 个词里有 {len(dead)} 个零引导）")
    if dead:
        print("# 零引导 = 这个词一次搜索都没引来，白占标题字数："
              + "、".join(str(w.get("searchWord")) for w in dead))
    print("词\t搜索引导访客\t支付转化率")
    ordered = sorted(words, key=lambda w: -(_value_of(w.get("guideSeUv")) or 0))
    for w in ordered[: args.limit]:
        uv = _value_of(w.get("guideSeUv"))
        # 缺列打 "-" 不打 0：0 是「统计到了但没量」，缺列是「压根没引来搜索」
        print(f"{w.get('searchWord')}\t{'-' if uv is None else uv}"
              f"\t{_pct(_value_of(w.get('payRate')))}")

    print("\n## 推荐词（热度越高越有量，竞争度越高越难抢）")
    for key, cn in TITLE_REC_GROUPS.items():
        group = rec.get(key) or []
        if not group:
            continue
        print(f"\n### {cn}")
        print("词\t推荐分\t热度分位\t竞争分位")
        for r in group[: args.limit]:
            print(f"{r.get('word')}\t{_num(r.get('score'))}"
                  f"\t{_pct(r.get('hot_pctile'))}\t{_pct(r.get('compete_pctile'))}")


# ---------- 关联搭配 ----------
#
# 系统推荐 /cc/item/bundle/recommend.json —— 买了这个款的人还买了什么（本店内）。
# 卖家自选 /cc/item/bundle/sellerRecommend.json —— 店主手动配的搭配。
#   缺 orderBy 会被 code=1003 拒绝；实测本店返回 0 行，因为压根没配过。
#   空表要说清是「没配置」而不是「接口坏了」——两者的处置完全不同。

BUNDLE_SELLER_ORDER_BY = "recent7AItmUv"


def cmd_item_bundle(args: argparse.Namespace) -> None:
    cookies = load_taobao_cookies()
    item_id = resolve_item_id(args, cookies=cookies)
    end = args.end_date or args.date
    base = {
        "token": cookies.get("_tb_token_", ""),
        "itemId": item_id,
        "dateType": "day" if args.date == end
                    else _infer_cc_date_type(args.date, end),
        "dateRange": f"{args.date}|{end}",
        "device": "0",
        "page": str(args.page),
        "pageSize": str(args.limit),
    }
    ref = f"{REFERER_ARCHIVES}?activeKey=bundle"

    system = _api_get("/cc/item/bundle/recommend.json",
                      dict(base, _=_now_ms()), cookies, referer=ref).get("data") or []
    _sleep_humanlike()
    seller_raw = _api_get("/cc/item/bundle/sellerRecommend.json",
                          dict(base, _=_now_ms(), order="desc",
                               orderBy=BUNDLE_SELLER_ORDER_BY),
                          cookies, referer=ref).get("data") or {}
    seller = (seller_raw.get("data") if isinstance(seller_raw, dict)
              else seller_raw) or []

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"system": system, "seller": seller}, ensure_ascii=False, indent=2))
        print(f"已写入 {args.out}", file=sys.stderr)
        return
    if args.raw:
        print(json.dumps({"system": system, "seller": seller},
                          ensure_ascii=False, indent=2))
        return

    def table(rows: list[dict[str, Any]]) -> None:
        print("排名\t预测连带支付件数\t占比\t商品")
        for r in rows[: args.limit]:
            cell = r.get("bundlePayCnt") or {}
            print(f"{_value_of(r.get('rank'))}\t{_num(cell.get('value'))}"
                  f"\t{_pct(cell.get('ratio'))}"
                  f"\t{((r.get('item') or {}).get('title') or '')[:30]}")

    print(f"# 关联搭配  商品 {item_id}  {args.date}")
    print("\n## 连带商品推荐（页面上叫这个；买了这个款的人还买了什么）")
    if system:
        table(system)
    else:
        print("（无数据）")

    print("\n## 掌柜推荐（你自己配的搭配，页面上叫「掌柜推荐」）")
    if seller:
        table(seller)
    else:
        print("（空）本店**没配置过**卖家自选搭配 —— 是没配，不是接口取不到。"
              "要用这个位置得先去后台手动配搭配商品。")


# ---------- 内容分析 ----------
#
# /s_content/forcc/video/single/item/list.json（2026-08-06 从页面 performance 录得）
# 三个猜不出来、且服务端不给白名单的参数：
#   keyword=<商品ID>          ← 是 keyword 不是 itemId。第一次按 itemId 传，
#                               服务端回「请求参数非法」，光看报错想不到是这个
#   accountRole=guanghe-all
#   indexCode=<逗号分隔>      缺了行里就没有指标列
#
# 返回是两层：videoId="all" 的汇总行 + children 里逐个视频。汇总行必须标出来，
# 混进逐个视频列表会被重复计数。
# 页面默认 recent30 —— 内容效果看单日没意义，命令沿用长窗口默认。

CONTENT_INDEX_CODES = ("contentItemClickCnt,itemFansClickPv,contentCltTimes,"
                        "contentCartItmCnt,interestPayAmt")

# 中文名照抄页面表头（2026-08-06 核对）。
CONTENT_COLUMNS: list[tuple[str, str]] = [
    ("contentItemClickCnt", "商品点击次数"),
    ("itemFansClickPv", "粉丝点击次数"),
    ("contentCltTimes", "引导收藏次数"),
    ("contentCartItmCnt", "引导加购件数"),
    ("interestPayUV", "种草成交人数"),
    ("interestPayAmt", "种草成交金额"),
]

# 2026-08-06 与页面「TOP短视频」表逐行比对：粉丝点击次数 / 引导收藏次数 /
# 引导加购件数 / 种草成交金额 四列**全中**，但 contentItemClickCnt 有两行对不上
# （页面 219 / 18，接口 223 / 17）。响应里**没有任何字段等于页面那个值**，
# 所以不是取错字段。原因未查明 —— 不装作没事，命令打一句提示。
# 2026-08-07 结案：页面截图逐格比对，7 行 × 5 列 35 个格子全中，含「商品点击次数」。
# 之前记的「219 vs 223 对不上」是比错了对象 —— 页面这一块有 TOP直播 / TOP短视频 /
# TOP图文 三个标签，本命令走的 video 接口只对应「TOP短视频」那一个。
CONTENT_SCOPE_NOTE = (
    "# 范围：只覆盖页面的「TOP短视频」标签（走 video 接口）。"
    "同一块还有 TOP直播 / TOP图文 两个标签，本命令不含 —— 拿这里的数去对页面时，"
    "先确认页面切在「TOP短视频」上。\n"
    "# 数值口径：2026-08-07 与页面逐格比对通过（7 行 × 5 列全中，含商品点击次数）。")


def flatten_content_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """展平内容树。

    实测（2026-08-06）children 里不是直接的视频行，而是包了一层信封：
        children: [ {data: [ 视频行, ... ]} ]
    把信封当成行会渲染出一整行横杠。另外视频行的标题字段是 videoTitle，
    汇总行才是 itemTitle —— 照着汇总行写会让每个视频都没名字。
    """
    flat: list[dict[str, Any]] = []
    for row in rows or []:
        inner = row.get("data")
        if isinstance(inner, list):        # 信封，不是数据行
            flat += flatten_content_rows(inner)
            continue
        node = {k: v for k, v in row.items() if k != "children"}
        vid = str(_value_of(row.get("videoId")) or "")
        title = _value_of(row.get("videoTitle")) or _value_of(row.get("itemTitle"))
        node["_label"] = ("合计（全部内容）" if vid == "all"
                          else str(title or vid)[:28])
        flat.append(node)
        flat += flatten_content_rows(row.get("children") or [])
    return flat


def _content_window(args: argparse.Namespace) -> tuple[str, str]:
    """内容分析的日期窗口。

    不传日期 → 近 30 天（和页面默认一致，也是这个命令 help 里写的口径）；
    显式传了 --date 就照给的来（这个接口单日也认，2026-08-07 实测
    dateType=day + 单日 dateRange 正常返回）。

    2026-08-07 修：原来把 dateType 硬写成 recent30、dateRange 却是单日，
    服务端 code=1003 直接拒。**默认参数就是坏的** —— 当初核验时手工传了
    30 天区间，恰好绕开了默认路径，测试也全绿。教训：核验必须先跑一遍
    不带任何参数的默认调用。
    """
    if args.date is None:
        end = args.end_date or _yesterday()
        start = (date.fromisoformat(end) - timedelta(days=29)).isoformat()
        return start, end
    return args.date, args.end_date or args.date


def cmd_item_content(args: argparse.Namespace) -> None:
    cookies = load_taobao_cookies()
    item_id = resolve_item_id(args, cookies=cookies)
    start, end = _content_window(args)
    params = {
        "_": _now_ms(),
        "token": cookies.get("_tb_token_", ""),
        # 注意：这个接口用 keyword 传商品 ID，不是 itemId
        "keyword": item_id,
        "dateType": _infer_cc_date_type(start, end),
        "dateRange": f"{start}|{end}",
        "page": str(args.page),
        "pageSize": str(args.limit),
        "order": "desc",
        "orderBy": "interestPayAmt",
        "accountRole": "guanghe-all",
        "indexCode": CONTENT_INDEX_CODES,
    }
    raw = _api_get("/s_content/forcc/video/single/item/list.json", params, cookies,
                   referer=f"{REFERER_ARCHIVES}?activeKey=content").get("data") or {}
    rows = (raw.get("data") if isinstance(raw, dict) else raw) or []

    if args.out:
        Path(args.out).write_text(json.dumps(raw, ensure_ascii=False, indent=2))
        print(f"已写入 {args.out}", file=sys.stderr)
        return
    if args.raw:
        print(json.dumps(raw, ensure_ascii=False, indent=2))
        return

    print(f"# 内容分析  商品 {item_id}  {start} ~ {end}")
    if not rows:
        print("（无数据）这个款没有关联的内容/视频。")
        return
    print("内容\t" + "\t".join(cn for _, cn in CONTENT_COLUMNS))
    for row in flatten_content_rows(rows)[: args.limit + 1]:
        cells = [_num(_value_of(row.get(code))) for code, _ in CONTENT_COLUMNS]
        print(row["_label"] + "\t" + "\t".join(cells))
    print("# 「合计（全部内容）」是汇总行，别和下面逐条内容相加。")
    print(CONTENT_SCOPE_NOTE)


# ---------- 服务体验 ----------
#
# /domain/oneQuery.json domainCode=tao.shop.qos.item（2026-08-06 从页面录得）。
#
# **needCycleCrc 要放进 extMap 里**，不是独立 query 参数。当独立参数传时服务端
# 不报错、直接回空 dict —— 2026-08-06 上午就栽在这，一度以为这个 domainCode
# 取不到数。这也是当天「网关字段只能录不能推」结论的又一例。
#
# 指标成对出现：本店值 + 同款/类目均值。光看「有效回复 47」判断不了好坏，
# 所以按对渲染，缺了对比值就只显示本店值。

SERVICE_PAIRS: list[tuple[str, str | None, str]] = [
    ("validReplyUv", "validReplyUvSameItem", "有效接待人数"),
    ("preSaleConsultCnt", "preSaleAvgConsultCnt", "售前咨询人数"),
    ("preSaleConsultRate", "preSaleAvgConsultRate", "售前咨询率"),
    ("preSaleDealCnt", "preSaleAvgDealCnt", "售前成交人数"),
    ("afterSaleConsultCnt", "afterSaleAvgConsultCnt", "售后咨询人数"),
    ("afterSaleFstSolutionRate", "afterSaleAvgFstSolutionRate", "售后首次解决率"),
    ("actRmkCnt", "actRmkCntSameItem", "主动评价数"),
    ("wdjVocCnt", "wdjCateAvgVocCnt", "问大家原声量"),
    ("rfdSucCnt", "rfdCntAvg", "成功退款笔数"),
]

SERVICE_RATE_FIELDS = ("preSaleConsultRate", "preSaleAvgConsultRate",
                        "afterSaleFstSolutionRate", "afterSaleAvgFstSolutionRate")

SERVICE_INDEX_CODES = ",".join(
    c for own, cmp_, _ in SERVICE_PAIRS for c in (own, cmp_) if c)


def cmd_item_service(args: argparse.Namespace) -> None:
    cookies = load_taobao_cookies()
    item_id = resolve_item_id(args, cookies=cookies)
    end = args.end_date or args.date
    params = {
        "_": _now_ms(),
        "token": cookies.get("_tb_token_", ""),
        "domainCode": "tao.shop.qos.item",
        "showType": "overview",
        "device": "0",
        "dateType": "day" if args.date == end
                    else _infer_cc_date_type(args.date, end),
        "dateRange": f"{args.date}|{end}",
        "indexCodes": SERVICE_INDEX_CODES,
        # needCycleCrc 在 extMap 里面，不是独立参数（见上方注释）
        "extMap": json.dumps({"itemId": item_id, "needCycleCrc": True},
                              separators=(",", ":")),
    }
    data = _api_get("/domain/oneQuery.json", params, cookies,
                    referer=f"{REFERER_ARCHIVES}?activeKey=service").get("data") or {}

    if args.out:
        Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"已写入 {args.out}", file=sys.stderr)
        return
    if args.raw:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    print(f"# 服务体验  商品 {item_id}  {args.date} ~ {end}")
    if not data:
        print("（无数据）")
        return
    print("指标\t本店\t同类商品平均\t环比")
    for own, cmp_, cn in SERVICE_PAIRS:
        cell = data.get(own)
        if not isinstance(cell, dict):
            continue          # 服务端按权限少回指标是常态，缺的跳过不打 0
        fmt = _pct if own in SERVICE_RATE_FIELDS else _num
        other = data.get(cmp_) if cmp_ else None
        other_txt = fmt(other.get("value")) if isinstance(other, dict) else "-"
        print(f"{cn}\t{fmt(cell.get('value'))}\t{other_txt}"
              f"\t{_pct(cell.get('cycleCrc'))}")
    print("# 「同类商品平均」是页面上的原话（2026-08-06 核对：有效接待47/平均2、主动评价10/2、问大家5/1、成功退款265/0，四项全中）。")


# ========== 阶段3：页面级模块（店铺级，不带 itemId）==========
#
# 参数全部 2026-08-06 从页面 performance 记录录得。三个反直觉的点：
#   商品集   spuType=**def**，不是 all —— 传 all 只回一句 "param check error"，
#            没有任何提示指向这个参数
#   连带分析 关联侧字段名带 relate 前缀（relatePayByrCnt），排序参数是
#            mainOrderBy + relateOrderBy + relateOrder，没有 order/orderBy；
#            只传 mainOrderBy 会 code=600007 且**消息为空**
#   视频分析 detail/list 一次 1441 条 × 33 个指标

def _page_params(args: argparse.Namespace, cookies: dict[str, str],
                  **extra: str) -> dict[str, str]:
    end = args.end_date or args.date
    p = {
        "_": _now_ms(),
        "token": cookies.get("_tb_token_", ""),
        "dateType": "day" if args.date == end
                    else _infer_cc_date_type(args.date, end),
        "dateRange": f"{args.date}|{end}",
        "device": "0",
        "page": str(args.page),
        "pageSize": str(args.limit),
    }
    p.update(extra)
    return p


def _emit(args: argparse.Namespace, payload: Any) -> bool:
    """--out / --raw 的公共出口。返回 True 表示已输出，调用方直接 return。"""
    if args.out:
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"已写入 {args.out}", file=sys.stderr)
        return True
    if args.raw:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return True
    return False


SPU_INDEX_CODES = "spuPayOrdAmt,spuPayOrdItmQty,spuUnitPrice"


def cmd_spu_list(args: argparse.Namespace) -> None:
    end = args.end_date or args.date
    if end != args.date:
        # 服务端只回一句 "param check error"，完全指不到日期上。本地拦掉，
        # 免得下次又要从头排查一遍。
        print(f"商品集分析只认单日：多日区间服务端只回一句 param check error，"
              f"不会告诉你是日期的问题。请只传 --date（收到 {args.date} ~ {end}）。",
              file=sys.stderr)
        sys.exit(1)
    cookies = load_taobao_cookies()
    data = _api_get("/cc/spu/list.json",
                    _page_params(args, cookies, order="desc",
                                 orderBy="spuPayOrdAmt", spuType="def",
                                 indexCode=SPU_INDEX_CODES),
                    cookies, referer="https://sycm.taobao.com/cc/spu_manage").get("data") or {}
    if _emit(args, data):
        return
    rows = data.get("data") or []
    print(f"# 商品集分析  {args.date} ~ {args.end_date or args.date}"
          f"  共 {data.get('recordCount')} 个商品集")
    print("商品集\t分类\t含商品数\t支付金额\t支付件数\t件单价")
    for r in rows[: args.limit]:
        g = lambda k: _value_of(r.get(k))
        print(f"{g('spuName')}\t{g('spuTypeCn')}\t{_num(g('spuItemCnt'))}"
              f"\t{_num(g('spuPayOrdAmt'))}\t{_num(g('spuPayOrdItmQty'))}"
              f"\t{_num(g('spuUnitPrice'))}")


def cmd_item_relate(args: argparse.Namespace) -> None:
    if (args.end_date or args.date) == args.date:
        # 服务端只回 code=1002 "4004:"，一个字都不提日期。本地拦掉。
        # 2026-08-07 实测：单日必挂，7 天窗口正常。当初核验时用的就是 7 天窗口，
        # 所以「默认单日直接报错」这条一直没被发现。
        print("连带分析不认单日：服务端只回 code=1002 4004:，不会告诉你是日期的问题。"
              "请给区间，如 --date 2026-07-31 --end-date 2026-08-06（7/15/30 天窗口）。",
              file=sys.stderr)
        sys.exit(1)
    cookies = load_taobao_cookies()
    data = _api_get("/cc/item/relate/analysis.json",
                    _page_params(args, cookies, device="2",
                                 mainOrderBy="payItemCnt",
                                 relateOrderBy="relatePayByrCnt",
                                 relateOrder="desc"),
                    cookies, referer="https://sycm.taobao.com/cc/item_relate").get("data") or {}
    if _emit(args, data):
        return
    rows = (data.get("data") if isinstance(data, dict) else data) or []
    print(f"# 连带分析  {args.date} ~ {args.end_date or args.date}")
    print("# 主商品行 = 这个款自己的表现；缩进行 = 买了它的人还买了什么")
    for r in rows[: args.limit]:
        g = lambda k: _value_of(r.get(k))
        print(f"\n{(r.get('item') or {}).get('title', '')[:28]}"
              f"\t访客={_num(g('uv'))}\t支付金额={_num(g('payAmt'))}"
              f"\t支付件数={_num(g('payItemCnt'))}")
        print("  关联商品\t关联支付人数\t关联购买率\t关联访客数")
        for ri in (r.get("relateItems") or [])[: args.limit]:
            rg = lambda k: _value_of(ri.get(k))
            print(f"  {(ri.get('item') or {}).get('title', '')[:26]}"
                  f"\t{_num(rg('relatePayByrCnt'))}"
                  f"\t{_pct(rg('relatePayByrRate'))}\t{_num(rg('relateUv'))}")


VIDEO_COLUMNS: list[tuple[str, str, bool]] = [
    ("itemExposeUv", "曝光人数", False),
    ("itemClkUv", "点击人数", False),
    ("exposureClickRate", "曝光点击率", True),
    ("validPlayUv", "有效播放人数", False),
    ("effectivePlayRate", "有效播放率", True),
    ("completionRateNew", "完播率", True),
    ("daysDealUv", "当日成交人数", False),
    ("daysPayAmt", "当日成交金额", False),
]


def cmd_video_list(args: argparse.Namespace) -> None:
    cookies = load_taobao_cookies()
    data = _api_get("/cc/video/detail/list.json",
                    _page_params(args, cookies, order="desc",
                                 orderBy="itemExposeUv"),
                    cookies,
                    referer="https://sycm.taobao.com/cc/video/analysis").get("data") or {}
    if _emit(args, data):
        return
    rows = data.get("data") or []
    total = data.get("recordCount")
    # 实测 1441 条，默认只出一页。不报总数会让人以为就这么几条。
    print(f"# 视频分析  {args.date} ~ {args.end_date or args.date}"
          f"  共 {total} 条，本页 {len(rows)}")
    print("商品\t" + "\t".join(cn for _, cn, _ in VIDEO_COLUMNS))
    for r in rows[: args.limit]:
        cells = [(_pct if is_rate else _num)(_value_of(r.get(code)))
                 for code, _, is_rate in VIDEO_COLUMNS]
        print(f"{(r.get('item') or {}).get('title', '')[:26]}\t" + "\t".join(cells))


# ---------- 宏观监控 ----------
#
# /cc/cockpit/marcro/core/live/overview.json（注意服务端把 macro 拼成了 marcro）
# 是**实时快照**：响应带 updateTime 与 interval=60。
#
# 2026-08-06 实测：recent7 / recent30 / day 三档返回的 payAmt 完全相同
# （11757.95），访客数的微小差异只是实时数在跳 —— **--date 不生效**。
# 这是本项目第七次撞上「参数照收、结果与日期无关」，所以命令直接把这句
# 打出来，不指望用户自己发现。

MACRO_METRICS: list[tuple[str, str, bool]] = [
    ("payAmt", "支付金额", False),
    ("payByrCnt", "支付买家数", False),
    ("payItmCnt", "支付件数", False),
    ("payRate", "支付转化率", True),
    ("itmUv", "商品访客数", False),
    ("itmPv", "商品浏览量", False),
    ("miniDetailUv", "微详情访客数", False),
    ("itemCartCnt", "商品加购件数", False),
    ("itemCartByrCnt", "商品加购人数", False),
    ("itemCltByrCnt", "商品收藏人数", False),
    ("visitCartRate", "访问加购转化率", True),
    ("visitCltRate", "访问收藏转化率", True),
]


def cmd_macro_monitor(args: argparse.Namespace) -> None:
    cookies = load_taobao_cookies()
    envelope = _api_get("/cc/cockpit/marcro/core/live/overview.json",
                        _page_params(args, cookies), cookies,
                        referer="https://sycm.taobao.com/cc/macro_monitor").get("data") or {}
    if _emit(args, envelope):
        return
    inner = envelope.get("data") or {}
    print(f"# 宏观监控（实时快照，更新于 {envelope.get('updateTime')}，"
          f"每 {envelope.get('interval')} 秒刷新）")
    print("# 注意：这个接口**不认日期**——实测 day / recent7 / recent30 三档返回完全"
          "相同的值，--date / --end-date 传了不生效。要看历史请用别的命令。")
    print("指标\t当前值\t环比")
    for code, cn, is_rate in MACRO_METRICS:
        cell = inner.get(code)
        if not isinstance(cell, dict):
            continue
        fmt = _pct if is_rate else _num
        print(f"{cn}\t{fmt(cell.get('value'))}\t{_pct(cell.get('cycleCrc'))}")


# ---------- 问题预警（隐藏路由 /cc/problem_alarm）----------
#
# 2026-08-06 侦查阶段4 的 21 条隐藏路由，只有这一条有独立数据，其余大多是
# 「同一份数据换个角度」的下钻页、跳出 sycm 的外链、或本店无数据。
#
# 接口路径里服务端把 problem 拼成了 **prolem**，照抄不改。实时（interval=30）。
#
# 三个计数里只有「缺货」有明细接口。**质量问题商品在页面上点进去只显示
# 「请在新打开的页面中查看」——明细在别的系统，sycm 侧拿不到**。不写清楚，
# 用户会以为是 CLI 少做了一块。

ALARM_COUNTS: list[tuple[str, str]] = [
    ("qualityIssueItemCnt", "质量问题商品"),
    ("stockoutItemCnt", "缺货商品"),
    ("highPriceItemCnt", "高价限流商品"),
]


def cmd_problem_alarm(args: argparse.Namespace) -> None:
    cookies = load_taobao_cookies()
    ref = "https://sycm.taobao.com/cc/problem_alarm"
    stats = _api_get("/cc/prolemitem/statistics.json",
                     _page_params(args, cookies), cookies, referer=ref).get("data") or {}
    _sleep_humanlike()
    stock = _api_get("/cc/exp/stock/out.json",
                     _page_params(args, cookies), cookies, referer=ref).get("data") or {}

    if _emit(args, {"statistics": stats, "stockout": stock}):
        return

    counts = stats.get("data") or {}
    print(f"# 问题预警（实时，更新于 {stats.get('updateTime')}）")
    print("类型\t数量")
    for code, cn in ALARM_COUNTS:
        print(f"{cn}\t{counts.get(code, '-')}")

    if counts.get("qualityIssueItemCnt"):
        print(f"# 注意：质量问题商品只有计数、**明细不在 sycm**——页面上点进去是"
              f"「请在新打开的页面中查看」，跳出去到别的系统。要看具体是哪 "
              f"{counts['qualityIssueItemCnt']} 个，得去千牛体检中心。")

    rows = (stock.get("data") if isinstance(stock, dict) else stock) or []
    print("\n## 缺货明细")
    if not rows:
        print("没有缺货商品。")   # 0 条是好消息，别渲染成让人以为出错的空表
        return
    print(json.dumps(rows[: args.limit], ensure_ascii=False, indent=1))


# ---------- 商品区间分析（宏观监控的第 2 个子 tab）----------
#
# /cc/interval/list.json（2026-08-06 从页面录得）。回答的是「我的动销商品
# 按价格/件数/金额切开，各段各占多少」—— 一句话：你的货到底集中在哪一档。
#
# **空区间的行只有 band 一个键，没有任何指标**，跟标题死词是同一个模式：
# 打 0 会被读成「这个区间有商品但卖了 0 元」，实际是这个区间一个商品都没有。

INTERVAL_VIEWS: dict[str, str] = {
    "ordPqt": "按价格带",
    "payItmCnt": "按支付件数",
    "payAmt": "按支付金额",
}

# 第三项 = 这一列要不要跟着打「占比」。件单价不打 —— 单价的「占比」是拿两档
# 单价相加当分母算出来的，没有业务含义，页面上也没有这一列（2026-08-06 核对）。
INTERVAL_COLUMNS: list[tuple[str, str, bool]] = [
    ("paidItemCnt", "动销商品数", True),
    ("payAmt", "支付金额", True),
    ("payItmCnt", "支付件数", True),
    ("ordPqt", "件单价", False),
]

INTERVAL_INDEX_CODES = "paidItemCnt,payAmt,payItmCnt,ordPqt"


def _bands_are_degenerate(rows: list[Any]) -> bool:
    """服务端把同一份数据当成多个区间吐出来了吗？

    `--by payItmCnt` 实测恒返回两行 band 都是 `0-`、四个指标值也完全相同的行。
    判据：至少两行 band 相同且指标值也相同 —— 真正的区间划分不可能这样。
    """
    seen: set[tuple] = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        key = (r.get("band"),) + tuple(
            _value_of(r.get(code)) for code, _, _ in INTERVAL_COLUMNS)
        if key in seen:
            return True
        seen.add(key)
    return False


def cmd_interval_analysis(args: argparse.Namespace) -> None:
    view = getattr(args, "by", None) or "ordPqt"
    if view not in INTERVAL_VIEWS:
        print(f"未知视角 {view!r}，合法值："
              + "、".join(f"{k}={v}" for k, v in INTERVAL_VIEWS.items()),
              file=sys.stderr)
        sys.exit(1)

    if view == "ordPqt" and (args.end_date or args.date) != args.date:
        # 2026-08-07 实测：价格带视角 7 天和 30 天窗口都回 code=1002 "4000:"，
        # 只有单日能用。另外两个视角多日正常。服务端那句 4000 不提日期，本地拦掉。
        print(f"价格带视角只认单日：7/30 天窗口服务端都回 code=1002 \"4000:\"，"
              f"不会告诉你是日期的问题（收到 {args.date} ~ {args.end_date}）。\n"
              f"要看多日请换视角：--by payItmCnt 或 --by payAmt。",
              file=sys.stderr)
        sys.exit(1)

    cookies = load_taobao_cookies()
    rows = _api_get("/cc/interval/list.json",
                    _page_params(args, cookies, cateId="", cateLevel="",
                                 defAnalyseType=view, includeSync="0",
                                 indexCode=INTERVAL_INDEX_CODES),
                    cookies,
                    referer="https://sycm.taobao.com/cc/macro_monitor").get("data") or []
    if _emit(args, rows):
        return

    print(f"# 商品区间分析（{INTERVAL_VIEWS[view]}）  {args.date}"
          f" ~ {args.end_date or args.date}")
    print("区间\t" + "\t".join(f"{cn}\t占比" if with_ratio else cn
                                  for _, cn, with_ratio in INTERVAL_COLUMNS))
    for r in rows[: args.limit]:
        cells = []
        for code, _, with_ratio in INTERVAL_COLUMNS:
            cell = r.get(code)
            # 空区间整行只有 band，缺列打 "-"：0 会被读成「有商品但没卖出去」
            if not isinstance(cell, dict):
                cells += ["-", "-"] if with_ratio else ["-"]
            elif with_ratio:
                cells += [_num(cell.get("value")), _pct(cell.get("ratio"))]
            else:
                cells.append(_num(cell.get("value")))
        print(str(r.get("band")) + "\t" + "\t".join(cells))
    print("# 只有 band、没有数字的行 = 这个区间一个动销商品都没有，不是卖了 0 元。")
    if _bands_are_degenerate(rows):
        print("# ⚠️ 这个视角的区间没配好，数字没有意义：多行的区间名和数值完全相同"
              "（占比各 50% 是拿自己两行相加当的分母）。\n"
              "# 修法：去 sycm 宏观监控 → 商品区间分析，点这一栏右上角的「编辑」，"
              "把区间边界配成有意义的值。区间是**店铺自己配的**，不是平台给死的 ——"
              "本店的「按支付件数」两档都配成了「0 以上」，等于没分档。\n"
              "# （2026-08-07 页面截图确认：页面显示的也是这两行相同的数据，"
              "改配置前 CLI 和页面都只能这样。）")


def register(subparsers: Any, yesterday: str) -> None:
    """把商品板块命令挂到主 parser 上。"""
    s = subparsers.add_parser("item-search",
                              help="按商品标题/商品ID/商品URL/货号搜商品（拿 itemId 用）")
    s.add_argument("keyword", help="商品标题关键词、商品ID、商品URL 或货号")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--raw", action="store_true")
    s.add_argument("--out")
    s.set_defaults(func=cmd_item_search)

    sku = subparsers.add_parser("item-sku-list",
                                help=ITEM_PRESETS["item-sku-list"]["desc"])
    _add_item_args(sku, yesterday)
    sku_mode = sku.add_mutually_exclusive_group()
    sku_mode.add_argument("--by", metavar="属性名",
                          help="按属性维度聚合（如 尺码、颜色分类），不传则出 SKU 组合明细；"
                               "取值来自商品自身的属性名，服务端不认的值会自己报错。"
                               "与 --live 互斥（属性聚合接口没有实时库存版本）")
    sku_mode.add_argument("--live", action="store_true",
                          help=ITEM_PRESETS["item-sku-list-live"]["desc"]
                               + "。与 --by 互斥")
    sku.set_defaults(func=cmd_item_sku_list)

    fs = subparsers.add_parser("item-flow-source",
                               help=ITEM_PRESETS["item-flow-source"]["desc"])
    _add_item_args(fs, yesterday)
    fs.set_defaults(func=cmd_item_flow_source)

    rf = subparsers.add_parser("item-refund",
                               help="单品退款归因：原因 + 各 SKU + 各属性")
    _add_item_args(rf, yesterday)
    rf.set_defaults(func=cmd_item_refund)

    i3 = subparsers.add_parser("item-360",
                               help="单品总体面貌：诊断核心指标(本店值+环比+未核实的cmpt对比值) + 销售总览(实时快照)")
    _add_item_args(i3, yesterday)
    i3.set_defaults(func=cmd_item_360)

    pf = subparsers.add_parser("item-profile",
                               help="客群洞察：买这个款的人是谁（人群标签/年龄/地域/消费层级等 10 个维度，只认单日）")
    _add_item_args(pf, yesterday)
    pf.add_argument("--by", default="crowd", metavar="维度",
                    help="维度，默认 crowd（人群标签）。可选："
                         + "、".join(f"{k}={v}" for k, v in PROFILE_TYPES.items()))
    pf.add_argument("--crowd", default="itmUv", metavar="人群口径",
                    help="人群口径，默认 itmUv（访问人群）。payByrCnt/appSearchUv "
                         "实测恒空、原因未定")
    pf.add_argument("--all", action="store_true", help="一次跑完 10 个维度")
    pf.set_defaults(func=cmd_item_profile)

    lr = subparsers.add_parser("item-loss-risk",
                               help="潜在流失风险：你这个款的客户预测会流向哪些商品（含友商）。人气值只有单日有")
    _add_item_args(lr, yesterday)
    lr.add_argument("--crowd-type", default="ptl-loss",
                    help="人群类型，默认 ptl-loss（潜在流失风险）。"
                         "页面上还有别的框，但值未核实，没写进来")
    lr.set_defaults(func=cmd_item_loss_risk)

    dt = subparsers.add_parser("item-detail",
                               help="详情分析：核心概况（带同行均值/优秀）+ 详情页逐屏，看买家看到哪屏走的")
    _add_item_args(dt, yesterday)
    dt.set_defaults(func=cmd_item_detail)

    pr = subparsers.add_parser("item-price",
                               help="价格分析：本款价格定位 + 类目各价格带大盘（标出本款所在档）")
    _add_item_args(pr, yesterday)
    pr.set_defaults(func=cmd_item_price)

    ti = subparsers.add_parser("item-title",
                               help="标题优化：标题每个词带来多少搜索访客（点出零引导的死词）+ 推荐词")
    _add_item_args(ti, yesterday)
    ti.set_defaults(func=cmd_item_title)

    bd = subparsers.add_parser("item-bundle",
                               help="关联搭配：买了这个款的人还买了什么（系统推荐 + 卖家自选）")
    _add_item_args(bd, yesterday)
    bd.set_defaults(func=cmd_item_bundle)

    ct = subparsers.add_parser("item-content",
                               help="内容分析：关联的视频/内容带来多少种草点击、加购、支付（默认近30天）")
    _add_item_args(ct, yesterday)
    # 唯一一个默认不是「昨天单日」的单品命令：内容种草效果按天看噪音太大，
    # 页面默认也是近30天。date=None 是「用户没给日期」的信号，交给 _content_window。
    ct.set_defaults(func=cmd_item_content, date=None)

    sv = subparsers.add_parser("item-service",
                               help="服务体验：售前咨询/售后解决率/有效回复/问大家声量等，每项带对比值")
    _add_item_args(sv, yesterday)
    sv.set_defaults(func=cmd_item_service)

    # 阶段3：页面级（店铺级，不带 --item-id）
    def _page_parser(name: str, help_text: str, fn):
        q = subparsers.add_parser(name, help=help_text)
        q.add_argument("--date", default=yesterday, help="YYYY-MM-DD (默认昨天)")
        q.add_argument("--end-date", help="结束日期（默认 = --date）")
        q.add_argument("--limit", type=int, default=10)
        q.add_argument("--page", type=int, default=1)
        q.add_argument("--raw", action="store_true")
        q.add_argument("--out")
        q.set_defaults(func=fn)

    _page_parser("spu-list", "商品集分析：各商品集的支付金额/件数/件单价", cmd_spu_list)

    # 连带分析单日必挂（服务端 code=1002 4004:），所以默认给近 7 天而不是昨天。
    _page_parser("item-relate", "连带分析：买了这个款的人还买了什么（主商品 + 关联商品，默认近7天）",
                 cmd_item_relate)
    subparsers.choices["item-relate"].set_defaults(
        date=(date.fromisoformat(yesterday) - timedelta(days=6)).isoformat(),
        end_date=yesterday)
    _page_parser("video-list", "视频分析：各商品视频的曝光/点击/播放/完播/成交", cmd_video_list)
    _page_parser("macro-monitor", "宏观监控：全店商品实时大盘（实时快照，--date 不生效）",
                 cmd_macro_monitor)
    _page_parser("problem-alarm", "问题预警：质量问题/缺货/高价限流商品计数 + 缺货明细（实时）",
                 cmd_problem_alarm)

    iv = subparsers.add_parser("interval-analysis",
                               help="商品区间分析：动销商品按价格带/支付件数/支付金额切开各占多少")
    iv.add_argument("--date", default=yesterday, help="YYYY-MM-DD (默认昨天)")
    iv.add_argument("--end-date", help="结束日期（默认 = --date）")
    iv.add_argument("--by", default="ordPqt", metavar="视角",
                    help="视角，默认 ordPqt（按价格带）。可选："
                         + "、".join(f"{k}={v}" for k, v in INTERVAL_VIEWS.items()))
    iv.add_argument("--limit", type=int, default=10)
    iv.add_argument("--page", type=int, default=1)
    iv.add_argument("--raw", action="store_true")
    iv.add_argument("--out")
    iv.set_defaults(func=cmd_interval_analysis)
