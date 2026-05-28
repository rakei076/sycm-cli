---
name: sycm-cli
description: 生意参谋（sycm.taobao.com）"旺旺咨询明细"全自动抓取 CLI。给 AI 代理一行命令拉取淘宝店铺的客服聊天记录，用于客服分析、质检、回访话术挖掘。触发场景：用户提到"生意参谋"、"sycm"、"旺旺咨询明细"、"客服聊天记录"、"接待明细"、"客服分析"、"拉聊天数据"。
author: rakel
version: "0.1.0"
tags:
  - taobao
  - sycm
  - customer-service
  - ecommerce
  - cli
  - scraper
---

# sycm-cli — 生意参谋旺旺咨询明细抓取 CLI

**适用人群**：淘宝/天猫店铺商家自己拉取自己店铺的客服聊天记录，用于内部客服分析。

**前置条件**：
- macOS（已测试），Linux/Windows 理论可用（browser_cookie3 跨平台）
- 本地 Chrome 已登录 sycm.taobao.com（不需要打开 sycm 页面，cookie 在本地存着即可）
- 已装 `uv`（或 `pip` + Python 3.8+）

## 一句话用法

```bash
cd ~/claudecodeworkspace/sycm-cli  # 或本 skill 目录
uv run --with browser-cookie3 --with curl-cffi python sycm_cli.py fetch-recent --date 2026-05-27 --limit 10 --out chats.json
```

输出 `chats.json` 包含某日前 N 个会话的元数据 + 全部消息内容，可直接喂给 LLM 做客服分析。

## 工作机制

参考 [twitter-cli](~/.claude/skills/twitter-cli/) 的纯本地认证模型：

1. `browser_cookie3.chrome(domain_name='taobao.com')` 从本地 Chrome 的 Cookies SQLite 直读所有 taobao 域 cookie（macOS 走 Keychain 自动解密）
2. `curl_cffi` 伪 TLS 指纹（`impersonate='chrome120'`）直调 sycm API
3. **不接管浏览器、不开 profile、不需要 CDP、不用 Playwright/Selenium**

风控视角下和正常人工浏览没有区别。

## 子命令

| 子命令 | 用途 |
|---|---|
| `doctor` | 检查 cookie 能否读到 / 登录态是否有效 |
| `list --date YYYY-MM-DD [--page N --size N]` | 拉某日的咨询会话列表（不含消息内容） |
| `detail <dataId>` | 拉单个会话的全部消息（自动翻页） |
| `fetch-recent --date YYYY-MM-DD --limit N [--out file]` | **主力**：列表 + 全部详情，给 AI 一行命令即可拿全数据 |

## 输出 schema

`fetch-recent` 输出 JSON：

```json
{
  "fetchedAt": "2026-05-28T19:05:00",
  "date": "2026-05-27",
  "totalOnServer": 149,
  "fetched": 10,
  "sessions": [
    {
      "meta": {
        "dataId": "20260527_<sellerId>_<accountId>_<buyerId>",
        "buyerNick": "x**",
        "psnNickName": "<店铺>:<客服名>",
        "accountNick": "<客服名>",
        "startTime": "2026-05-27 23:16:41",
        "endTime": "2026-05-27 23:16:59",
        "isSellerFst": "买家发起" | "客服主动跟进",
        "isUnReply": "已回复" | "未回复"
      },
      "messages": [
        {
          "gmtCreated": "2026-05-27 23:16:41.000",
          "userNickFrom": "<店铺>:<客服>" | "<买家旺旺>",
          "userNickTo": "<对方>",
          "msg": "聊天文本内容",
          "msgId": "..."
        }
      ]
    }
  ]
}
```

判断发言方：`'旗舰店' in userNickFrom` → 客服；否则 → 买家。

## 安全护栏（已写进 CLI，硬约束）

- 请求间隔随机 1.8 ~ 3.5 秒（接近人工）
- 单次运行最多 80 个请求，超过自动停止
- 连续 2 次失败立即停止
- 检测响应含 `滑块` / `验证码` / `操作过于频繁` / `请重新登录` 立即终止
- 夜间 1:00 – 6:00 禁跑（行为风控敏感时段）

**如果触发风控**，CLI 直接抛 `RiskTriggered` 异常退出码 2，**永远不重试**。重试只会让风控升级。

## 反编译笔记（接口情报）

接口来源：`https://g.alicdn.com/aligenius/customer-service-performance/100.0.39/index.js` 反编译（公开 CDN，无需登录）。

**列表接口**：
```
GET https://sycm.taobao.com/csp/api/ww/consultation/detail/list
  ?_=<timestamp_ms>
  &token=<_tb_token_ cookie 值>
  &startDate=YYYYMMDD   (注意是 YYYYMMDD 不是 YYYY-MM-DD)
  &endDate=YYYYMMDD
  &dateType=day
  &dateRange=day
  &orderBy=startTime    ← 必需，漏掉返回 0 条（这是个坑）
  &pageNo=1
  &pageSize=10
```

**详情接口**：
```
GET https://sycm.taobao.com/csp/api/detail/list
  ?dataId=<dateId>_<sellerId>_<accountId>_<buyerId>
  &dateType=1&dateRange=1&startDate=1&endDate=1
  &pageNo=<n>
```

每页约 10 条消息，>10 条需翻页，直到 `data.dataSource:[]`。

**dataId 拼接规则**：列表 row 不直接给 `dataId` 字段，必须从 4 个字段拼接：

```python
data_id = f"{row['dateId']}_{row['sellerId']}_{row['accountId']}_{row['buyerId']}"
```

**鉴权**：纯 cookie + URL 参数 `token=<_tb_token_>` + `_=<毫秒时间戳>`。**无动态 sign，无加密**。

## 可扩展接口（同套鉴权机制）

反编译同时挖出 **183 个 sycm 服务模块接口**，全部用同样的 cookie + token 鉴权，按需扩展子命令：

- `ww/sale/detail/list` — 旺旺销售明细
- `effective/Reception/detail/list` — 有效接待明细
- `reception/filtering/detail/list` — 接待过滤明细
- `slow/rsps/detail/list` — 慢响应明细
- `long/rcpt/detail/list` — 长接待明细
- `evaluation/detail/list` — 评价明细
- `inquiry/loss/list` — 询单流失
- `serv/sale/analysis/list` — 服务销售分析
- `user/duty/analyse/list` — 客服值班分析
- `core/monitor/list` — 实时监控
- `shop/refund/core/summary` — 店铺退款核心数据
- `refund/complaint/detail/list` — 退款投诉明细
- 等等...

## AI 代理调用示例

用户："帮我看下昨天客服都聊了什么"：

```bash
DATE=$(date -v-1d +%Y-%m-%d)
uv run --with browser-cookie3 --with curl-cffi python ~/.claude/skills/sycm-cli/sycm_cli.py \
  fetch-recent --date $DATE --limit 10 --out /tmp/sycm-$DATE.json

# 然后读 /tmp/sycm-$DATE.json，逐个会话做分析
```

用户："分析下今天客服的尺码推荐是否准确"：

1. 拉今天的 fetch-recent
2. 过滤 messages 里包含"穿什么码 / 身高 / 体重 / XL / L 码"等关键词的会话
3. 分析每个会话客服推荐的尺码合理性，输出报告

## 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `doctor` 报"未找到淘宝登录态" | Chrome 没登录 sycm 或被另一个 Chrome 锁定 cookie 文件 | 打开 Chrome 登录 sycm.taobao.com 一次 |
| `list` 返回 0 条 | 漏传 `orderBy=startTime` 参数 | CLI 已内置，正常情况不会遇到 |
| `RiskTriggered: 滑块` | sycm 触发风控 | 立即停 24 小时，不要重试 |
| HTTP 5810 | session 超时 | 重新打开 Chrome 登录 sycm |

## 文件清单

- `sycm_cli.py` — 主 CLI
- `format_chats.py` — JSON → Markdown 报告格式化（可选）
- `requirements.txt` — Python 依赖（browser-cookie3, curl-cffi）

## 局限性

- 只覆盖了"旺旺咨询明细"（接待明细页）。其他 180+ 接口待按需扩展
- 详情接口每页最多 10 条消息，CLI 自动翻页处理
- 列表 `pageSize` 实测最大约 20，过大会被服务端截断
- Cookie 写在 Chrome Default profile，若你 Chrome 有多个 profile，可能要改 `browser_cookie3.chrome(cookie_file=...)` 指定
