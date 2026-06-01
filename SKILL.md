---
name: sycm-cli
description: 生意参谋（sycm.taobao.com）店铺数据抓取 + Excel 导出 CLI。覆盖客服聊天 / 接待 / 评价 / 销售 / 退款 / 询单流失 / 商品排行 / 商品 360 / 品类 360 / 新品追踪等核心数据，支持一行命令导出 Excel 到本地。触发场景：用户提到"生意参谋"、"sycm"、"旺旺咨询明细"、"客服聊天记录"、"接待明细"、"客服分析"、"商品销售 Excel"、"导出 Excel"、"下载店铺数据"、"评价数据下载"、"销售明细 Excel"、"邀评数据"、"商品排行"、"商品 360"、"品类 360"、"新品追踪"等。
author: rakel
version: "0.4.0"
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
uv run --with browser-cookie3 --with curl-cffi python sycm_cli.py fetch-recent --date YYYY-MM-DD --limit 10 --out chats.json
```

输出 `chats.json` 包含某日前 N 个会话的元数据 + 全部消息内容，可直接喂给 LLM 做客服分析。

## 工作机制

参考 [twitter-cli](~/.claude/skills/twitter-cli/) 的纯本地认证模型：

1. `browser_cookie3.chrome(domain_name='taobao.com')` 从本地 Chrome 的 Cookies SQLite 直读所有 taobao 域 cookie（macOS 走 Keychain 自动解密）
2. `curl_cffi` 伪 TLS 指纹（`impersonate='chrome120'`）直调 sycm API
3. **不接管浏览器、不开 profile、不需要 CDP、不用 Playwright/Selenium**

请求形态尽量贴近正常人工浏览，但仍然必须控制频率并遵守下面的安全护栏。

## 子命令

### 旺旺咨询接待（含完整对话）

| 子命令 | 用途 |
|---|---|
| `doctor` | 检查 cookie 能否读到 / 登录态是否有效 |
| `list --date YYYY-MM-DD [--page N --size N]` | 拉某日的咨询会话列表（不含消息内容） |
| `detail <dataId>` | 拉单个会话的全部消息（自动翻页） |
| `fetch-recent --date YYYY-MM-DD --limit N [--out file]` | **主力**：列表 + 全部详情，给 AI 一行命令即可拿全数据 |

### 高频日维度列表页面（v0.2+）

每个子命令都接受 `--date YYYY-MM-DD --limit N --raw --out file`：

| 子命令 | 对应 sycm 页面 | 字段 |
|---|---|---|
| `reception-list` | 服务/接待明细 | 开始/结束时间、买家、客服、是否回复 |
| `evaluation-list` | 服务/售后评价 (邀评明细) | 接待时间、邀评时间、买家、客服、来源 |
| `sale-shop-list` | 商品/销售分析 | 商品 ID/标题、店铺销售额、客服销售额、静默销售额 |
| `sale-item-list` | 交易/订单明细 | 订单时间、订单金额、买家、客服、是否静默 |
| `sale-cs-list` | 客服销售明细（旺旺销售）| 订单时间、买家、客服 |
| `inquiry-loss-list` | 服务/询单流失 | 开始/结束时间、买家、客服 |
| `slow-rsps-list` | 服务/慢响应 | 日期、开始/结束时间、买家、客服 |

示例：
```bash
sycm-cli sale-shop-list --date YYYY-MM-DD --limit 10
sycm-cli evaluation-list --date YYYY-MM-DD --limit 20 --out eval.json
sycm-cli reception-list --date YYYY-MM-DD --raw   # 输出原始 JSON
```

### 商品大类 (v0.4+) —— 商品排行 / 商品 360 / 品类 360 / 新品追踪

走的是 sycm 商品板块的**新接口（cc/* 系列，cc-v2 风格）**，与上面的旧 csp 接口参数完全不同：
- 日期参数：`dateRange="YYYY-MM-DD|YYYY-MM-DD"` + `dateType=day|recent7|recent15|recent30`
- response 里字段值常是 `{value, cycleCrc, syncCrc}` 嵌套对象（CLI 已自动提取 `.value` 展示）

| 子命令 | 对应 sycm 页面 | 关键字段 | 备注 |
|---|---|---|---|
| `item-list` | 商品/商品排行 (`/cc/item_rank`) 或 商品 360 (`/cc/item_archives`) | 商品标题、payAmt、itmUv、payRate、itemLevel | 两个页面共用同一个接口 `/cc/item/portal/itemList.json` |
| `cate-list` | 商品/品类 360 (`/cc/new_cate_archives`) | cateName、payAmt、itmUv、payRate | 返回的是当日全行业品类数据（含 children 树）|
| `new-product-list` | 商品/新品追踪 → 列表 (`/cc/new_item_analysis`) | 商品、publishNewTime、payAmtNew、shopUvNew | 接 `--cate-id` 限定类目 |
| `new-product-overview` | 商品/新品追踪 → 顶部汇总卡 | newItmCnt、shopUvNew、payAmtNew、addCartCntNew | 不是 list，返回汇总对象 |
| `new-product-trend` | 商品/新品追踪 → 趋势图 | self/industry 两组时序数据 | 建议加 `--raw` 拿全 |

示例：
```bash
# 看昨天销售前 10 商品 (商品排行)
sycm-cli item-list --date YYYY-MM-DD --limit 10

# 看品类 360（全行业品类销售）
sycm-cli cate-list --date YYYY-MM-DD --limit 5

# 新品追踪 (3 个子接口)
sycm-cli new-product-overview --date YYYY-MM-DD           # 总览
sycm-cli new-product-list --date YYYY-MM-DD --limit 10    # 列表
sycm-cli new-product-trend --date YYYY-MM-DD --raw        # 趋势
```

**字段值是嵌套对象，加 `--raw` 才能拿到对比指标**（cycleCrc=环比、syncCrc=同比）。摘要模式只显示 `.value`。

### Excel 一键下载（v0.3+）—— 商品数据 / 评价 / 销售等导出

任何上面的 list preset 都能用 `excel` 子命令**一行下载 Excel 文件**到本地（默认 `~/Downloads/sycm-exports/`）。
内部走 sycm 自带的"申请导出 → 排队生成 → 拿 OSS 临时链接 → 自动下"四步，全自动。

```bash
# 下昨天的商品销售 Excel (最高频用法)
sycm-cli excel sale-shop-list

# 下指定日期范围 + 指定输出位置
sycm-cli excel evaluation-list --date YYYY-MM-DD --end-date YYYY-MM-DD --out /tmp/eval.xlsx

# 下旺旺接待对话明细
sycm-cli excel reception-list --date YYYY-MM-DD

# 看最近的导出任务列表（含失败/排队中的）
sycm-cli excel-tasks
```

支持导出的 preset：`reception-list / evaluation-list / sale-shop-list / sale-item-list / sale-cs-list / inquiry-loss-list / slow-rsps-list`

**典型输出**：
```
[1/4] 触发 [店铺商品销售排行 (商品/销售分析)] 导出 (YYYY-MM-DD ~ YYYY-MM-DD)...
       任务 ID: 123456
[2/4] 等服务端生成 Excel（最多 60 秒）...
       完成。12 条记录。
[3/4] 取 OSS 下载链接...
[4/4] 下载到 ~/Downloads/sycm-exports/店铺绩效-专项分析-商品销售分析_YYYYMMDD_YYYYMMDD_全部.xlsx ...

✅ 完成: 12.3 KB, 12 条记录
```

OSS 临时链接 1 小时有效；过期需重新跑命令。

### 通用接口探测（高级）

```bash
sycm-cli api <path> --param key=val --param key2=val2
```

用来探索还没封装为子命令的接口。例如：
```bash
sycm-cli api ww/consultation/detail/list \
  -p startDate=YYYYMMDD -p endDate=YYYYMMDD -p dateType=day \
  -p dateRange=day -p orderBy=startTime -p pageNo=1 -p pageSize=10
```

## 安全护栏的环境变量

| 变量 | 作用 |
|---|---|
| `SYCM_BYPASS_CURFEW=1` | 强制跑（绕过 1:00–6:00 夜禁），仅自己调试用 |
| `SYCM_REQUEST_LIMIT=N` | 可选硬上限：达到 N 次请求停止（默认无；只是兜底防脚本跑飞）|

## 输出 schema

`fetch-recent` 输出 JSON：

```json
{
  "fetchedAt": "YYYY-MM-DDTHH:MM:SS",
  "date": "YYYY-MM-DD",
  "totalOnServer": 12,
  "fetched": 10,
  "sessions": [
    {
      "meta": {
        "dataId": "YYYYMMDD_<sellerId>_<accountId>_<buyerId>",
        "buyerNick": "x**",
        "psnNickName": "<店铺>:<客服名>",
        "accountNick": "<客服名>",
        "startTime": "YYYY-MM-DD HH:MM:SS",
        "endTime": "YYYY-MM-DD HH:MM:SS",
        "isSellerFst": "买家发起" | "客服主动跟进",
        "isUnReply": "已回复" | "未回复"
      },
      "messages": [
        {
          "gmtCreated": "YYYY-MM-DD HH:MM:SS.000",
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

判断发言方：优先用列表里的客服昵称匹配 `userNickFrom`；无法匹配时再按买家侧处理。

## 安全护栏

CLI 内置的护栏分两层：

**硬约束**（确认是风险信号才停，不会因日常使用误触）：
- 检测响应含 `滑块` / `验证码` / `操作过于频繁` / `请重新登录` → 立即终止，抛 `RiskTriggered` 退出码 2
- 连续 2 次 HTTP 失败 → 立即终止（连续失败大概率是登录态过期或网络挂了）
- 夜间 1:00 – 6:00 默认禁跑（行为风控敏感时段）— 调试可加 `SYCM_BYPASS_CURFEW=1`

**软建议**（不停止，只在 stderr 提示）：
- 请求间隔随机 1.8 ~ 3.5 秒（接近人工）
- 累计 200 次请求时打一次提醒（风控按"短时高频"判定，不按"总量"，所以 200 不是上限只是个提示点）
- 如需硬性兜底（防脚本跑飞），设 `SYCM_REQUEST_LIMIT=N`

**触发 `RiskTriggered` 时绝对不要重试**。重试只会让风控升级，等 24 小时再用。

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
