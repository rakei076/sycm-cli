# sycm-cli

> 生意参谋（sycm.taobao.com）"旺旺咨询明细"全自动抓取 CLI

给 AI 代理一行命令拉取淘宝/天猫自营店铺的客服聊天记录，用于客服分析、质检、回访话术挖掘。

## 特性

- **零浏览器交互**：不接管 Chrome、不开新 profile、不用 CDP、不用 Playwright/Selenium
- **纯本地认证**：从本地 Chrome 直读 cookie，伪 TLS 指纹直调 API
- **接口完全反向工程**：所有参数、字段、坑都摸清楚了，写在文档里
- **安全护栏内置**：随机延迟、单次上限、风控关键词检测、夜禁
- **AI 代理友好**：一条 wrapper 命令拿全数据，JSON schema 明确

参考 [twitter-cli](https://github.com/jackwener/twitter-cli) 的纯本地认证模型设计。

## 适用人群

淘宝/天猫店铺商家自己拉取**自己店铺**的客服聊天记录，做内部分析。

**不适用**：替别人抓数据、抓非自营店铺、商业爬虫服务。

## 快速开始

### 前置条件

- **macOS**（已测试）— Linux/Windows 理论可用但 cookie 解密差异未测
- **Google Chrome**（不是 Brave/Edge/Arc/Safari）已登录 sycm.taobao.com
- **uv**（推荐）或 Python 3.8+ + pip

### 装 uv（一次性）

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# 重开终端
```

### 安装本 skill

```bash
# 克隆到 Claude Code skill 目录
git clone https://github.com/rakei076/sycm-cli.git ~/.claude/skills/sycm-cli
```

### 第一次跑

**重要：先去 Chrome 打开并登录 https://sycm.taobao.com 一次**（cookie 存到本地）。

然后：

```bash
~/.claude/skills/sycm-cli/scripts/sycm.sh doctor
```

**macOS 用户首次运行会弹"钥匙串"授权弹窗** —— 这是 Chrome 的 cookie 用 macOS Keychain 加密，需要授权 Python 进程读它。点 **"始终允许"** 一次，以后就不再弹。

成功的输出：
```
== sycm-cli doctor ==
✓ 读到 N 个 taobao 域 cookie
✓ _tb_token_ = <present>
✓ ...
```

### 常见报错

| 报错 | 原因 | 处理 |
|---|---|---|
| `permission denied: scripts/sycm.sh` | 极少见（脚本执行位丢失） | `chmod +x ~/.claude/skills/sycm-cli/scripts/sycm.sh` |
| `缺 Python 依赖` | 没装 uv | 按提示装 uv 或用 pip |
| `未找到淘宝登录态` | Chrome 没登录 sycm | 去 Chrome 登录 sycm.taobao.com |
| Keychain 弹窗 deny 了 | 拒绝了 Keychain 授权 | 钥匙串访问 → 找 "Chrome Safe Storage" → 把终端加进访问控制 |
| 多个 Chrome profile | 默认读 Default，可能不是你登录的那个 | 改 `sycm_cli.py` 里 `browser_cookie3.chrome()` 传 `cookie_file=` |

### 一行命令拉数据

```bash
# 拉昨天最新 10 个会话 + 完整对话
~/.claude/skills/sycm-cli/scripts/sycm.sh fetch-recent \
  --date $(date -v-1d +%Y-%m-%d) \
  --limit 10 \
  --out ~/sycm-chats.json
```

输出 JSON 直接喂 LLM 做分析。

## 子命令

### 客服 / 服务类（旧 csp 接口）
| 子命令 | 用途 |
|---|---|
| `doctor` | 检查 cookie / 登录态 |
| `list --date YYYY-MM-DD` | 列出某日的咨询会话（不含消息正文） |
| `detail <dataId>` | 拉单个会话的全部消息（自动翻页） |
| `fetch-recent --date YYYY-MM-DD --limit N` | **主力**：列表 + 全部详情，给 AI 用 |
| `reception-list` / `evaluation-list` / `inquiry-loss-list` / `slow-rsps-list` / `sale-cs-list` | 客服与服务高频 API |
| `sale-shop-list` / `sale-item-list` | 交易与商品销售 API |
| `excel <preset>` | 一行命令导出对应数据为 Excel（自动触发→排队→下载）|

### 商品大类（v0.4+，新 cc-v2 接口）
| 子命令 | 对应 sycm 页面 |
|---|---|
| `item-list` | 商品/商品排行 + 商品 360（共用接口）|
| `cate-list` | 商品/品类 360 |
| `new-product-list` | 商品/新品追踪 → 列表 |
| `new-product-overview` | 商品/新品追踪 → 顶部汇总卡 |
| `new-product-trend` | 商品/新品追踪 → 趋势图 |

### 通用工具
| 子命令 | 用途 |
|---|---|
| `api <path> -p k=v` | 通用 API 探测器，调任何 sycm 接口 |

详细 schema、字段定义、参数风格区别（sycm-v1 vs cc-v2）见 [SKILL.md](SKILL.md)。

## 安全护栏

CLI 内置的护栏分两层：

**硬约束**（确认是风险信号才停）：
| 规则 | 行为 |
|---|---|
| 风控关键词检测 | 响应含 `滑块/验证码/操作过于频繁/请重新登录` → 立即终止，退出码 2 |
| 连续失败 | 连续 2 次 HTTP 失败 → 立即终止 |
| 夜禁时段 | 01:00 – 06:00 默认禁跑（调试设 `SYCM_BYPASS_CURFEW=1`）|

**软建议**（不停止，只 stderr 提示）：
| 规则 | 默认 |
|---|---|
| 请求间隔（随机） | 1.8 – 3.5 秒 |
| 累计请求软警告点 | 200 次（只是提示点，不是上限）|
| 可选硬上限 | 设 `SYCM_REQUEST_LIMIT=N` 启用（默认无上限，防脚本跑飞用）|

**风控按"短时高频"判定，不按"总量"**，所以日常批量拉数据完全没问题。

触发 `RiskTriggered` 时**绝对不要重试** —— 重试会让风控升级，等 24 小时再用。

## 接口情报

接口反编译自 `https://g.alicdn.com/aligenius/customer-service-performance/100.0.39/index.js`（公开 CDN）。

**列表接口**：
```
GET https://sycm.taobao.com/csp/api/ww/consultation/detail/list
  ?_=<ms> &token=<_tb_token_>
  &startDate=YYYYMMDD &endDate=YYYYMMDD
  &dateType=day &dateRange=day
  &orderBy=startTime    ← 必传，否则返回 0 条
  &pageNo=1 &pageSize=10
```

**详情接口**：
```
GET https://sycm.taobao.com/csp/api/detail/list
  ?dataId=<dateId>_<sellerId>_<accountId>_<buyerId>
  &dateType=1 &dateRange=1 &startDate=1 &endDate=1
  &pageNo=<n>
```

`dataId` 拼接规则、字段语义、错误码、其他 180+ 同套鉴权接口 — 全部在 [SKILL.md](SKILL.md)。

## AI 代理使用

把仓库克隆到 `~/.claude/skills/sycm-cli/` 后，Claude Code 等支持 Skill 的 AI 代理会自动识别 [SKILL.md](SKILL.md) 里的触发词（生意参谋 / sycm / 旺旺咨询明细 / 客服聊天记录 等），主动调用。

调用入口：

```bash
~/.claude/skills/sycm-cli/scripts/sycm.sh <subcommand> [args...]
```

## 法律与合规

- 仅供商家**自己店铺**数据合规获取使用
- 严禁用于：抓取他人店铺、商业爬虫服务、绕过平台风控
- 触发淘宝平台风控的后果由使用者承担
- 商家本人对自己经营数据的访问权利，不构成对淘宝服务条款的违反，但**频次和方式应当合理**

## License

MIT


---

## 联系作者

欢迎**有想法、有需求、想加朋友**的人来撩。

- 微信：扫下方二维码加好友
- X / Twitter：[@LuJia32473](https://x.com/LuJia32473)

<p align="center">
  <img src="assets/wechat-qr.jpg" alt="WeChat QR" width="240">
</p>

如果这个工具帮到了你，欢迎给个 ⭐️。
