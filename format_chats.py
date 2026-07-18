#!/usr/bin/env python3
"""把抓到的 sycm 聊天 JSON 转成 markdown 报告。

输入: scout-output/sycm-chats-*.json (列表结构，每项 {url, data})
输出: stdout markdown
"""
import json
import sys
from collections import defaultdict
from pathlib import Path


def parse_data_id(data_id: str) -> tuple[str, str, str]:
    """YYYYMMDD_<sellerId>_<accountId>_<buyerId> -> (date, sellerId, accountId)"""
    parts = data_id.split("_", 3)
    return parts[0], parts[1], parts[2]


def extract_data_id_from_url(url: str) -> str:
    qs = url.split("?", 1)[1] if "?" in url else ""
    for kv in qs.split("&"):
        if kv.startswith("dataId="):
            return kv[len("dataId="):]
    return ""


def main(path: str) -> None:
    raw = json.loads(Path(path).read_text())
    by_id: dict[str, list[dict]] = defaultdict(list)

    for entry in raw:
        url = entry.get("url", "")
        data_id = extract_data_id_from_url(url)
        if not data_id:
            continue
        rows = entry.get("data", {}).get("data", {}).get("dataSource", []) or []
        by_id[data_id].extend(rows)

    print(f"# 聊天明细 ({len(by_id)} 个会话)\n")

    for i, (data_id, rows) in enumerate(by_id.items(), 1):
        if not rows:
            continue
        rows.sort(key=lambda r: r.get("gmtCreated", ""))
        first = rows[0]
        buyer = first.get("buyerNick", "?")
        psn = first.get("psnNickName", "?")
        date = first.get("dateId", "")
        start_ts = rows[0].get("gmtCreated", "")[11:19]
        end_ts = rows[-1].get("gmtCreated", "")[11:19]

        print(f"## 会话 {i}: 买家 {buyer} ↔ 客服 {psn}")
        print(f"- 日期: {date}  {start_ts} – {end_ts}")
        print("- accountId: `<redacted>`  dataId: `<redacted>`")
        print(f"- 共 {len(rows)} 条消息\n")

        for r in rows:
            ts = r.get("gmtCreated", "")[11:19]
            from_nick = r.get("userNickFrom", "?")
            msg = r.get("msg", "").replace("\n", " ")
            is_cs = from_nick == psn or (psn != "?" and psn in from_nick)
            arrow = "→" if is_cs else "←"
            print(f"- `{ts}` {arrow} **{from_nick}**: {msg}")
        print()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "scout-output/sycm-chats.json")
