# sycm-cli

![License](https://img.shields.io/github/license/rakei076/sycm-cli)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Stars](https://img.shields.io/github/stars/rakei076/sycm-cli?style=social)
![Last Commit](https://img.shields.io/github/last-commit/rakei076/sycm-cli)

> 生意参谋（sycm.taobao.com）店铺数据抓取 + Excel 导出 CLI

给 AI 代理一行命令拉取淘宝/天猫自营店铺的客服聊天、评价、销售、商品等经营数据，用于客服分析、质检、回访话术挖掘、经营复盘。

---

> 💡 推荐：自己做了一个电商模特图生成站 [paitumao.com](https://paitumao.com)，
> 用的是目前最强的模特图生成模型，image-2 定价 ¥0.5/张，专门服务预算有限的小商家。
> 有需要的话加我微信聊，备注一下来意。

---

## 特性

- **跨平台本地认证**：macOS 从 Chrome 直读 cookie；Windows 使用 CLI 专用 Chrome/Edge Profile + CDP
- **不降低浏览器安全性**：不导出 cookie、不关闭 Chrome 安全保护、不接管默认 Profile
- **接口完全反向工程**：所有参数、字段、坑都摸清楚了，写在文档里
- **安全护栏内置**：随机延迟、单次上限、风控关键词检测、夜禁
- **AI 代理友好**：一条 wrapper 命令拿全数据，JSON schema 明确

参考 [twitter-cli](https://github.com/jackwener/twitter-cli) 的纯本地认证模型设计。

## 适用人群

淘宝/天猫店铺商家自己拉取**自己店铺**的客服聊天记录，做内部分析。

**不适用**：替别人抓数据、抓非自营店铺、商业爬虫服务。

## 快速开始

### 前置条件

- **macOS**：Google Chrome 已登录 sycm.taobao.com
- **Windows 10/11**：Chrome 或 Edge；首次运行会自动打开专用浏览器，登录一次后自动复用
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

macOS 请先在 Chrome 登录 https://sycm.taobao.com。Windows 可直接运行，CLI 会自动打开专用浏览器并等待首次登录。

然后：

```bash
~/.claude/skills/sycm-cli/scripts/sycm.sh doctor
```

Windows：

```bat
scripts\sycm.cmd doctor
```

Windows 启动器会优先使用 `uv`；否则使用 Python 3，并自动安装缺少的依赖。Python、依赖缓存和专用浏览器 Profile 都保存在项目内的隐藏目录，因此也能在只允许访问工作区的 Codex/AI 沙箱中运行。

> `.runtime/` 含登录后的专用浏览器 Profile。它已加入 `.gitignore`，请勿提交、打包或分享该目录。

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
| Windows 首次运行打开 Chrome/Edge | 正在创建 CLI 专用登录环境 | 登录一次，CLI 会自动检测并继续 |
| Windows 等待登录超时 | 5 分钟内没有完成登录 | 登录后重新运行；可用 `SYCM_LOGIN_TIMEOUT` 调整秒数 |
| Windows 找不到浏览器 | Chrome/Edge 未安装在常规位置 | 设置 `SYCM_BROWSER_PATH` 指向浏览器 exe |
| Windows 报 `AppData\Roaming\uv\python: 拒绝访问` | Codex/AI 仅允许访问工作区，旧启动器把 Python 放在 AppData | 更新到最新版后重新运行 `scripts\sycm.cmd doctor`；运行时会自动放到项目目录 |

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
| `refund-item-list` | 退款商品明细（按款退款金额/笔数/率/原因） |
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
| `menu [--all] [--raw]` | 读取当前账号的生意参谋菜单，作为页面/接口继续枚举的站点地图 |
| `api <path> -p k=v` | 通用 API 探测器，调任何 sycm 接口 |

网络错误和 HTTP 5xx 默认最多重试 2 次；可用 `SYCM_RETRIES=N` 调整。业务错误会返回非零退出码。

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

## 更新记录

### v0.5（2026-07）
- **首页「数据概览」多日表格 `home-table`**：一条命令拉页面「数据概览」四个 Tab 的完整 **32 项指标**（支付 10 / 意向 7 / 履约售后 10 / 推广 5），多日并排 + 每格「较上一周期」，等价于页面点「表格」那张多天对比表；字段中文名对页面逐格核对锁定。
- **首页大盘只读命令**：`home-overview` / `home-trend` / `grow-factor`（支付/访客/转化/退款率/加购 + 广告引导/直播/新品/会员成交额三档对标）。
- **多店铺登录态**：`export-profile <店名>` 保存、`--store <店名>` 切换、`profiles` 查看；一台机器管多个店，与 qianniu-cli 共用同一份 profile。
- **退款商品明细 `refund-item-list`**：按款看退款金额 / 笔数 / 率 / 原因。
- **菜单站点地图 `menu`**：读取当前账号完整菜单，便于继续定位页面/接口。
- **Windows 跨平台认证**：首次运行自动打开专用 Chrome/Edge Profile，通过本机 CDP 读登录态，不动默认 Profile、不关浏览器安全保护。
- 请求加固：网络错误 / HTTP 5xx 默认重试 2 次（`SYCM_RETRIES=N` 可调）。

### v0.4
- 商品大类（cc-v2 新接口）：商品排行 / 商品 360 / 品类 360 / 新品追踪。

### v0.3
- Excel 一键导出：`excel <preset>`，申请 → 排队 → 下载全自动。

## 法律与合规

- 仅供商家**自己店铺**数据合规获取使用
- 严禁用于：抓取他人店铺、商业爬虫服务、绕过平台风控
- 触发淘宝平台风控的后果由使用者承担
- 商家本人对自己经营数据的访问权利，不构成对淘宝服务条款的违反，但**频次和方式应当合理**

## License

MIT


---

## 联系作者

有想法、有需求，欢迎加微信找我，并注明来意。

- 微信：扫下方二维码加好友
- X / Twitter：[@LuJia32473](https://x.com/LuJia32473)

<p align="center">
  <img src="assets/wechat-qr.jpg" alt="WeChat QR" width="240">
</p>

如果这个工具帮到了你，欢迎给个 ⭐️。

---

## Star History

<a href="https://www.star-history.com/?repos=rakei076%2Fsycm-cli%2Crakei076%2Falimama-cli&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=rakei076/sycm-cli%2Crakei076/alimama-cli&type=date&theme=dark&legend=top-left&sealed_token=1C-YpKaGC2R31lIvkjjJxJ5-Nic1CJuUI18K8ttteBZoy0ktTZ7ZtH4Das9FbfclXR8d63D7McC7DbIABoPlfFEPPVjrG29Nvo56crqx6KT53wxcUbu8e8qMMgoYWjZC7fTkPi4X5H4u7liA8fp2zUmmQ-c4CABvtjksi6k69cEhKOTppTM48U7VLkac" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=rakei076/sycm-cli%2Crakei076/alimama-cli&type=date&legend=top-left&sealed_token=1C-YpKaGC2R31lIvkjjJxJ5-Nic1CJuUI18K8ttteBZoy0ktTZ7ZtH4Das9FbfclXR8d63D7McC7DbIABoPlfFEPPVjrG29Nvo56crqx6KT53wxcUbu8e8qMMgoYWjZC7fTkPi4X5H4u7liA8fp2zUmmQ-c4CABvtjksi6k69cEhKOTppTM48U7VLkac" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=rakei076/sycm-cli%2Crakei076/alimama-cli&type=date&legend=top-left&sealed_token=1C-YpKaGC2R31lIvkjjJxJ5-Nic1CJuUI18K8ttteBZoy0ktTZ7ZtH4Das9FbfclXR8d63D7McC7DbIABoPlfFEPPVjrG29Nvo56crqx6KT53wxcUbu8e8qMMgoYWjZC7fTkPi4X5H4u7liA8fp2zUmmQ-c4CABvtjksi6k69cEhKOTppTM48U7VLkac" />
 </picture>
</a>
