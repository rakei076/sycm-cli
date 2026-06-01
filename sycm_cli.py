#!/usr/bin/env python3
"""sycm-cli — 生意参谋"旺旺咨询明细"全自动抓取 CLI

参考 twitter-cli 的纯本地认证模型：
- browser_cookie3 从已登录的 Chrome 直接读 taobao cookies（无需手动输入账号密码）
- curl_cffi 伪 TLS 指纹直调 sycm API
- 不开新 profile、不接管浏览器、不需要用户手动操作

接口完全反向工程自 sycm 客户端 JS（aligenius/customer-service-performance）。

子命令：
    doctor          检查 cookie 与登录态
    list            拉某日的旺旺咨询会话列表（分页）
    detail <id>     拉单个会话的全部消息
    fetch-recent    一行命令：拉某日最新 N 个会话 + 完整对话内容（推荐 AI agent 用）
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import browser_cookie3
from curl_cffi import requests

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/148.0.0.0 Safari/537.36"
)

API_BASE = "https://sycm.taobao.com/csp/api"
REFERER_DETAIL_PAGE = "https://sycm.taobao.com/qos/service/frame/performance/detail/new"

RISK_KEYWORDS = ("滑块", "验证码", "操作过于频繁", "请重新登录", "异常请求", "风控")

# 安全护栏
MIN_DELAY_SEC = 1.8
MAX_DELAY_SEC = 3.5
MAX_REQUESTS_PER_RUN = 80
MAX_CONSECUTIVE_FAILS = 2


class RiskTriggered(RuntimeError):
    pass


def _sleep_humanlike() -> None:
    time.sleep(random.uniform(MIN_DELAY_SEC, MAX_DELAY_SEC))


def load_taobao_cookies() -> dict[str, str]:
    """从 Chrome 读取 taobao 域所有 cookies。"""
    jar = browser_cookie3.chrome(domain_name="taobao.com")
    cookies: dict[str, str] = {}
    for c in jar:
        if c.domain and "taobao.com" in c.domain:
            cookies[c.name] = c.value
    if "_tb_token_" not in cookies:
        raise RuntimeError(
            "未找到淘宝登录态。请在 Chrome 里打开并登录 sycm.taobao.com 后重试。"
        )
    return cookies


def _check_risk(text: str) -> None:
    for kw in RISK_KEYWORDS:
        if kw in text and "618" not in text:
            raise RiskTriggered(f"响应含 '{kw}'，立即停止")


_request_count = 0
_consecutive_fails = 0


def _api_get(path: str, params: dict[str, Any], cookies: dict[str, str], referer: str | None = None) -> dict[str, Any]:
    """对 sycm API 做一次 GET，带安全护栏。

    path 处理规则：
    - 以 `/` 开头 → 绝对路径，拼到 https://sycm.taobao.com 后
    - 否则 → 相对路径，拼到 https://sycm.taobao.com/csp/api/ 后（旧 CSP 接口）
    """
    global _request_count, _consecutive_fails
    if _request_count >= MAX_REQUESTS_PER_RUN:
        raise RuntimeError(f"单次运行已达 {MAX_REQUESTS_PER_RUN} 次请求上限，自动停止")

    hour = datetime.now().hour
    if 1 <= hour < 6 and not os.environ.get("SYCM_BYPASS_CURFEW"):
        raise RuntimeError(
            f"夜间禁跑时段 (1:00–6:00)，当前 {hour} 点。"
            f"如需强制运行：SYCM_BYPASS_CURFEW=1 ..."
        )

    if path.startswith("/"):
        url = f"https://sycm.taobao.com{path}"
    else:
        url = f"{API_BASE}/{path}"
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": referer or REFERER_DETAIL_PAGE,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7",
    }

    try:
        resp = requests.get(
            url, params=params, cookies=cookies, headers=headers,
            impersonate="chrome120", timeout=15,
        )
        _request_count += 1
        if resp.status_code != 200:
            _consecutive_fails += 1
            if _consecutive_fails >= MAX_CONSECUTIVE_FAILS:
                raise RuntimeError(
                    f"连续 {MAX_CONSECUTIVE_FAILS} 次失败 (最后 HTTP {resp.status_code})，自动停止"
                )
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        _check_risk(resp.text)
        _consecutive_fails = 0
        return resp.json()
    except RiskTriggered:
        raise
    except Exception:
        _consecutive_fails += 1
        if _consecutive_fails >= MAX_CONSECUTIVE_FAILS:
            raise RuntimeError(f"连续 {MAX_CONSECUTIVE_FAILS} 次失败，自动停止") from None
        raise


# ---------- 高频页面预设注册表 ----------
#
# 每个 preset 对应 sycm 的一个标准"日维度列表页面"。AI 代理可以一行命令调任一个。
# 字段：
#   path       — sycm API 路径
#   orderBy    — 排序字段（找列表的关键参数，漏了大多返回 0 条）
#   referer    — 对应的 sycm 页面 URL（API 风控会查 Referer，最好真实）
#   desc       — 子命令帮助说明
#   show       — 在结果摘要里展示的字段名列表（按顺序）

LIST_PRESETS: dict[str, dict[str, Any]] = {
    "reception-list": {
        "category": "service",
        "priority": 1,
        "status": "verified",
        "path": "ww/consultation/detail/list",
        "orderBy": "startTime",
        "bizCode": "receptionDetail-wwConsultation",
        "referer": "https://sycm.taobao.com/qos/service/frame/performance/detail/new",
        "desc": "旺旺咨询接待明细 (服务/接待明细)",
        "show": ["startTime", "endTime", "buyerNick", "psnNickName", "isUnReply"],
    },
    "effective-reception-list": {
        "category": "service",
        "priority": 1,
        "status": "live-ok-empty",
        "path": "effective/Reception/detail/list",
        "orderBy": "startTime",
        "bizCode": "receptionDetail-effectiveReception",
        "referer": "https://sycm.taobao.com/qos/service/frame/performance/detail/new",
        "desc": "有效接待明细 (服务/接待明细)",
        "show": ["startTime", "endTime", "buyerNick", "psnNickName", "isUnReply"],
    },
    "filtered-reception-list": {
        "category": "service",
        "priority": 1,
        "status": "live-ok-empty",
        "path": "reception/filtering/detail/list",
        "orderBy": "startTime",
        "bizCode": "receptionDetail-receptionFilter",
        "referer": "https://sycm.taobao.com/qos/service/frame/performance/detail/new",
        "desc": "接待过滤明细 (服务/接待明细)",
        "show": ["startTime", "endTime", "buyerNick", "psnNickName", "realFilterType"],
    },
    "long-reception-list": {
        "category": "service",
        "priority": 1,
        "status": "live-ok-empty",
        "path": "long/rcpt/detail/list",
        "orderBy": "startTime",
        "bizCode": "long-rcpt-detail-cjdmx",
        "referer": "https://sycm.taobao.com/qos/service/frame/performance/detail/new",
        "desc": "长接待明细 (服务/接待明细)",
        "show": ["startTime", "endTime", "buyerNick", "psnNickName", "rcptDuration"],
    },
    "evaluation-list": {
        "category": "service",
        "priority": 1,
        "status": "verified",
        "path": "evaluation/detail/list",
        "orderBy": "servTime",
        "bizCode": "qualityDetail-receptionEvaluation",
        "referer": "https://sycm.taobao.com/qos/service/after_sale/estimate",
        "desc": "邀评/评价明细 (服务/售后评价)",
        "show": ["servTime", "sendTime", "buyerNick", "psnNickName", "source", "lstEvaScore"],
    },
    "sale-shop-list": {
        "category": "transaction",
        "priority": 2,
        "status": "verified",
        "path": "shop/sale/analysis/list",
        "orderBy": "itemId",
        "bizCode": "saleDetail-shopSale",
        "referer": "https://sycm.taobao.com/fa/frame/trade_overview",
        "desc": "店铺商品销售排行 (商品/销售分析)",
        "show": ["itemId", "itemTitle", "shopPayAmt1d", "shopPayItmCnt1d", "servPayAmt1d", "silentPayAmt1d"],
    },
    "sale-item-list": {
        "category": "transaction",
        "priority": 2,
        "status": "verified",
        "path": "item/sale/detail/list",
        "orderBy": "startTime",
        "bizCode": "saleDetail-itemSale",
        "referer": "https://sycm.taobao.com/qos/service/frame/performance/detail/new",
        "desc": "订单销售明细 (交易/订单明细)",
        "show": ["createTime", "createAmt", "buyerNick", "accountNick", "isSlientFlow"],
    },
    "sale-cs-list": {
        "category": "service",
        "priority": 1,
        "status": "verified",
        "path": "ww/sale/detail/list",
        "orderBy": "startTime",
        "bizCode": "saleDetail-wwSale",
        "referer": "https://sycm.taobao.com/qos/service/frame/performance/detail/new",
        "desc": "客服销售明细 (旺旺销售)",
        "show": ["createTime", "buyerNick", "accountNick"],
    },
    "inquiry-loss-list": {
        "category": "service",
        "priority": 1,
        "status": "verified",
        "path": "inquiry/loss/list",
        "orderBy": "startTime",
        "bizCode": "lossDetail-inquiryLoss",
        "referer": "https://sycm.taobao.com/qos/service/frame/performance/detail/new",
        "desc": "询单流失明细 (服务/咨询分析)",
        "show": ["startTime", "endTime", "buyerNick", "psnNickName"],
    },
    "slow-rsps-list": {
        "category": "service",
        "priority": 1,
        "status": "verified",
        "path": "slow/rsps/detail/list",
        "orderBy": "startTime",
        "bizCode": "slow-rsps-detail-mxymx",
        "referer": "https://sycm.taobao.com/qos/service/frame/performance/detail/new",
        "desc": "慢响应明细 (服务/慢响应)",
        "show": ["dateId", "startTime", "endTime", "buyerNick", "psnNickName"],
    },
}


def fetch_preset(preset_name: str, *, start_date: str, end_date: str,
                  page_no: int = 1, page_size: int = 10,
                  cookies: dict[str, str] | None = None) -> dict[str, Any]:
    """按预设名拉某个日期范围的列表。"""
    preset = LIST_PRESETS[preset_name]
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
        "orderBy": preset["orderBy"],
        "pageNo": str(page_no),
        "pageSize": str(page_size),
    }
    return _api_get(preset["path"], params, cookies, referer=preset["referer"])


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
        _sleep_humanlike()
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

    print(f"[3/4] 取 OSS 下载链接...", file=sys.stderr)
    url = get_excel_download_url(task_id, biz_code, cookies=cookies)

    # 默认输出路径
    if args.out:
        out_path = Path(args.out)
    else:
        Path.home().joinpath("Downloads/sycm-exports").mkdir(parents=True, exist_ok=True)
        # 用 server 文件名最后一段（去掉路径）
        suggested = server_filename.split("/")[-1] if "/" in server_filename else f"{args.preset_name}_{args.date}.xlsx"
        out_path = Path.home() / "Downloads" / "sycm-exports" / suggested

    print(f"[4/4] 下载到 {out_path} ...", file=sys.stderr)
    import urllib.request
    urllib.request.urlretrieve(url, out_path)
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
                from datetime import datetime
                ts_str = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M") if ts else "?"
                print(f"  [{t.get('id')}] {ts_str}  {status} {proc}%  {rec} 条")
        except Exception as e:
            print(f"## {name}: 查询失败 - {e}", file=sys.stderr)
        time.sleep(1)


# ---------- 命令 ----------

def cmd_presets(args: argparse.Namespace) -> None:
    rows = sorted(
        LIST_PRESETS.items(),
        key=lambda item: (item[1].get("priority", 99), item[1].get("category", ""), item[0]),
    )
    print("| preset | category | priority | status | endpoint |")
    print("|---|---|---:|---|---|")
    for name, preset in rows:
        category = preset.get("category", "?")
        priority = preset.get("priority", "?")
        status = preset.get("status", "unknown")
        print(f"| `{name}` | {category} | {priority} | {status} | `{preset['path']}` |")


def cmd_doctor(args: argparse.Namespace) -> None:
    print("== sycm-cli doctor ==")
    try:
        cookies = load_taobao_cookies()
        print(f"✓ 读到 {len(cookies)} 个 taobao 域 cookie")
        print("✓ _tb_token_ = <present>")
        for k in ("cna", "t", "_m_h5_tk", "thw"):
            if k in cookies:
                print(f"✓ {k} = <present>")
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
    """命名预设的列表查询：sycm-cli <preset-name> --date ... --limit N"""
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
    d = data.get("data", {})
    rows = d.get("dataSource", []) or []
    total = d.get("count")
    print(f"# {preset['desc']}")
    print(f"# {args.date}{' ~ ' + end if end != args.date else ''}  共 {total} 条，本页 {len(rows)}\n")
    if not rows:
        print("(空)")
        return
    show = preset["show"]
    for i, r in enumerate(rows, 1):
        vals = " | ".join(f"{k}={r.get(k, '?')}" for k in show)
        print(f"[{i:2}] {vals}")


def cmd_api(args: argparse.Namespace) -> None:
    """通用 API 探测命令：sycm-cli api <path> --param key=val ..."""
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
        is_cs = "旗舰店" in speaker or speaker == rows[0].get("accountNick")
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
        _sleep_humanlike()
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

    print(f"[3/3] 完成。", file=sys.stderr)

    if args.out:
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
        print(f"已写入 {args.out}", file=sys.stderr)
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))


# ---------- main ----------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sycm-cli", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)

    d = sp.add_parser("doctor", help="检查 cookie / 登录态")
    d.set_defaults(func=cmd_doctor)

    ps = sp.add_parser("presets", help="列出已封装和候选 API preset")
    ps.set_defaults(func=cmd_presets)

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

    ap = sp.add_parser("api", help="通用接口探测：sycm-cli api <path> --param k=v ...")
    ap.add_argument("path", help='接口路径，如 "/cc/item/isAuth.json" 或 "ww/consultation/detail/list"')
    ap.add_argument("--param", "-p", action="append", help="附加参数 key=value，可重复")
    ap.add_argument("--referer", help="自定义 Referer 头")
    ap.set_defaults(func=cmd_api)

    # 命名子命令：每个高频页面一个
    for name, preset in LIST_PRESETS.items():
        sub = sp.add_parser(name, help=preset['desc'])
        sub.add_argument("--date", default=yesterday, help=f"YYYY-MM-DD (默认昨天)")
        sub.add_argument("--end-date", help="结束日期 (默认 = --date，做日维度查询)")
        sub.add_argument("--limit", type=int, default=10, help="拉多少条 (默认 10)")
        sub.add_argument("--page", type=int, default=1)
        sub.add_argument("--raw", action="store_true", help="输出原始 JSON")
        sub.add_argument("--out", help="输出到文件")
        sub.set_defaults(func=cmd_preset_list, preset_name=name)

    # Excel 导出（一行搞定：触发 → 等 → 下载）
    preset_choices = sorted(LIST_PRESETS.keys())
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

    return p


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args)
    except RiskTriggered as e:
        print(f"\n⚠️  风险信号触发，已停止：{e}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print("\n中断", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
