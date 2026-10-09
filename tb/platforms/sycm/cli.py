#!/usr/bin/env python3
"""生意参谋店铺数据与经营分析命令：tb sycm <命令>。

取数方式与其他平台一样（见 tb/core/transport.py）：浏览器插件优先；Mac 上没装插件就读 Chrome 的 cookie；
请求、登录判断、风控词、护栏（请求数提醒 / 间隔）都在 tb.core 里，这里只放接口清单、参数拼装和输出。
稳定命令来自 sycm 页面请求与客户端 JS 的实际验证，覆盖大盘、商品、新品、销售、退款、客服与 Excel 导出。
运行 ``--help`` 查看当前完整命令面。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ...core import profiles, transport
from ...core.auth import NotLoggedIn, load_cookies
from ...core.bridge import BridgeRefused
from ...core.client import Client
from ...core.errors import TbError
from .platform import SYCM

REFERER_DETAIL_PAGE = "https://sycm.taobao.com/qos/service/frame/performance/detail/new"


def _validated_https_url(url: str) -> str:
    """Reject local/file/custom-scheme download URLs returned by the server."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise RuntimeError("服务端返回了不安全的下载地址（必须是无凭据的 HTTPS URL）")
    return url


class ClientCookies:
    """给调用方一个像 dict 的「cookie 视图」：`cookies.get("_tb_token_", "")`。
    实际读取走 client.cookie()——命令行读 cookie 模式读本地副本，插件模式向浏览器要（只放行平台声明的令牌类 cookie）。
    读到的值缓存在本次运行里。"""

    def __init__(self, client: Client):
        self.client = client
        self._cache: dict[str, str | None] = {}

    def get(self, name: str, default: str | None = None) -> str | None:
        if name not in self._cache:
            try:
                self._cache[name] = self.client.cookie(name)
            except BridgeRefused:   # 插件模式下不是令牌类的 cookie 读不到，按「没有」处理
                self._cache[name] = None
        return self._cache[name] or default

    def __contains__(self, name: str) -> bool:
        return bool(self.get(name))

    def __len__(self) -> int:
        return len(self.client.cookies)


# 由 main() 依据 --store 设置；非空时改读保存的 profile 而不是实时浏览器。
_ACTIVE_STORE: str | None = None
_CLIENT: Client | None = None


def make_client() -> Client:
    if _ACTIVE_STORE:   # 保存的登录态：只用命令行读 cookie 的方式
        return Client(SYCM, cookies=profiles.load_profile(SYCM, _ACTIVE_STORE))
    return transport.make_client(SYCM)


def load_taobao_cookies() -> ClientCookies:
    """取当前应使用的登录态（一次运行只建一个连接）。"""
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = make_client()
    return ClientCookies(_CLIENT)


def _api_get(path: str, params: dict[str, Any], cookies: ClientCookies, referer: str | None = None) -> dict[str, Any]:
    """对 sycm API 做一次 GET，返回完整响应。

    path 处理规则：
    - 以 `/` 开头 → 绝对路径，拼到 https://sycm.taobao.com 后
    - 否则 → 相对路径，拼到 https://sycm.taobao.com/csp/api/ 后（旧 CSP 接口）
    """
    host, rel = ("root", path) if path.startswith("/") else ("api", "/" + path)
    return cookies.client.get(host, rel, params, raw=True, name=path,
                              headers={"Referer": referer or REFERER_DETAIL_PAGE})


# ---------- 高频页面预设注册表 ----------
#
# 每个 preset 对应 sycm 的一个标准"日维度列表页面"。AI 代理可以一行命令调任一个。
# 字段：
#   path        — sycm API 路径（"/" 开头 = 绝对路径；否则拼到 /csp/api/）
#   orderBy     — 排序字段（找列表的关键参数，漏了大多返回 0 条）
#   referer     — 对应的 sycm 页面 URL（API 风控会查 Referer，最好真实）
#   desc        — 子命令帮助说明
#   show        — 在结果摘要里展示的字段名列表（按顺序）
#   param_style — "sycm-v1" (默认, csp/api 老列表接口) | "cc-v2" (新接口统一拼法，
#                 覆盖 /cc/*、/flow/*、/csp/api/* 三族，实测拼装一致)
#   list_path   — 从 response 里提取 list 的路径，点分；默认 "data.dataSource"
#                 cate 类用 "data"
#                 item-list / new-product / relate 类用 "data.data"
#   total_path  — list 总数字段路径；默认 "data.count"
#   extra_params — cc-v2 风格的额外 GET 参数（indexCode、cateId、device 等）

LIST_PRESETS: dict[str, dict[str, Any]] = {
    "reception-list": {
        "path": "ww/consultation/detail/list",
        "orderBy": "startTime",
        "bizCode": "receptionDetail-wwConsultation",
        "referer": "https://sycm.taobao.com/qos/service/frame/performance/detail/new",
        "desc": "旺旺咨询接待明细 (服务/接待明细)",
        "show": ["startTime", "endTime", "buyerNick", "psnNickName", "isUnReply"],
    },
    "evaluation-list": {
        "path": "evaluation/detail/list",
        "orderBy": "servTime",
        "bizCode": "qualityDetail-receptionEvaluation",
        "referer": "https://sycm.taobao.com/qos/service/after_sale/estimate",
        "desc": "邀评/评价明细 (服务/售后评价)",
        "show": ["servTime", "sendTime", "buyerNick", "psnNickName", "source", "lstEvaScore"],
    },
    "sale-shop-list": {
        "path": "shop/sale/analysis/list",
        "orderBy": "itemId",
        "bizCode": "saleDetail-shopSale",
        "referer": "https://sycm.taobao.com/fa/frame/trade_overview",
        "desc": "店铺商品销售排行 (商品/销售分析)",
        "show": ["itemId", "itemTitle", "shopPayAmt1d", "shopPayItmCnt1d", "servPayAmt1d", "silentPayAmt1d"],
    },
    "sale-item-list": {
        "path": "item/sale/detail/list",
        "orderBy": "startTime",
        "bizCode": "saleDetail-itemSale",
        "referer": "https://sycm.taobao.com/qos/service/frame/performance/detail/new",
        "desc": "订单销售明细 (交易/订单明细)",
        "show": ["createTime", "createAmt", "buyerNick", "accountNick", "isSlientFlow"],
    },
    "sale-cs-list": {
        "path": "ww/sale/detail/list",
        "orderBy": "startTime",
        "bizCode": "saleDetail-wwSale",
        "referer": "https://sycm.taobao.com/qos/service/frame/performance/detail/new",
        "desc": "客服销售明细 (旺旺销售)",
        "show": ["createTime", "buyerNick", "accountNick"],
    },
    "inquiry-loss-list": {
        "path": "inquiry/loss/list",
        "orderBy": "startTime",
        "bizCode": "lossDetail-inquiryLoss",
        "referer": "https://sycm.taobao.com/qos/service/frame/performance/detail/new",
        "desc": "询单流失明细 (服务/咨询分析)",
        "show": ["startTime", "endTime", "buyerNick", "psnNickName"],
    },
    "slow-rsps-list": {
        "path": "slow/rsps/detail/list",
        "orderBy": "startTime",
        "bizCode": "slow-rsps-detail-mxymx",
        "referer": "https://sycm.taobao.com/qos/service/frame/performance/detail/new",
        "desc": "慢响应明细 (服务/慢响应)",
        "show": ["dateId", "startTime", "endTime", "buyerNick", "psnNickName"],
    },
    "refund-item-list": {
        "path": "shop/refund/item/list",
        "orderBy": "itemCaseEndSucAmt",
        "referer": "https://sycm.taobao.com/fa/refund/analysis",
        "desc": "退款商品明细 (交易/退款分析)",
        "show": ["itemId", "itemName", "itemCaseEndSucAmt", "itemCaseEndSucCnt",
                 "itemCaseEndSucRate", "itemCaseEndSucReasonText"],
    },

    # ---- 商品大类 (cc-v2 风格接口) ----
    # 这些是 sycm 商品板块的真接口，HAR 直接抓出来的，response data 字段值多为 {value, cycleCrc, syncCrc} 对比结构
    "item-list": {
        "path": "/cc/item/view/top.json",
        "param_style": "cc-v2",
        "orderBy": "payAmt",
        "indexCode": ("payAmt,sucRefundAmt,payItmCnt,payByrCnt,payRate,payPct,"
                      "itemCartCnt,itemCltByrCnt,itmUv,stayTimeAvg,itmBounceRate,"
                      "seGuideUv,seGuidePayByrCnt,seGuidePayRate,uvAvgValue"),
        "extra_params": {"device": "0", "compareType": "cycle"},
        "referer": "https://sycm.taobao.com/cc/item_rank",
        "desc": "商品排行 / 商品 360 列表 (商品/商品排行 + 商品 360 共用此接口)",
        # 之前挂在这里的 /cc/item/portal/itemList.json 是本仓库反复踩过的
        # 同一类 bug：网页时间选择器停在「实时」档时录到的接口，日/7天/30天
        # 历史档实际打的是另一个完全不同的接口。
        # 实测（2026-08-05）：itemList.json 不论 indexCode 传几个值，返回的
        # 永远只有 itmUv/payAmt/payRate 3 个指标——不是权限或参数问题，是这
        # 个接口本身不认 indexCode。历史档页面真正调用的是
        # /cc/item/view/top.json；换过去后同一次调用能拿到 41 个字段。
        # 全仓库 grep 确认没有其它命令还在用 itemList.json，直接删掉，不留
        # 兼容层。
        #
        # 实测（2026-08-05）：indexCode 在 view/top.json 上不生效——传 2 个、
        # 15 个，或者干脆不传，返回的都是同一组固定 41 字段，不像
        # item-sku-attr / item-flow-source 那样按 indexCode 筛列。所以这里
        # 也谈不上"长度上限"：它根本不按这个参数过滤。继续传 indexCode 只是
        # 为了贴近页面真实请求形态，防着服务端将来真的启用过滤。
        #
        # 实测（2026-08-05，同一 itemId）：2026-07-29~08-04 (recent7) 与
        # 2026-07-06~08-04 (recent30) 两次调用的 payAmt 不同，是认日期的。
        #
        # 响应形状：data 是分页信封 {recordCount, data}，行列表在 data.data
        # （不是 data 本身——旧 itemList.json 才是 data 直接是行列表）。
        "list_path": "data.data",
        "total_path": "data.recordCount",
        # 只挑「支付/访客/加购/收藏/停留/跳出/搜索引导/退款」这条主线，其余
        # 已入 indexCode 的字段（如 payItmCnt/payByrCnt/uvAvgValue）用 --raw
        # 看，不在默认表里塞满 41 列。payPct 是已在别处验证过的「客单价」；
        # 指标选择器里的「件单价」在这 41 个字段里没找到对应字段码，没有勉强
        # 映射。
        "show": ["item", "payAmt", "itmUv", "payByrCnt", "payItmCnt", "payRate",
                 "payPct", "itemCartCnt", "itemCltByrCnt", "stayTimeAvg",
                 "itmBounceRate", "seGuideUv", "sucRefundAmt"],
    },
    "cate-list": {
        "path": "/cc/cockpit/marcro/cate.json",
        "param_style": "cc-v2",
        "orderBy": "payAmt",
        "indexCode": "payAmt,payAmtRatio,sucRefundAmt,payRate,itmUv",
        "extra_params": {"follow": "false", "cateType": "std"},
        "referer": "https://sycm.taobao.com/cc/new_cate_archives",
        "desc": "品类 360 / 宏观品类 (商品/品类)",
        "list_path": "data",
        "total_path": "",
        "show": ["cateName", "parentCateName", "payAmt", "payByrCnt", "itmUv", "payRate"],
    },
    "new-product-list": {
        "path": "/cc/new/product/item/list.json",
        "param_style": "cc-v2",
        "orderBy": "publishNewTime",
        # 页面指标选择器共 8 项（同时最多选 5，但接口不受这个限制）。
        # 2026-08-06 实测把 8 项一次全传，服务端 9 个字段全回、一个不丢——
        # 与 item-sku-list 的库存字段被静默丢弃是两回事，这里可以放心全要。
        "indexCode": ("publishNewTime,shopUvNew,addCartCntNew,collectCntNew,"
                       "addCartRateNew,payByrCntNew,payAmtNew,shopPayRateNew,uvWorth"),
        "extra_params": {"cateId": "0"},
        "referer": "https://sycm.taobao.com/cc/new_item_analysis",
        "desc": "新品追踪明细 (商品/新品追踪)",
        "list_path": "data.data",
        "total_path": "data.recordCount",
        "show": ["item", "publishNewTime", "shopUvNew", "addCartCntNew",
                  "collectCntNew", "addCartRateNew", "payByrCntNew",
                  "payAmtNew", "shopPayRateNew", "uvWorth"],
    },
}


# cc 系接口支持的窗口宽度（天）。实测：其它宽度服务端一律 code=1003 拒绝。
CC_WINDOW_DAYS = (1, 7, 15, 30)


def _num(v: Any) -> str:
    """一个数字单元格：浮点保留两位，None 打横杠（0 会被读成「有但为零」）。"""
    if v is None:
        return "-"
    return f"{v:.2f}" if isinstance(v, float) else str(v)


def _print_scalar_block(data: dict[str, Any], indent: str = "  ") -> None:
    """把一层 {字段码: 值} 打成人看得懂的行。

    2026-08-07：原来六处各自 `print(f"  {k}: {_value_of(v)}")`，于是
    `saleRateNew: 0.24060150375939848`、`statDate: 1785945600000` 一路打到屏幕上。
    列名和格式 fields.json 里都有，统一走 _field_label / _field_value。
    """
    for key, value in data.items():
        print(f"{indent}{_field_label(key)}: {_field_value(key, value)}")


def _field_label(code: str) -> str:
    """列名用 fields.json 里的中文名；字典里没有的原样打字段码，不猜。"""
    return (FIELDS_DICT.get(code) or {}).get("cn") or code


def _field_value(code: str, value: Any) -> str:
    """按字典的 fmt 打值。

    2026-08-07：在此之前这里直接 `_value_of()`，于是 `payRate=0.006838394217482196`
    这种裸小数一路打到屏幕上 —— 没人读得出来那是 0.68%。中文名和格式字典里
    本来就有（cn + fmt），查字典即可，不该在代码里再抄一份。
    """
    unwrapped = _value_of(value)
    if unwrapped is None:
        return ""          # 缺列打空白，不是字面量 "None"
    if isinstance(unwrapped, (int, float)) and not isinstance(unwrapped, bool):
        fmt = (FIELDS_DICT.get(code) or {}).get("fmt")
        if fmt == "epoch_ms":
            return _as_dates([unwrapped])[0]
        # fmt 认字典；字典没收录的退回 Rate 后缀启发式 —— 否则 itmVstPayByrRate
        # 这种未入典的比率会从 100.00% 退成 1.00，比改造前还糟。
        if fmt in ("pct", "rate") or (fmt is None and code.endswith("Rate")):
            return f"{unwrapped * 100:.2f}%"
        if isinstance(unwrapped, float):
            if fmt in ("int", "num") and unwrapped.is_integer():
                return str(int(unwrapped))
            return f"{unwrapped:.2f}"
    return str(unwrapped)


def _infer_cc_date_type(start_date: str, end_date: str) -> str:
    """cc 系（cc-v2 / flow-v2 / csp-item）的 dateType：单日 → day，7/15/30 天 → recentN。

    实测结论（2026-08-05，用 /cc/diagnose/coreIndex.json 逐日对照）：

    1. recentN 是相对 dateRange 的，不是相对今天。
       dateRange=2026-07-01|2026-07-07 + recent7 返回的 payAmt，与该窗口内
       七个单日各调一次得到的 payAmt 之和逐位相等；换成 2026-07-29|2026-08-04
       返回的是另一组值。
       返回的 statDate 也落在窗口末日。所以表头照 dateRange 打印区间是对的。
       （uv 不等于逐日相加，是窗口内按人去重，属正常口径，不是 bug。）

    2. 窗口宽度只支持 1/7/15/30 天。10 天窗口不论 dateType 传 day 还是
       recent10，服务端都以 code=1003 拒绝，coreIndex、退款(csp-item)、
       流量来源(flow-v2) 三个接口实测行为一致。
       所以这里不再静默回落成 day 去发一个必然失败的请求 —— 直接在客户端
       报清楚哪些宽度可用（设计文档 §8：已知业务错误要给明确提示）。
    """
    try:
        delta_days = (datetime.strptime(end_date, "%Y-%m-%d")
                      - datetime.strptime(start_date, "%Y-%m-%d")).days + 1
    except ValueError as e:
        raise ValueError(f"日期必须是 YYYY-MM-DD：{start_date} ~ {end_date}") from e
    if delta_days == 1:
        return "day"
    if delta_days not in CC_WINDOW_DAYS:
        raise ValueError(
            f"这个接口只支持 {'/'.join(str(d) for d in CC_WINDOW_DAYS)} 天的窗口，"
            f"你给的 {start_date} ~ {end_date} 是 {delta_days} 天。"
            f"服务端对其它宽度一律 code=1003 拒绝（2026-08-05 实测）。"
            f"请把 --end-date 调成距 --date 恰好 7/15/30 天，或只查单日。"
        )
    return f"recent{delta_days}"


def build_query_params(preset: dict[str, Any], *, start_date: str, end_date: str,
                        page_no: int, page_size: int, token: str,
                        extra: dict[str, str] | None = None) -> dict[str, str]:
    """按 preset 的 param_style 拼 query 参数（不含 `_` 时间戳，由调用方补）。

    键冲突时 `extra` 覆盖 preset 的 `extra_params`（调用点比预设更具体）。

    只有两种风格：
    - "cc-v2"    — 新接口的统一拼法，覆盖 /cc/*、/flow/*、/csp/api/* 三个
                   网关族。实测这三族的 query 拼装完全一致（dateRange +
                   dateType + page/pageSize + order/orderBy [+ indexCode]），
                   差异全在 path 与 extra_params 里，所以不为它们各起一个
                   风格名——同一条代码路径挂三个标签只会让人以为拼法不同。
                   将来真出现拼法分化，再按分化点拆新风格。
    - "sycm-v1"  — 老 csp/api 列表接口（startDate/endDate/pageNo 那套），默认。
    """
    style = preset.get("param_style", "sycm-v1")
    params: dict[str, str] = {"token": token}

    if style == "cc-v2":
        params.update({
            "dateRange": f"{start_date}|{end_date}",
            "dateType": preset.get("default_date_type")
                        or _infer_cc_date_type(start_date, end_date),
            "page": str(page_no),
            "pageSize": str(page_size),
            "order": "desc",
            "orderBy": preset["orderBy"],
        })
        if preset.get("indexCode"):
            params["indexCode"] = preset["indexCode"]
    else:
        params.update({
            "startDate": start_date.replace("-", ""),
            "endDate": end_date.replace("-", ""),
            "dateType": "day",
            "dateRange": "day",
            "orderBy": preset["orderBy"],
            "pageNo": str(page_no),
            "pageSize": str(page_size),
        })

    # extra_params 对所有 param_style 都生效。曾经只在一种风格里生效、其它风格
    # 静默丢弃，是个潜伏的 bug；每种风格都该能声明自己的固定附加参数。
    params.update(preset.get("extra_params", {}))
    params.update(extra or {})
    return params


def fetch_preset(preset_name: str, *, start_date: str, end_date: str,
                  page_no: int = 1, page_size: int = 10,
                  cookies: dict[str, str] | None = None,
                  extra: dict[str, str] | None = None) -> dict[str, Any]:
    """按预设名拉某个日期范围的列表。"""
    preset = LIST_PRESETS[preset_name]
    cookies = cookies or load_taobao_cookies()
    params = build_query_params(
        preset, start_date=start_date, end_date=end_date,
        page_no=page_no, page_size=page_size,
        token=cookies.get("_tb_token_", ""), extra=extra,
    )
    params["_"] = str(int(time.time() * 1000))
    return _api_get(preset["path"], params, cookies, referer=preset["referer"])


def fetch_refund_all_list(*, start_date: str, end_date: str,
                          query_type: str = "caseEnd", page_no: int = 1,
                          page_size: int = 100,
                          cookies: dict[str, str] | None = None) -> dict[str, Any]:
    """拉全部退款明细，可按申请、完结或原订单付款时间筛选。"""
    if query_type not in {"caseCreate", "caseEnd", "orderPay"}:
        raise ValueError(f"不支持的退款时间口径: {query_type}")
    cookies = cookies or load_taobao_cookies()
    sd, ed = start_date.replace("-", ""), end_date.replace("-", "")
    params = {
        "_": str(int(time.time() * 1000)),
        "token": cookies.get("_tb_token_", ""),
        "queryType": query_type,
        "dateType": "day",
        "dateRange": "1d" if sd == ed else "cz",
        "pageNo": str(page_no),
        "pageSize": str(page_size),
        "orderBy": "caseId",
        "order": "desc",
        "cardUid": "sycm-cli-refund-all",
    }
    path = "refund/all/detail/list"
    if query_type == "caseEnd":
        params.update({"endStartDate": sd, "endEndDate": ed})
    else:
        params.update({"startDate": sd, "endDate": ed})
        if query_type == "orderPay":
            path = "refund/all/detail/ord-pay/list"
    return _api_get(path, params, cookies, referer=REFERER_DETAIL_PAGE)


def fetch_all_refunds(*, start_date: str, end_date: str,
                      query_type: str = "caseEnd",
                      cookies: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """分页拉完整退款明细；按 caseId 去重。"""
    cookies = cookies or load_taobao_cookies()
    rows: list[dict[str, Any]] = []
    page_no, page_size, total = 1, 100, None
    while total is None or len(rows) < total:
        payload = fetch_refund_all_list(
            start_date=start_date, end_date=end_date, query_type=query_type,
            page_no=page_no, page_size=page_size, cookies=cookies,
        )
        data = payload.get("data") or {}
        batch = data.get("dataSource") or []
        total = int(data.get("count") or 0)
        rows.extend(r for r in batch if isinstance(r, dict))
        if not batch or len(rows) >= total:
            break
        page_no += 1
    deduped: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    for row in rows:
        case_id = row.get("caseId")
        # Missing IDs must not collapse unrelated rows into a single "None" record.
        if case_id in (None, ""):
            deduped.append(row)
            continue
        key = str(case_id)
        if key not in seen_case_ids:
            seen_case_ids.add(key)
            deduped.append(row)
    return deduped


def summarize_refund_origins(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """汇总退款完结事件来自哪些付款日、退款场景及间隔。"""
    from collections import Counter, defaultdict

    pay_days: Counter[str] = Counter()
    pay_day_amounts: dict[str, float] = defaultdict(float)
    scenes: Counter[str] = Counter()
    scene_amounts: dict[str, float] = defaultdict(float)
    ages: Counter[str] = Counter()
    age_amounts: dict[str, float] = defaultdict(float)
    age_order = ("当日", "1-3天", "4-7天", "8-14天", "15-30天", "30天以上")
    for row in rows:
        amount = float(row.get("refundRealAmt") or 0)
        pay_day = str(row.get("ordPayTime") or "")[:10] or "缺失"
        scene = str(row.get("caseSceneType") or "未知")
        pay_days[pay_day] += 1
        pay_day_amounts[pay_day] += amount
        scenes[scene] += 1
        scene_amounts[scene] += amount
        try:
            paid = datetime.fromisoformat(str(row["ordPayTime"]))
            ended = datetime.fromisoformat(str(row["caseEndTime"]))
            days = (ended.date() - paid.date()).days
        except (KeyError, TypeError, ValueError):
            continue
        bucket = ("当日" if days == 0 else "1-3天" if days <= 3 else
                  "4-7天" if days <= 7 else "8-14天" if days <= 14 else
                  "15-30天" if days <= 30 else "30天以上")
        ages[bucket] += 1
        age_amounts[bucket] += amount
    return {
        "records": len(rows),
        "uniqueOrders": len({str(r.get("orderId")) for r in rows if r.get("orderId")}),
        "refundRealAmt": round(sum(float(r.get("refundRealAmt") or 0) for r in rows), 2),
        "scenes": [{"name": k, "count": v, "amount": round(scene_amounts[k], 2)}
                   for k, v in scenes.most_common()],
        "payDays": [{"date": k, "count": pay_days[k], "amount": round(pay_day_amounts[k], 2)}
                    for k in sorted(pay_days, reverse=True)],
        "ageBuckets": [{"name": k, "count": ages[k], "amount": round(age_amounts[k], 2)}
                       for k in age_order],
    }


def _dig(obj: Any, path: str) -> Any:
    """从嵌套 dict 里按 'a.b.c' 路径取值。空 path 返回 obj。"""
    if not path:
        return obj
    cur = obj
    for key in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(key)
        else:
            return None
    return cur


def _value_of(field: Any) -> Any:
    """sycm cc-v2 字段值常是嵌套对象，提取一个"展示用"标量：
    - {value, cycleCrc, syncCrc} → value
    - {title, itemId, ...} (item 商品对象) → "<itemId> <title 前 24 字>"
    - {cateName, ...} → cateName
    - 空 dict → "—"
    - 其他 dict → 转字符串截断
    """
    if not isinstance(field, dict):
        return field
    if "value" in field:
        return field["value"]
    if "title" in field and "itemId" in field:
        title = str(field.get("title", ""))[:24]
        return f"{field.get('itemId')} {title}"
    if "cateName" in field:
        return field["cateName"]
    if not field:
        return "—"
    return str(field)[:80]


# ---------- 接口封装 ----------

def fetch_consultation_list(
    *,
    start_date: str,
    end_date: str,
    page_no: int = 1,
    page_size: int = 10,
    order_by: str = "startTime",
    cookies: dict[str, str] | None = None,
) -> dict[str, Any]:
    """旺旺咨询明细 列表。日期格式 YYYY-MM-DD，内部转 YYYYMMDD。"""
    cookies = cookies or load_taobao_cookies()
    sd = start_date.replace("-", "")
    ed = end_date.replace("-", "")
    params = {
        "_": str(int(time.time() * 1000)),
        "token": cookies.get("_tb_token_", ""),
        "startDate": sd,
        "endDate": ed,
        "dateType": "day",
        "dateRange": "day",
        "orderBy": order_by,
        "pageNo": str(page_no),
        "pageSize": str(page_size),
    }
    return _api_get("ww/consultation/detail/list", params, cookies)


def fetch_chat_detail(
    data_id: str,
    page_no: int = 1,
    cookies: dict[str, str] | None = None,
) -> dict[str, Any]:
    """单个会话的全部消息（每页约 10 条，>10 条需多页拉）。"""
    cookies = cookies or load_taobao_cookies()
    params = {
        "dataId": data_id,
        "dateType": "1",
        "dateRange": "1",
        "startDate": "1",
        "endDate": "1",
        "pageNo": str(page_no),
    }
    return _api_get("detail/list", params, cookies)


def fetch_chat_detail_all_pages(
    data_id: str, cookies: dict[str, str], max_pages: int = 10
) -> list[dict[str, Any]]:
    """翻完所有页，合并 dataSource。"""
    all_rows: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        data = fetch_chat_detail(data_id, page, cookies)
        rows = data.get("data", {}).get("dataSource", []) or []
        if not rows:
            break
        all_rows.extend(rows)
    return all_rows


# ---------- Excel 导出（async-excel + 轮询 + 下载，三步合一）----------

def trigger_excel_export(preset_name: str, *, start_date: str, end_date: str,
                          cookies: dict[str, str]) -> int:
    """触发某 preset 的 async-excel 导出，返回 task ID。"""
    preset = LIST_PRESETS[preset_name]
    biz_code = preset.get("bizCode")
    if not biz_code:
        raise RuntimeError(f"preset {preset_name} 未配置 bizCode，无法导出")
    excel_path = preset["path"].replace("/list", "/async-excel")
    sd = start_date.replace("-", "")
    ed = end_date.replace("-", "")
    params = {
        "_": str(int(time.time() * 1000)),
        "token": cookies.get("_tb_token_", ""),
        "startDate": sd,
        "endDate": ed,
        "dateType": "day",
        "dateRange": "day",
        "orderBy": preset["orderBy"],
        "bizCode": biz_code,
    }
    resp = _api_get(excel_path, params, cookies, referer=preset.get("referer"))
    if not resp.get("success"):
        raise RuntimeError(f"导出触发失败: {resp.get('message') or resp}")
    return int(resp.get("data"))


def poll_excel_task(task_id: int, biz_code: str, *, cookies: dict[str, str],
                     max_wait_sec: int = 60, poll_interval: int = 3) -> dict[str, Any]:
    """轮询任务列表直到指定 task_id 完成 (status='ok' / process=100)。"""
    deadline = time.time() + max_wait_sec
    while time.time() < deadline:
        params = {
            "_": str(int(time.time() * 1000)),
            "token": cookies.get("_tb_token_", ""),
            "bizCode": biz_code,
        }
        resp = _api_get("file/task-list.json", params, cookies)
        tasks = (resp.get("data") or {}).get("result") or []
        match = next((t for t in tasks if int(t.get("id", -1)) == task_id), None)
        if match and match.get("status") == "ok" and (match.get("process") or 0) >= 100:
            return match
        time.sleep(poll_interval)
    raise TimeoutError(f"等任务 #{task_id} 超时 ({max_wait_sec}s)")


def get_excel_download_url(task_id: int, biz_code: str, *, cookies: dict[str, str]) -> str:
    """拿 OSS 临时下载 URL。"""
    params = {
        "_": str(int(time.time() * 1000)),
        "token": cookies.get("_tb_token_", ""),
        "id": str(task_id),
        "bizCode": biz_code,
    }
    resp = _api_get("file/url", params, cookies)
    if not resp.get("success"):
        raise RuntimeError(f"拿下载 URL 失败: {resp.get('message') or resp}")
    return resp["data"]


def cmd_excel(args: argparse.Namespace) -> None:
    """一行搞定：触发导出 → 轮询 → 下载到本地。"""
    cookies = load_taobao_cookies()
    preset = LIST_PRESETS[args.preset_name]
    biz_code = preset.get("bizCode")
    if not biz_code:
        print(f"⚠️  {args.preset_name} 还没配置 bizCode，无法导出 Excel", file=sys.stderr)
        sys.exit(1)
    end = args.end_date or args.date

    print(f"[1/4] 触发 [{preset['desc']}] 导出 ({args.date} ~ {end})...", file=sys.stderr)
    task_id = trigger_excel_export(args.preset_name, start_date=args.date,
                                    end_date=end, cookies=cookies)
    print(f"       任务 ID: {task_id}", file=sys.stderr)

    print(f"[2/4] 等服务端生成 Excel（最多 {args.wait} 秒）...", file=sys.stderr)
    task = poll_excel_task(task_id, biz_code, cookies=cookies, max_wait_sec=args.wait)
    record_num = task.get("recordNum", "?")
    server_filename = task.get("fileName", "?")
    print(f"       完成。{record_num} 条记录。", file=sys.stderr)

    print("[3/4] 取 OSS 下载链接...", file=sys.stderr)
    url = _validated_https_url(get_excel_download_url(task_id, biz_code, cookies=cookies))

    # 默认输出路径
    if args.out:
        out_path = Path(args.out)
    else:
        Path.home().joinpath("Downloads/sycm-exports").mkdir(parents=True, exist_ok=True)
        # 用 server 文件名最后一段（去掉路径）
        suggested = Path(server_filename.replace("\\", "/")).name
        if not suggested or suggested in {".", ".."}:
            suggested = f"{args.preset_name}_{args.date}.xlsx"
        out_path = Path.home() / "Downloads" / "sycm-exports" / suggested

    print(f"[4/4] 下载到 {out_path} ...", file=sys.stderr)
    # URL is constrained to HTTPS above.
    urllib.request.urlretrieve(url, out_path)  # nosec B310
    size_kb = out_path.stat().st_size / 1024
    print(f"\n✅ 完成: {out_path} ({size_kb:.1f} KB, {record_num} 条记录)")


def cmd_excel_tasks(args: argparse.Namespace) -> None:
    """列出所有 preset 名下的导出任务（最近的）。"""
    cookies = load_taobao_cookies()
    for name, preset in LIST_PRESETS.items():
        biz = preset.get("bizCode")
        if not biz:
            continue
        try:
            params = {
                "_": str(int(time.time() * 1000)),
                "token": cookies.get("_tb_token_", ""),
                "bizCode": biz,
            }
            resp = _api_get("file/task-list.json", params, cookies)
            tasks = (resp.get("data") or {}).get("result") or []
            if not tasks:
                continue
            print(f"\n## {name} (bizCode={biz})")
            for t in tasks[:5]:
                status = t.get("status", "?")
                proc = t.get("process", 0)
                rec = t.get("recordNum", "?")
                ts = t.get("gmtCreate", 0)
                ts_str = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M") if ts else "?"
                print(f"  [{t.get('id')}] {ts_str}  {status} {proc}%  {rec} 条")
        except Exception as e:
            print(f"## {name}: 查询失败 - {e}", file=sys.stderr)
        time.sleep(1)


# ---------- 命令 ----------

def cmd_doctor(args: argparse.Namespace) -> None:
    print("== tb sycm doctor ==")
    try:
        cookies = load_taobao_cookies()
        print(f"✓ 读到 {len(cookies)} 个 taobao 域 cookie" if len(cookies)
              else "✓ 通过浏览器插件取数（登录态在浏览器里，不读 cookie 文件）")
        if not cookies.get("_tb_token_"):
            print("✗ 没有 _tb_token_（请在浏览器里打开并登录 https://sycm.taobao.com，等首页加载完再试）")
            sys.exit(1)
        print("✓ _tb_token_ = <present>")
        for k in ("cna", "t", "_m_h5_tk", "thw"):
            if k in cookies:
                print(f"✓ {k} = <present>")
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        probe = fetch_preset(
            "sale-shop-list", start_date=yesterday, end_date=yesterday,
            page_no=1, page_size=1, cookies=cookies,
        )
        count = (probe.get("data") or {}).get("count")
        print(f"✓ sale-shop-list probe = ok (count={count})")
    except Exception as e:
        print(f"✗ {e}")
        sys.exit(1)


def cmd_list(args: argparse.Namespace) -> None:
    data = fetch_consultation_list(
        start_date=args.date,
        end_date=args.date,
        page_no=args.page,
        page_size=args.size,
    )
    if args.raw:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    rows = data.get("data", {}).get("dataSource", []) or []
    total = data.get("data", {}).get("count", 0)
    print(f"# {args.date} 共 {total} 条咨询，本页 {len(rows)} 条")
    print()
    for i, r in enumerate(rows, 1):
        start = r.get("startTime", r.get("gmtCreated", ""))[:19]
        end = r.get("endTime", "")[:19]
        buyer = r.get("buyerNick", "?")
        cs = r.get("accountNick") or r.get("psnNickName", "?")
        replied = r.get("replied") or r.get("isReply", "")
        data_id = r.get("dataId", "")
        print(f"[{i}] {start} – {end[11:] if end else '?'}  买家 {buyer:<8}  客服 {cs:<20}  回复={replied}")
        print(f"    dataId={data_id}")
    print()


def cmd_preset_list(args: argparse.Namespace) -> None:
    """命名预设的列表查询：tb sycm <preset-name> --date ... --limit N"""
    end = args.end_date or args.date
    data = fetch_preset(args.preset_name, start_date=args.date, end_date=end,
                         page_no=args.page, page_size=args.limit)
    if args.out:
        Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"已写入 {args.out}", file=sys.stderr)
        return
    if args.raw:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    preset = LIST_PRESETS[args.preset_name]
    list_path = preset.get("list_path", "data.dataSource")
    total_path = preset.get("total_path", "data.count")
    rows = _dig(data, list_path) or []
    if not isinstance(rows, list):
        rows = []
    total = _dig(data, total_path) if total_path else None
    print(f"# {preset['desc']}")
    head = f"# {args.date}{' ~ ' + end if end != args.date else ''}"
    if total is not None:
        head += f"  共 {total} 条，本页 {len(rows)}"
    else:
        head += f"  本页 {len(rows)} 条"
    print(head + "\n")
    if not rows:
        print("(空)  — 提示：加 --raw 看完整 JSON 排查")
        return
    show = preset["show"]
    for i, r in enumerate(rows, 1):
        if not isinstance(r, dict):
            print(f"[{i:2}] {r}")
            continue
        vals = " | ".join(f"{_field_label(k)}={_field_value(k, r.get(k, '?'))}"
                          for k in show)
        print(f"[{i:2}] {vals}")


def cmd_refund_all_list(args: argparse.Namespace) -> None:
    end = args.end_date or args.date
    query_type = {"case-end": "caseEnd", "case-create": "caseCreate",
                  "order-pay": "orderPay"}[args.by]
    data = fetch_refund_all_list(
        start_date=args.date, end_date=end, query_type=query_type,
        page_no=args.page, page_size=args.limit,
    )
    if args.out:
        Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"已写入 {args.out}", file=sys.stderr)
        return
    if args.raw:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    payload = data.get("data") or {}
    rows = payload.get("dataSource") or []
    print(f"# 全部退款明细  {args.date}{' ~ ' + end if end != args.date else ''} "
          f"按 {args.by}，共 {payload.get('count', 0)} 条，本页 {len(rows)} 条\n")
    for i, row in enumerate(rows, 1):
        print(f"[{i:2}] 完结={row.get('caseEndTime', '-')} | 付款={row.get('ordPayTime', '-')} | "
              f"场景={row.get('caseSceneType', '-')} | 实退={row.get('refundRealAmt', '-')} | "
              f"商品={str(row.get('itemTitle') or '-')[:32]}")


def cmd_refund_origin_analysis(args: argparse.Namespace) -> None:
    end = args.end_date or args.date
    summary = summarize_refund_origins(fetch_all_refunds(
        start_date=args.date, end_date=end, query_type="caseEnd"))
    if args.raw or args.out:
        text = json.dumps(summary, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(text)
            print(f"已写入 {args.out}", file=sys.stderr)
        else:
            print(text)
        return
    print(f"# 退款完结来源分析  {args.date}{' ~ ' + end if end != args.date else ''}")
    print(f"# {summary['records']} 笔 / {summary['uniqueOrders']} 个订单，成功退款 "
          f"{summary['refundRealAmt']:,.2f} 元\n")
    print("## 退款场景")
    for row in summary["scenes"]:
        print(f"  {row['name']}: {row['count']} 笔，{row['amount']:,.2f} 元")
    print("\n## 原订单付款日")
    for row in summary["payDays"]:
        print(f"  {row['date']}: {row['count']} 笔，{row['amount']:,.2f} 元")
    print("\n## 从付款到退款完结")
    for row in summary["ageBuckets"]:
        print(f"  {row['name']}: {row['count']} 笔，{row['amount']:,.2f} 元")
    print("\n注：这是退款事件归属；真实退货率还要用同一付款批次的支付订单/件数作分母，"
          "并只保留“退货退款”，不能把未发货退款混进去。")


def _fetch_cc_v2_scalar(path: str, *, start_date: str, end_date: str,
                          extra: dict[str, str] | None = None,
                          referer: str | None = None,
                          cookies: dict[str, str] | None = None) -> dict[str, Any]:
    """cc-v2 风格的非 list 接口（overview / trend 等返回 {self, industry} 对象）。"""
    cookies = cookies or load_taobao_cookies()
    date_type = "day" if start_date == end_date else "recent"
    params = {
        "_": str(int(time.time() * 1000)),
        "token": cookies.get("_tb_token_", ""),
        "dateRange": f"{start_date}|{end_date}",
        "dateType": date_type,
    }
    if extra:
        params.update(extra)
    return _api_get(path, params, cookies, referer=referer)


def cmd_new_product_overview(args: argparse.Namespace) -> None:
    """新品总览 (商品/新品追踪 → 顶部汇总卡)"""
    end = args.end_date or args.date
    data = _fetch_cc_v2_scalar(
        "/cc/new/product/overview.json",
        start_date=args.date, end_date=end,
        extra={"cateId": str(args.cate_id)},
        referer="https://sycm.taobao.com/cc/new_item_analysis",
    )
    if args.out:
        Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"已写入 {args.out}", file=sys.stderr)
        return
    if args.raw:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    d = data.get("data", {}) or {}
    self_ = d.get("self") or {}
    print(f"# 新品总览  {args.date}{' ~ ' + end if end != args.date else ''}  cateId={args.cate_id}")
    for k, v in self_.items():
        print(f"  {_field_label(k)}: {_field_value(k, v)}")


# 趋势表展示哪几个指标、按什么顺序。中文名和格式不写在这里 ——
# 那两样 fields.json 已经有了（2026-08-07 把这批指标名录进字典时补齐的），
# 再抄一份就是第二个真相来源。
NEW_PRODUCT_TREND_METRICS = ("shopUvNew", "addCartCntNew", "collectCntNew",
                              "payByrCntNew", "payAmtNew", "shopPayRateNew",
                              "uvWorth")


# sycm 的 statDate 是**北京时间零点**的毫秒时间戳。用本机时区换算会在
# UTC+8 以西的机器上整体倒退一天（伦敦 -> 前一天 17:00，纽约 -> 前一天 12:00），
# 日期标签静默错位。固定按 +08:00 换算。
_BEIJING = timezone(timedelta(hours=8))


def _as_dates(series: list[Any]) -> list[str]:
    """statDate 是毫秒时间戳。打 1785945600000 等于没打，转成 YYYY-MM-DD。"""
    out = []
    for v in series:
        if isinstance(v, (int, float)) and v > 10_000_000_000:
            out.append(datetime.fromtimestamp(v / 1000, _BEIJING).strftime("%Y-%m-%d"))
        else:
            out.append(str(v))
    return out


def _print_new_product_trend(data: dict[str, Any]) -> None:
    """把 {self|industry: {指标: [30 个值]}} 渲染成按日的表。

    2026-08-07 补：原来这里只打「self: 1 项 / industry: 1 项」加一句
    「建议加 --raw 看完整 JSON」——等于没渲染。实际结构很规整：
    每个指标一条等长序列，`statDate` 就是对应的日期序列。
    """
    self_data = data.get("self") or {}
    industry = data.get("industry") or {}
    dates = self_data.get("statDate") or industry.get("statDate") or []
    if not dates:
        print("（无数据）这个类目/窗口没有新品趋势。")
        return

    cols = [c for c in NEW_PRODUCT_TREND_METRICS if c in self_data]
    print("日期\t" + "\t".join(_field_label(c) for c in cols))
    for i, day in enumerate(_as_dates(dates)):
        cells = []
        for code in cols:
            series = self_data.get(code) or []
            v = series[i] if i < len(series) else None
            cells.append("-" if v is None else _field_value(code, v))
        print(f"{day}\t" + "\t".join(cells))

    averages = []
    for code in cols:
        series = industry.get(code)
        if isinstance(series, list) and series:
            avg = sum(series) / len(series)
            averages.append(f"{_field_label(code)}={_field_value(code, avg)}")
    if averages:
        print("# 同行对照（industry，整窗均值）：" + "  ".join(averages))
    print("# 序列按日期升序，与页面趋势图同一份数据。--raw 可看全部 14 个指标。")


def cmd_new_product_trend(args: argparse.Namespace) -> None:
    """新品趋势 (商品/新品追踪 → 趋势图)"""
    end = args.end_date or args.date
    data = _fetch_cc_v2_scalar(
        "/cc/new/product/trend.json",
        start_date=args.date, end_date=end,
        extra={"cateId": str(args.cate_id)},
        referer="https://sycm.taobao.com/cc/new_item_analysis",
    )
    if args.out:
        Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"已写入 {args.out}", file=sys.stderr)
        return
    if args.raw:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    print(f"# 新品趋势  {args.date}{' ~ ' + end if end != args.date else ''}"
          f"  cateId={args.cate_id}")
    _print_new_product_trend(data.get("data") or {})


def _fetch_live_guide(path: str, *, start_date: str, end_date: str,
                      device: str, index_code: str, trend_type: str | None = None,
                      cookies: dict[str, str] | None = None) -> dict[str, Any]:
    """直播实时引导读取接口。

    参数来自真实页面 HAR：dateRange/dateType/device/indexCode；趋势接口额外需要 type。
    该接口没有分页：overview 是当前实时汇总，trend 返回 today/yesterday 两组趋势对象。
    """
    cookies = cookies or load_taobao_cookies()
    params = {
        "_": str(int(time.time() * 1000)),
        "token": cookies.get("_tb_token_", ""),
        "dateRange": f"{start_date}|{end_date}",
        "dateType": "today" if start_date == end_date == date.today().isoformat() else "day",
        "device": device,
        "indexCode": index_code,
    }
    if trend_type is not None:
        params["type"] = trend_type
    return _api_get(path, params, cookies, referer="https://sycm.taobao.com/flow/live.htm")


def _emit_json_or_file(data: dict[str, Any], args: argparse.Namespace) -> bool:
    """处理所有命名读取命令的 --raw / --out；返回是否已经输出。"""
    if args.out:
        Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"已写入 {args.out}", file=sys.stderr)
        return True
    if args.raw:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return True
    return False


def cmd_live_guide_overview(args: argparse.Namespace) -> None:
    """流量/直播实时引导 → 实时汇总卡（只读）。"""
    end = args.end_date or args.date
    data = _fetch_live_guide(
        "/flow/new/live/guide/trend/overview.json", start_date=args.date, end_date=end,
        device=args.device, index_code=args.index_code,
    )
    if _emit_json_or_file(data, args):
        return
    metrics = ((data.get("data") or {}).get("data") or {})
    print(f"# 直播实时引导汇总  {args.date}{' ~ ' + end if end != args.date else ''}")
    for key, value in metrics.items():
        print(f"  {_field_label(key)}: {_field_value(key, value)}")


def cmd_live_guide_trend(args: argparse.Namespace) -> None:
    """流量/直播实时引导 → today/yesterday 趋势对象（只读）。"""
    end = args.end_date or args.date
    data = _fetch_live_guide(
        "/flow/new/live/guide/trend.json", start_date=args.date, end_date=end,
        device=args.device, index_code=args.index_code, trend_type=args.type,
    )
    if _emit_json_or_file(data, args):
        return
    periods = ((data.get("data") or {}).get("data") or {})
    print(f"# 直播实时引导趋势  {args.date}{' ~ ' + end if end != args.date else ''}")
    for period, values in periods.items():
        keys = ", ".join(values.keys()) if isinstance(values, dict) else type(values).__name__
        print(f"  {period}: {keys}")


def cmd_preheating_metrics(args: argparse.Namespace) -> None:
    """店铺/预热看板 → 当前可读指标卡（只读、无分页）。"""
    cookies = load_taobao_cookies()
    data = _api_get(
        "/portal/shop/preheating/dashboard/metrics.json",
        {"_": str(int(time.time() * 1000)), "token": cookies.get("_tb_token_", "")},
        cookies,
        referer="https://sycm.taobao.com/portal/shop/preheating.htm",
    )
    content = data.get("content") or {}
    content_code = content.get("code")
    if content_code not in (None, 0, 200, "0", "200"):
        raise RuntimeError(f"生意参谋业务失败 code={content_code}: {content.get('message') or ''}")
    if _emit_json_or_file(data, args):
        return
    print("# 店铺预热看板指标")
    for key, value in (content.get("data") or {}).items():
        print(f"  {_field_label(key)}: {_field_value(key, value)}")


def _content_data_or_error(payload: dict[str, Any]) -> dict[str, Any]:
    """处理 portal 接口的 {hasError, content:{code,data,message}} 响应包装。"""
    content = payload.get("content") or {}
    code = content.get("code")
    if payload.get("hasError") is True or code not in (None, 0, 200, "0", "200"):
        raise RuntimeError(f"生意参谋业务失败 code={code}: {content.get('message') or ''}")
    data = content.get("data")
    return data if isinstance(data, dict) else {"_value": data}


def _fetch_order_portal(path: str, *, date_value: str,
                        extra: dict[str, str] | None = None,
                        cookies: dict[str, str] | None = None) -> dict[str, Any]:
    """首页“客单”卡片的已验证 portal 读取接口。"""
    cookies = cookies or load_taobao_cookies()
    params = {
        "_": str(int(time.time() * 1000)),
        "token": cookies.get("_tb_token_", ""),
        "dateType": "day",
        "dateRange": f"{date_value}|{date_value}",
    }
    if extra:
        params.update(extra)
    return _api_get(path, params, cookies, referer="https://sycm.taobao.com/portal/home.htm")


def cmd_order_overview(args: argparse.Namespace) -> None:
    """首页/客单 → 连带率与平均购买件数汇总（只读）。"""
    response = _fetch_order_portal("/portal/order/index/v2.json", date_value=args.date)
    if _emit_json_or_file(response, args):
        return
    data = _content_data_or_error(response)
    print(f"# 客单汇总  {args.date}")
    for scope in ("my", "rivalAvg"):
        values = data.get(scope) or {}
        print(f"## {scope}")
        for key, value in values.items():
            print(f"  {_field_label(key)}: {_field_value(key, value)}")


def cmd_order_trend(args: argparse.Namespace) -> None:
    """首页/客单 → 截止日 30 日趋势（只读、接口固定窗口）。"""
    response = _fetch_order_portal("/portal/order/indexTrend/v2.json", date_value=args.date)
    if _emit_json_or_file(response, args):
        return
    data = _content_data_or_error(response)
    print(f"# 客单趋势  截止 {args.date}（页面接口固定 30 日窗口）")
    for scope in ("my", "rivalAvg"):
        values = data.get(scope) or {}
        detail = ", ".join(
            f"{key}={len(value) if isinstance(value, list) else type(value).__name__}"
            for key, value in values.items()
        )
        print(f"  {scope}: {detail}")


def cmd_order_distribution(args: argparse.Namespace) -> None:
    """首页/客单 → 买家客单价分布（只读、6 个价格带）。"""
    response = _fetch_order_portal(
        "/portal/order/distribute.json", date_value=args.date,
        extra={"indexCode": "payOrderByrCnt"},
    )
    if _emit_json_or_file(response, args):
        return
    data = _content_data_or_error(response)
    print(f"# 客单分布  截止 {args.date}（每价格带为固定 30 日序列）")
    for band, series in data.items():
        print(f"  {band}: {len(series) if isinstance(series, list) else type(series).__name__} 点")


def cmd_order_recommend(args: argparse.Namespace) -> None:
    """首页/客单 → 商品搭配推荐组合（只读、当前为固定推荐集）。"""
    response = _fetch_order_portal(
        "/portal/order/recommend.json", date_value=args.date,
        extra={"page": "1", "pageSize": "10"},
    )
    if _emit_json_or_file(response, args):
        return
    data = _content_data_or_error(response).get("_value") or []
    print(f"# 商品搭配推荐  {args.date}（共 {len(data)} 组；页面接口无可靠翻页）")
    for i, row in enumerate(data, 1):
        if not isinstance(row, dict):
            continue
        items = row.get("item") or []
        titles = " + ".join(str(x.get("title") or "?")[:24] for x in items if isinstance(x, dict))
        print(
            f"  [{i:>2}] {titles} | commonBuy={_value_of(row.get('commBuyCnt'))} "
            f"payAmt={_value_of(row.get('payAmt'))} items={len(items)}"
        )


def _print_board_scopes(data: dict[str, Any], scopes: tuple[str, ...] = ("self",)) -> None:
    """打印首页 board 接口的对标档指标（self=本店 / rivalAvg=同行平均 / rivalGood=同行优秀）。"""
    for scope in scopes:
        values = data.get(scope)
        if not isinstance(values, dict):
            continue
        print(f"## {scope}")
        for key, value in values.items():
            print(f"  {_field_label(key)}: {_field_value(key, value)}")


def cmd_home_overview(args: argparse.Namespace) -> None:
    """首页/数据概览 → 当日核心指标（支付金额/访客/转化率/退款额率/加购…，只读）。"""
    response = _fetch_order_portal(
        "/portal/coreIndex/new/overview/v3.json", date_value=args.date,
        extra={"needCycleCrc": "true"},
    )
    if _emit_json_or_file(response, args):
        return
    data = _content_data_or_error(response)
    print(f"# 首页数据概览  {args.date}（本店 self；每项 value=值 cycleCrc=环比）")
    _print_board_scopes(data, ("self",))


def cmd_home_trend(args: argparse.Namespace) -> None:
    """首页/数据概览 → 截止日趋势（只读、接口固定窗口）。"""
    response = _fetch_order_portal(
        "/portal/coreIndex/new/trend/v3.json", date_value=args.date,
    )
    if _emit_json_or_file(response, args):
        return
    data = _content_data_or_error(response)
    print(f"# 首页数据概览趋势  截止 {args.date}")
    for scope in ("self", "rivalAvg"):
        values = data.get(scope) or {}
        detail = ", ".join(
            f"{key}={len(value) if isinstance(value, list) else type(value).__name__}"
            for key, value in values.items()
        )
        print(f"  {scope}: {detail}")


def cmd_grow_factor(args: argparse.Namespace) -> None:
    """首页/增长因子 → 广告引导/直播/新品/会员成交额（只读）。"""
    response = _fetch_order_portal(
        "/portal/board/grow/factor/overview.json", date_value=args.date,
        extra={"device": "2"},
    )
    if _emit_json_or_file(response, args):
        return
    data = _content_data_or_error(response)
    print(f"# 增长因子  {args.date}（本店 self；newPortalAdPayAmt=广告引导 "
          f"portalLivePayAmt=直播 newItmPayAmt=新品 mbrPayAmt=会员）")
    _print_board_scopes(data, ("self",))


# 首页“数据概览”表格：字段 → 中文标签 + 分组 + 格式。
# 2026-07-18：对着页面「数据概览」展开的完整 32 项(支付10/意向7/履约售后10/推广5)逐格锁定，
# 中文名照抄页面，字段码用「较上一周期」百分比做唯一键反查确认。
# fmt: amt=金额2位 / int=整数 / pct=百分比 / num=2位小数纯数值(单位在名字里)。取值走 self.<field>.value。
HOME_TABLE_ROWS: tuple[tuple[str, str, str, str], ...] = (
    # —— 支付 10 ——
    ("支付",   "支付金额",          "payAmt",            "amt"),
    ("支付",   "净支付金额",        "netPaymentAmount",  "amt"),
    ("支付",   "访客数",            "uv",                "int"),
    ("支付",   "支付买家数",        "payByrCnt",         "int"),
    ("支付",   "支付转化率",        "payRate",           "pct"),
    ("支付",   "浏览量",            "pv",                "int"),
    ("支付",   "平均停留时长",      "stayTime",          "num"),
    ("支付",   "支付子订单数",      "subPayOrdSubCnt",   "int"),
    ("支付",   "支付件数",          "payItmCnt",         "int"),
    ("支付",   "客单价",            "payPct",            "amt"),
    # —— 意向 7 ——
    ("意向",   "加购人数",          "cartByrCnt",        "int"),
    ("意向",   "商品收藏人数",      "cltItmCnt",         "int"),
    ("意向",   "加购件数",          "cartItemCnt",       "int"),
    ("意向",   "老客复购金额",      "rePurchasePayAmount", "amt"),
    ("意向",   "老客复购人数",      "payOldByrCnt",      "int"),
    ("意向",   "老客复购率",        "hasPurchaseUbyCntRate", "pct"),
    ("意向",   "咨询率",            "consultRate",       "pct"),
    # —— 履约售后 10 ——
    ("履约售后", "签收退款率",        "realPayrealRfdRate", "pct"),
    ("履约售后", "退款金额(完结时间)", "rfdSucAmt",         "amt"),
    ("履约售后", "退款金额(支付时间)", "payShopRfdAmt",     "amt"),
    ("履约售后", "金额退款率",        "payAmtRfdRate",     "pct"),
    ("履约售后", "订单退款率",        "ordRfdRate",        "pct"),
    ("履约售后", "退款处理时长(天)",  "rfdFinshDur",       "num"),
    ("履约售后", "旺旺人工响应时长(秒)", "wwReplyManualAvgTimeLen", "num"),
    ("履约售后", "平台判责率",        "slrRespRate",       "pct"),
    ("履约售后", "24小时揽收及时率",  "gotInTime24hRate",  "pct"),
    ("履约售后", "物流到货时长(小时)", "avgSignTimeHh",     "num"),
    # —— 推广 5 ——
    ("推广",   "关键词推广费",      "p4pExpendAmt",      "amt"),
    ("推广",   "精准人群推广费",    "cubeAmt",           "amt"),
    ("推广",   "智能场景花费",      "feedCharge",        "amt"),
    ("推广",   "全站推广花费",      "adStrategyAmt",     "amt"),
    ("推广",   "淘宝客佣金",        "tkExpendAmt",       "amt"),
)


# ---------- 字段字典 ----------
#
# fields.json：机器可读字段字典（字段码 -> 中文名/适用范围/展示格式/核验状态/备注）。
# 启动时加载一次；文件缺失或损坏不崩，退回空字典并在 stderr 提醒。
FIELDS_PATH = Path(__file__).resolve().parent / "fields.json"


def load_fields_dict() -> dict[str, dict]:
    """字段字典；缺失/损坏不崩，退回空字典并提醒。"""
    try:
        return json.loads(FIELDS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️ fields.json 不可用({e}),退回内置字段表", file=sys.stderr)
        return {}


FIELDS_DICT = load_fields_dict()


def _home_table_dates(start_date: str, end_date: str) -> list[str]:
    """返回 start..end（含）的日期字符串，升序。"""
    d0 = datetime.strptime(start_date, "%Y-%m-%d").date()
    d1 = datetime.strptime(end_date, "%Y-%m-%d").date()
    if d1 < d0:
        d0, d1 = d1, d0
    out, cur = [], d0
    while cur <= d1:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def fetch_home_table(start_date: str, end_date: str, *,
                     cookies: dict[str, str] | None = None) -> dict[str, dict[str, Any]]:
    """逐日拉“数据概览”，返回 {日期: self 指标字典}（含 cycleCrc=较上一周期）。"""
    cookies = cookies or load_taobao_cookies()
    result: dict[str, dict[str, Any]] = {}
    for day in _home_table_dates(start_date, end_date):
        resp = _fetch_order_portal(
            "/portal/coreIndex/new/overview/v3.json", date_value=day,
            extra={"needCycleCrc": "true"}, cookies=cookies,
        )
        result[day] = _content_data_or_error(resp).get("self") or {}
    return result


def _fmt_home_value(value: Any, fmt: str) -> str:
    if value is None:
        return "-"
    if fmt == "pct":
        return f"{value * 100:.2f}%"
    if fmt == "amt":
        return f"{value:,.2f}"
    if fmt == "int":
        return f"{int(value):,}"
    if fmt == "num":
        return f"{value:,.2f}"
    return str(value)


def _home_cell(field_obj: Any, fmt: str, *, show_crc: bool) -> str:
    """一个格子：值 [+较上一周期%]。field_obj 形如 {value, cycleCrc}。"""
    value = field_obj.get("value") if isinstance(field_obj, dict) else field_obj
    text = _fmt_home_value(value, fmt)
    if show_crc and isinstance(field_obj, dict) and field_obj.get("cycleCrc") is not None:
        crc = field_obj["cycleCrc"] * 100
        text += f" {crc:+.1f}%"
    return text


def _field_row_for_code(code: str) -> tuple[str, str, str]:
    """(中文标签, 字段码, fmt)：verified/candidate 有字典项就用字典，没有就退回字段码本身 + fmt=num。"""
    entry = FIELDS_DICT.get(code)
    if entry:
        return entry.get("cn", code), code, entry.get("fmt", "num")
    return code, code, "num"


def _all_fields_rows() -> list[tuple[str, str, str, str]]:
    """--all-fields 用：verified 按 HOME_TABLE_ROWS 原顺序分组在前，candidate 追加到【未破译】组。"""
    rows = list(HOME_TABLE_ROWS)
    verified_codes = {code for _grp, _label, code, _fmt in HOME_TABLE_ROWS}
    for code, entry in FIELDS_DICT.items():
        if entry.get("status") == "candidate" and code not in verified_codes:
            rows.append(("未破译", entry.get("cn", code), code, entry.get("fmt", "num")))
    return rows


def cmd_home_table(args: argparse.Namespace) -> None:
    """首页/数据概览 → 多日并排表格（支付/意向/推广/售后退款，值+较上一周期，只读）。"""
    table = fetch_home_table(args.date, args.end_date)
    if args.raw:
        payload = {"data": table}
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            print(f"已写入 {args.out}")
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    fields_arg = getattr(args, "fields", None)
    grouped = True
    if fields_arg:
        codes = [c.strip() for c in fields_arg.split(",") if c.strip()]
        rows: list[tuple[str, str, str, str]] = [
            ("", *_field_row_for_code(code)) for code in codes
        ]
        grouped = False
    elif getattr(args, "all_fields", False):
        rows = _all_fields_rows()
    else:
        rows = list(HOME_TABLE_ROWS)

    days = sorted(table, reverse=True)  # 最新在左，对齐页面
    show_crc = not args.no_crc
    lines: list[str] = [
        f"# 数据概览  {min(table) if table else '?'} → {max(table) if table else '?'}"
        f"（列=日期，最新在左{'；括号=较上一周期' if show_crc else ''}）"
    ]
    label_w = max((len(lbl) for _, lbl, _, _ in rows), default=8) * 2
    cells: dict[tuple[str, str], list[str]] = {}
    for _grp, label, field, fmt in rows:
        cells[(label, field)] = [
            _home_cell(table.get(d, {}).get(field), fmt, show_crc=show_crc) for d in days
        ]
    col_w = max(
        [len(d[5:]) for d in days]
        + [len(c) for row in cells.values() for c in row]
        + [10],
    )
    header = "指标".ljust(label_w) + "".join(d[5:].rjust(col_w + 1) for d in days)
    lines.append(header)
    last_group = None
    for grp, label, field, _fmt in rows:
        if grouped and grp != last_group:
            lines.append(f"【{grp}】")
            last_group = grp
        pad = label_w - len(label) * 2
        row = label + " " * max(pad, 1)
        row += "".join(c.rjust(col_w + 1) for c in cells[(label, field)])
        lines.append(row)
    text = "\n".join(lines)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"已写入 {args.out}")
    else:
        print(text)


def cmd_api(args: argparse.Namespace) -> None:
    """通用 API 探测命令：tb sycm api <path> --param key=val ..."""
    cookies = load_taobao_cookies()
    params: dict[str, str] = {
        "_": str(int(time.time() * 1000)),
        "token": cookies.get("_tb_token_", ""),
    }
    for kv in args.param or []:
        if "=" not in kv:
            print(f"⚠️  忽略无效参数: {kv}（格式应为 key=value）", file=sys.stderr)
            continue
        k, v = kv.split("=", 1)
        params[k] = v
    data = _api_get(args.path, params, cookies, referer=args.referer)
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _flatten_menu(value: Any) -> list[dict[str, Any]]:
    found: dict[int, dict[str, Any]] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "menuId" in node and "menuName" in node:
                found[int(node["menuId"])] = {
                    "menuId": int(node["menuId"]),
                    "parentId": int(node.get("parentId") or 0),
                    "menuName": node.get("menuName") or "",
                    "menuPath": node.get("menuPath") or "",
                    "isVisible": node.get("isVisible") or "",
                    "menuOrder": node.get("menuOrder"),
                }
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return list(found.values())


def cmd_menu(args: argparse.Namespace) -> None:
    cookies = load_taobao_cookies()
    data = _api_get(
        "/oneauth/api/getMenuV2.json",
        {"_": str(int(time.time() * 1000)), "token": cookies.get("_tb_token_", "")},
        cookies,
        referer="https://sycm.taobao.com/portal/home.htm",
    )
    rows = _flatten_menu(data)
    if not args.all:
        rows = [r for r in rows if r["isVisible"] == "y"]
    rows.sort(key=lambda r: (r["parentId"], r["menuOrder"] or 0, r["menuId"]))
    if args.raw or args.out:
        payload = {"count": len(rows), "menus": rows}
        out = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(out)
            print(f"已写入 {args.out}", file=sys.stderr)
        else:
            print(out)
        return
    print(f"# 生意参谋菜单  共 {len(rows)} 项" + ("（含隐藏）" if args.all else "（可见）"))
    for row in rows:
        print(f"{row['menuId']}\t{row['parentId']}\t{row['menuName']}\t{row['menuPath']}")


def cmd_detail(args: argparse.Namespace) -> None:
    cookies = load_taobao_cookies()
    rows = fetch_chat_detail_all_pages(args.data_id, cookies)
    if args.raw:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        print("(空)")
        return
    print(f"# 会话 dataId={args.data_id}")
    print(f"# 买家 {rows[0].get('buyerNick')} ↔ 客服 {rows[0].get('accountNick')}, 共 {len(rows)} 条")
    print()
    for r in rows:
        ts = r.get("gmtCreated", "")[11:19]
        speaker = r.get("userNickFrom", "?")
        account_nick = rows[0].get("accountNick")
        is_cs = speaker == account_nick or (account_nick and account_nick in speaker)
        arrow = "→" if is_cs else "←"
        msg = r.get("msg", "").replace("\n", " ")
        print(f"[{ts}] {arrow} {speaker}: {msg}")


def cmd_fetch_recent(args: argparse.Namespace) -> None:
    """主力命令：拉某日前 N 个会话 + 完整内容，输出一份 JSON 报告。"""
    cookies = load_taobao_cookies()

    print(f"[1/3] 拉 {args.date} 的会话列表...", file=sys.stderr)
    list_resp = fetch_consultation_list(
        start_date=args.date, end_date=args.date,
        page_no=1, page_size=args.limit, cookies=cookies,
    )
    rows = list_resp.get("data", {}).get("dataSource", []) or []
    total = list_resp.get("data", {}).get("count", 0)
    print(f"      共 {total} 条，本次拉 {len(rows)} 条", file=sys.stderr)

    sessions: list[dict[str, Any]] = []
    for i, r in enumerate(rows, 1):
        # dataId 由 4 个字段拼接：dateId_sellerId_accountId_buyerId
        try:
            data_id = f"{r['dateId']}_{r['sellerId']}_{r['accountId']}_{r['buyerId']}"
        except KeyError:
            continue
        print(f"[2/3] [{i}/{len(rows)}] 拉详情 {r.get('buyerNick')} ↔ {r.get('psnNickName')}", file=sys.stderr)
        messages = fetch_chat_detail_all_pages(data_id, cookies)
        sessions.append({
            "meta": {
                "dataId": data_id,
                "buyerNick": r.get("buyerNick"),
                "psnNickName": r.get("psnNickName"),
                "accountNick": r.get("accountNick"),
                "startTime": r.get("startTime"),
                "endTime": r.get("endTime"),
                "isSellerFst": r.get("isSellerFst"),
                "isUnReply": r.get("isUnReply"),
            },
            "messages": messages,
        })

    out = {
        "fetchedAt": datetime.now().isoformat(),
        "date": args.date,
        "totalOnServer": total,
        "fetched": len(sessions),
        "sessions": sessions,
    }

    print("[3/3] 完成。", file=sys.stderr)

    if args.out:
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
        print(f"已写入 {args.out}", file=sys.stderr)
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))


# ---------- main ----------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tb sycm", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    # 顶层 --store：用保存的登录态而不是实时 Chrome。放在子命令前，如
    # tb sycm --store 示例主店 sale-shop-list
    p.add_argument("--mode", choices=["auto", "extension", "cookies"],
                   help="取数方式：extension=浏览器插件；cookies=读浏览器登录；默认 auto")
    p.add_argument("--store", metavar="店名",
                   help="用 export-profile 保存的登录态（放在子命令前），而不是实时 Chrome")
    sp = p.add_subparsers(dest="cmd", required=True)

    d = sp.add_parser("doctor", help="检查 cookie / 登录态")
    d.set_defaults(func=cmd_doctor)

    ep_ = sp.add_parser("export-profile", help="把当前 Chrome 登录态存成命名 profile（多店铺）")
    ep_.add_argument("name", help="店名 / profile 名，如 示例主店")
    ep_.set_defaults(func=cmd_export_profile)

    pf = sp.add_parser("profiles", help="列出已保存的登录态 profile")
    pf.set_defaults(func=cmd_profiles)

    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    ls = sp.add_parser("list", help="拉某日的咨询会话列表")
    ls.add_argument("--date", default=yesterday, help=f"YYYY-MM-DD (默认昨天 {yesterday})")
    ls.add_argument("--page", type=int, default=1)
    ls.add_argument("--size", type=int, default=10)
    ls.add_argument("--raw", action="store_true")
    ls.set_defaults(func=cmd_list)

    dt = sp.add_parser("detail", help="拉单个会话的完整消息")
    dt.add_argument("data_id")
    dt.add_argument("--raw", action="store_true")
    dt.set_defaults(func=cmd_detail)

    fr = sp.add_parser("fetch-recent", help="主力命令：拉某日 N 个会话 + 完整内容")
    fr.add_argument("--date", default=yesterday, help=f"YYYY-MM-DD (默认昨天 {yesterday})")
    fr.add_argument("--limit", type=int, default=5, help="拉前 N 个会话 (默认 5)")
    fr.add_argument("--out", help="输出到文件 (默认 stdout)")
    fr.set_defaults(func=cmd_fetch_recent)

    ap = sp.add_parser("api", help="通用接口探测：tb sycm api <path> --param k=v ...")
    ap.add_argument("path", help='接口路径，如 "/cc/item/isAuth.json" 或 "ww/consultation/detail/list"')
    ap.add_argument("--param", "-p", action="append", help="附加参数 key=value，可重复")
    ap.add_argument("--referer", help="自定义 Referer 头")
    ap.set_defaults(func=cmd_api)

    mn = sp.add_parser("menu", help="拉取当前生意参谋完整菜单地图")
    mn.add_argument("--all", action="store_true", help="包含隐藏菜单")
    mn.add_argument("--raw", action="store_true", help="输出结构化 JSON")
    mn.add_argument("--out", help="写入文件")
    mn.set_defaults(func=cmd_menu)

    from . import item as sycm_item
    sycm_item.register(sp, yesterday)
    from . import report as sycm_report
    sycm_report.register(sp, yesterday)

    # 命名子命令：每个高频页面一个
    for name, preset in LIST_PRESETS.items():
        sub = sp.add_parser(name, help=preset['desc'])
        sub.add_argument("--date", default=yesterday, help="YYYY-MM-DD (默认昨天)")
        sub.add_argument("--end-date", help="结束日期 (默认 = --date，做日维度查询)")
        sub.add_argument("--limit", type=int, default=10, help="拉多少条 (默认 10)")
        sub.add_argument("--page", type=int, default=1)
        sub.add_argument("--raw", action="store_true", help="输出原始 JSON")
        sub.add_argument("--out", help="输出到文件")
        sub.set_defaults(func=cmd_preset_list, preset_name=name)

    ral = sp.add_parser("refund-all-list", help="全部退款明细：按申请/完结/原订单付款时间查询（只读）")
    ral.add_argument("--date", default=yesterday, help="起始日 YYYY-MM-DD")
    ral.add_argument("--end-date", help="结束日（默认 = --date）")
    ral.add_argument("--by", choices=["case-end", "case-create", "order-pay"],
                     default="case-end", help="时间口径（默认按退款完结时间）")
    ral.add_argument("--limit", type=int, default=50)
    ral.add_argument("--page", type=int, default=1)
    ral.add_argument("--raw", action="store_true")
    ral.add_argument("--out")
    ral.set_defaults(func=cmd_refund_all_list)

    roa = sp.add_parser("refund-origin-analysis",
                        help="退款完结来源：追溯原订单付款日、退款场景和完结间隔（只读）")
    roa.add_argument("--date", default=yesterday, help="退款完结起始日 YYYY-MM-DD")
    roa.add_argument("--end-date", help="退款完结结束日（默认 = --date）")
    roa.add_argument("--raw", action="store_true")
    roa.add_argument("--out")
    roa.set_defaults(func=cmd_refund_origin_analysis)

    # Excel 导出（一行搞定：触发 → 等 → 下载）
    # 只对有 bizCode 的 sycm-v1 接口可用（cc-v2 接口没有 async-excel 端点）
    preset_choices = sorted(n for n, p in LIST_PRESETS.items() if p.get("bizCode"))
    ex = sp.add_parser("excel", help="导出 + 下载某个数据为 Excel（一条命令搞定）")
    ex.add_argument("preset_name", choices=preset_choices,
                    help=f"要导哪份数据：{', '.join(preset_choices)}")
    ex.add_argument("--date", default=yesterday, help=f"开始日期 (默认昨天 {yesterday})")
    ex.add_argument("--end-date", help="结束日期 (默认 = --date)")
    ex.add_argument("--out", help="输出文件路径 (默认 ~/Downloads/sycm-exports/<sycm-原文件名>.xlsx)")
    ex.add_argument("--wait", type=int, default=60, help="最多等几秒服务端生成 Excel (默认 60)")
    ex.set_defaults(func=cmd_excel)

    et = sp.add_parser("excel-tasks", help="列出最近的导出任务（按 preset 分组）")
    et.set_defaults(func=cmd_excel_tasks)

    # 商品大类专用：非 list 类接口
    npo = sp.add_parser("new-product-overview", help="新品总览 (商品/新品追踪 顶部汇总)")
    npo.add_argument("--date", default=yesterday, help="YYYY-MM-DD (默认昨天)")
    npo.add_argument("--end-date", help="结束日期 (默认 = --date)")
    npo.add_argument("--cate-id", type=int, default=0, help="品类 ID，0=全部 (默认 0)")
    npo.add_argument("--raw", action="store_true")
    npo.add_argument("--out", help="输出到文件")
    npo.set_defaults(func=cmd_new_product_overview)

    npt = sp.add_parser("new-product-trend", help="新品趋势 (商品/新品追踪 趋势图)")
    npt.add_argument("--date", default=yesterday, help="YYYY-MM-DD (默认昨天)")
    npt.add_argument("--end-date", help="结束日期 (默认 = --date)")
    npt.add_argument("--cate-id", type=int, default=0, help="品类 ID，0=全部 (默认 0)")
    npt.add_argument("--raw", action="store_true")
    npt.add_argument("--out", help="输出到文件")
    npt.set_defaults(func=cmd_new_product_trend)

    # 已由 HAR + 实时响应闭环验证的店铺/流量读取叶子。
    for name, help_text, func in (
        ("live-guide-overview", "直播实时引导汇总卡（只读）", cmd_live_guide_overview),
        ("live-guide-trend", "直播实时引导 today/yesterday 趋势（只读）", cmd_live_guide_trend),
    ):
        lg = sp.add_parser(name, help=help_text)
        lg.add_argument("--date", default=today, help=f"YYYY-MM-DD（默认今天 {today}）")
        lg.add_argument("--end-date", help="结束日期（默认 = --date）")
        lg.add_argument("--device", default="0", help="设备：0=全端（页面实际参数，默认 0）")
        lg.add_argument("--index-code", default="uv,itmUv,payByrCnt",
                        help="逗号分隔的指标代码（默认 uv,itmUv,payByrCnt）")
        if name == "live-guide-trend":
            lg.add_argument("--type", default="1", help="趋势类型（页面实际参数，默认 1）")
        lg.add_argument("--raw", action="store_true", help="输出原始 JSON")
        lg.add_argument("--out", help="输出到文件")
        lg.set_defaults(func=func)

    ph = sp.add_parser("preheating-metrics", help="店铺预热看板当前指标（只读）")
    ph.add_argument("--raw", action="store_true", help="输出原始 JSON")
    ph.add_argument("--out", help="输出到文件")
    ph.set_defaults(func=cmd_preheating_metrics)

    for name, help_text, func in (
        ("order-overview", "首页客单：连带率与平均购买件数汇总（只读）", cmd_order_overview),
        ("order-trend", "首页客单：截至指定日的 30 日趋势（只读）", cmd_order_trend),
        ("order-distribution", "首页客单：买家客单价分布（只读）", cmd_order_distribution),
        ("order-recommend", "首页客单：商品搭配推荐组合（只读、固定推荐集）", cmd_order_recommend),
    ):
        sub = sp.add_parser(name, help=help_text)
        sub.add_argument("--date", default=yesterday, help=f"截止日 YYYY-MM-DD（默认昨天 {yesterday}）")
        sub.add_argument("--raw", action="store_true", help="输出原始 JSON")
        sub.add_argument("--out", help="输出到文件")
        sub.set_defaults(func=func)

    for name, help_text, func in (
        ("home-overview", "首页数据概览：支付金额/访客/转化率/退款额率/加购（按日，只读）", cmd_home_overview),
        ("home-trend", "首页数据概览趋势（按日固定窗口，只读）", cmd_home_trend),
        ("grow-factor", "首页增长因子：广告引导/直播/新品/会员成交额（按日，只读）", cmd_grow_factor),
    ):
        sub = sp.add_parser(name, help=help_text)
        sub.add_argument("--date", default=yesterday, help=f"日期 YYYY-MM-DD（默认昨天 {yesterday}）")
        sub.add_argument("--raw", action="store_true", help="输出原始 JSON")
        sub.add_argument("--out", help="输出到文件")
        sub.set_defaults(func=func)

    six_days_ago = (date.today() - timedelta(days=6)).isoformat()
    ht = sp.add_parser(
        "home-table",
        help="首页数据概览多日表格：支付/意向/推广/售后退款并排 + 较上一周期（只读）",
    )
    ht.add_argument("--date", default=six_days_ago,
                    help=f"起始日 YYYY-MM-DD（默认 6 天前 {six_days_ago}）")
    ht.add_argument("--end-date", default=yesterday, dest="end_date",
                    help=f"结束日 YYYY-MM-DD（默认昨天 {yesterday}）")
    ht.add_argument("--no-crc", action="store_true", dest="no_crc",
                    help="不显示较上一周期（默认显示）")
    ht.add_argument("--raw", action="store_true", help="输出原始 JSON（每日全字段）")
    ht.add_argument("--out", help="输出到文件")
    ht_fields = ht.add_mutually_exclusive_group()
    ht_fields.add_argument("--fields",
                           help="逗号分隔字段码，只渲染这些字段（顺序照给的来，不分组），如 --fields payAmt,uv")
    ht_fields.add_argument("--all-fields", action="store_true", dest="all_fields",
                           help="渲染全部 62 个字段（verified 按默认顺序分组 + candidate 追加到【未破译】组）")
    ht.set_defaults(func=cmd_home_table)

    return p


def cmd_export_profile(args: argparse.Namespace) -> None:
    """把当前浏览器的淘宝登录态存成命名 profile，供 --store 复用。"""
    cookies = load_cookies(SYCM)   # 不受 --store 影响，始终读实时浏览器
    path = profiles.save_profile(args.name, cookies)
    print(f"✓ 已保存登录态 '{args.name}' → {path}")
    print(f"  含 {len(cookies)} 个 cookie。用法：tb sycm --store {args.name} <命令>")
    print("  该文件含长效登录凭据(权限 0600)；勿提交 git、勿外发。")


def cmd_profiles(args: argparse.Namespace) -> None:
    """列出已保存的登录态 profile。"""
    saved = profiles.list_profiles()
    if not saved:
        print(f"（暂无 profile。目录：{profiles.PROFILE_DIR}）")
        print("保存：在浏览器登录某店后跑 tb sycm export-profile <店名>")
        return
    print(f"已保存 {len(saved)} 个登录态（{profiles.PROFILE_DIR}）：")
    for p in saved:
        print(f"  - {p['store']:<16} 保存于 {p.get('saved_at') or '?'}")


def _force_utf8() -> None:
    """中文 Windows 的 cmd/SSH 常为 GBK；帮助文本里的 emoji 不应让 CLI 崩溃。统一用 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    global _ACTIVE_STORE, _CLIENT
    _force_utf8()
    args = build_parser().parse_args(argv)
    _ACTIVE_STORE = getattr(args, "store", None)
    _CLIENT = None
    if getattr(args, "mode", None):
        os.environ["SYCM_MODE"] = args.mode
    try:
        args.func(args)
        return 0
    except SystemExit as e:
        return int(e.code or 0)
    except NotLoggedIn as e:
        print(f"✗ {e}", file=sys.stderr)
        return 2
    except TbError as e:
        print(f"✗ {e}", file=sys.stderr)
        return e.exit_code
    except (RuntimeError, ValueError) as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n中断", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
