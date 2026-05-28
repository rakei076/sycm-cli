#!/usr/bin/env python3
"""sycm-cli — 生意参谋"旺旺咨询明细"全自动抓取 CLI

参考 twitter-cli 的纯本地认证模型：
- browser_cookie3 从 Chrome 直接读 taobao cookies（无需登录）
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


def _api_get(path: str, params: dict[str, Any], cookies: dict[str, str]) -> dict[str, Any]:
    """对 sycm API 做一次 GET，带安全护栏。"""
    global _request_count, _consecutive_fails
    if _request_count >= MAX_REQUESTS_PER_RUN:
        raise RuntimeError(f"单次运行已达 {MAX_REQUESTS_PER_RUN} 次请求上限，自动停止")

    hour = datetime.now().hour
    if 1 <= hour < 6:
        raise RuntimeError(f"夜间禁跑时段 (1:00–6:00)，当前 {hour} 点")

    url = f"{API_BASE}/{path.lstrip('/')}"
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": REFERER_DETAIL_PAGE,
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


# ---------- 命令 ----------

def cmd_doctor(args: argparse.Namespace) -> None:
    print("== sycm-cli doctor ==")
    try:
        cookies = load_taobao_cookies()
        print(f"✓ 读到 {len(cookies)} 个 taobao 域 cookie")
        print(f"✓ _tb_token_ = {cookies['_tb_token_']}")
        for k in ("cna", "t", "_m_h5_tk", "thw"):
            if k in cookies:
                v = cookies[k]
                print(f"✓ {k} = {v[:20]}{'...' if len(v) > 20 else ''}")
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
