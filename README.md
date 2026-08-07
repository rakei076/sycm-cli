# sycm-cli

![License](https://img.shields.io/github/license/rakei076/sycm-cli)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Stars](https://img.shields.io/github/stars/rakei076/sycm-cli?style=social)
![Last Commit](https://img.shields.io/github/last-commit/rakei076/sycm-cli)

> 生意参谋（sycm.taobao.com）店铺数据 CLI + AI 经营分析 Skill

给 AI 代理一行命令拉取淘宝/天猫自营店铺的大盘、客服、评价、销售、商品、新品和退款数据，并按可复用的方法生成报表和经营分析。

**v0.9 起商品板块全覆盖**：单品 360 的 14 个模块（详情逐屏 / 价格定位 / 标题死词 / 客群 10 维度
/ 退款归因 / 潜在流失…）+ 宏观监控、商品排行、品类 360、商品集、新品追踪、连带分析、视频分析、
问题预警 —— 共 **9 个页面 / 22 个模块 / 52 个命令**，其中 **14 个命令的数字已与页面逐格核对一致**。

字段中文名与展示格式统一取自 [`fields.json`](fields.json)（**182 条**，`verified` 的都注明了
验证日期与方法）；字典没收录的字段**原样打字段码，不猜中文名**。

---

> 💡 推荐：自己做了一个电商模特图生成站 [paitumao.com](https://paitumao.com)，
> 用的是目前最强的模特图生成模型，image-2 定价 ¥0.5/张，专门服务预算有限的小商家。
> 有需要的话加我微信聊，备注一下来意。

---

## 特性

- **跨平台本地认证**：macOS 从 Chrome 直读 cookie；Windows 使用 CLI 专用 Chrome/Edge Profile + CDP
- **不降低浏览器安全性**：不导出 cookie、不关闭 Chrome 安全保护、不接管默认 Profile
- **接口以真实页面请求验证**：稳定命令直接开放，未确认的日期窗口和字段口径明确标注
- **安全护栏内置**：随机延迟、可选请求硬上限、风控关键词检测、夜禁
- **AI 代理友好**：一条 wrapper 命令拿全数据，JSON schema 明确

## AI 店铺分析 Skill

仓库内的 [SKILL.md](SKILL.md) 是给 AI 代理执行的机器说明，不是 README 的复制。它目前定义了七个可单独触发的模块：

| 模块 | 它回答什么 | 关键边界 |
|---|---|---|
| 标准全景报表 | 当前到底能拿到哪些数据 | 每张表都列出，不用“等”省略 |
| 日体检 | 昨天是否有需要立即处理的异常 | 用完整日，只和自己过去比 |
| 周复盘 | 本周是流量、转化还是客单价在变 | 周 UV 不用日 UV 直接相加伪造 |
| 测款专项 | 哪些新品值得继续验证 | 没有毛利/退货队列时不直接放量 |
| 退货归因 | 哪些款是退款事件热点、原因是什么 | 禁止用历史订单退款除以当日成交 |
| 广告 ROI | 万相台的场景/计划/商品效率 | 需 `alimama-cli`，只读，不自动停投 |
| 客服质检 | 客服是否真正回答了买家问题 | 对话脱敏，不因空评分或情绪给人员贴标签 |

所有模块都要附上数据日期、命令和字段口径，并将建议收敛到 0–2 个动作。完整分析规则在 [references/analysis-workflows.md](references/analysis-workflows.md)。

参考 [twitter-cli](https://github.com/jackwener/twitter-cli) 的纯本地认证模型设计。

## 适用人群

淘宝/天猫店铺商家自己拉取**自己店铺**的客服聊天记录，做内部分析。

**不适用**：替别人抓数据、抓非自营店铺、商业爬虫服务。

## 快速开始

### 前置条件

- **macOS**：Google Chrome 已登录 sycm.taobao.com
- **Windows 10/11**：Chrome 或 Edge；首次运行会自动打开专用浏览器，登录一次后自动复用
- **uv**（推荐）或 Python 3.10+ + pip

### 装 uv（一次性）

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# 重开终端
```

### 安装本 skill

```bash
# Claude Code
git clone https://github.com/rakei076/sycm-cli.git ~/.claude/skills/sycm-cli

# Codex
git clone https://github.com/rakei076/sycm-cli.git ~/.codex/skills/sycm-cli
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
| `refund-all-list` | 全部退款逐笔明细；可按申请、完结或原订单付款时间筛选 |
| `refund-origin-analysis` | 将某日完结退款追溯到原付款日，并拆分退款场景和时间间隔 |
| `excel <preset>` | 一行命令导出对应数据为 Excel（自动触发→排队→下载）|

### 商品大类（v0.4+，新 cc-v2 接口）
| 子命令 | 对应 sycm 页面 |
|---|---|
| `item-list` | 商品/商品排行 + 商品 360（共用 `/cc/item/view/top.json`，12 项默认指标，`--raw` 看全部 41 个）|
| `cate-list` | 商品/品类 360 |
| `new-product-list` | 商品/新品追踪 → 列表 |
| `new-product-overview` | 商品/新品追踪 → 顶部汇总卡 |
| `new-product-trend` | 商品/新品追踪 → 趋势图 |

### 单品 360 全模块（v0.9+，只读）
覆盖单品 360 页面的全部 14 个模块。先 `item-search` 拿 `itemId`，其余都接 `--item-id`
（或 `--search <货号/标题>`，命中唯一才继续）。

| 子命令 | 用途 |
|---|---|
| `item-search <关键词>` | 按标题/商品ID/商品URL/货号搜商品，拿 itemId |
| `item-360 --item-id <ID>` | 单品核心指标（本店值 + 环比 + 未核实的 cmpt 对比值）+ 销售总览，都吃 `--date` |
| `item-sku-list --item-id <ID>` | 各 SKU 组合的加购/支付明细，吃 `--date`；`--by <属性名>` 改出按属性聚合表（尺码/颜色分类等）；`--live` 改出现有库存/售罄率/库存可售天数（当前快照，忽略 `--date`，与 `--by` 互斥） |
| `item-flow-source --item-id <ID>` | 流量来源树：访客从哪来、哪个渠道转化差 |
| `item-refund --item-id <ID>` | 一条命令三张表：退款原因 + 各 SKU 退款 + 各属性退款 |
| `item-profile --item-id <ID>` | 客群洞察/客群画像：买这个款的人是谁（10 个维度，`--all` 一次跑完）。**只认单日** |
| `item-loss-risk --item-id <ID>` | 客群洞察/客群细分：客户预测流向哪些商品（含友商），带按店铺汇总。人气值**只有单日有**；这份数据要有足够客户流向样本才出，冷门款/新款返回 0 条属正常 |
| `item-detail --item-id <ID>` | 详情分析：核心概况（**带同行均值/优秀**）+ 详情页逐屏 11 个楼层，看买家看到哪屏走的 |
| `item-price --item-id <ID>` | 价格分析：本款价格定位 + 类目各价格带大盘（标出本款所在档） |
| `item-title --item-id <ID>` | 标题优化：每个词带来多少搜索访客（点名零引导死词）+ 推荐词 |
| `item-bundle --item-id <ID>` | 关联搭配：系统推荐 + 卖家自选 |
| `item-content --item-id <ID>` | 内容分析：哪条视频真的带货。**不传日期 = 近 30 天**（页面默认口径），显式传 `--date` 则照给的窗口来（单日也认） |
| `item-service --item-id <ID>` | 服务体验：售前咨询/售后解决率/有效回复/问大家声量，带对比值 |

```bash
scripts/sycm.sh item-search 连衣裙 --limit 3
scripts/sycm.sh item-sku-list    --item-id 123456789 --date 起始 --end-date 结束 --limit 10
scripts/sycm.sh item-sku-list    --item-id 123456789 --date 起始 --end-date 结束 --by 尺码
scripts/sycm.sh item-sku-list    --item-id 123456789 --live --limit 10
scripts/sycm.sh item-flow-source --item-id 123456789 --date YYYY-MM-DD
scripts/sycm.sh item-refund      --item-id 123456789 --date 起始 --end-date 结束
scripts/sycm.sh item-profile     --item-id 123456789 --date YYYY-MM-DD --all --limit 5
scripts/sycm.sh item-loss-risk   --item-id 123456789 --date YYYY-MM-DD --limit 20
scripts/sycm.sh item-detail      --item-id 123456789 --date YYYY-MM-DD --limit 20
scripts/sycm.sh item-price       --item-id 123456789 --date YYYY-MM-DD
scripts/sycm.sh item-title       --item-id 123456789 --date YYYY-MM-DD
scripts/sycm.sh item-bundle      --item-id 123456789 --date YYYY-MM-DD
scripts/sycm.sh item-content     --item-id 123456789 --date 起始 --end-date 结束
scripts/sycm.sh item-service     --item-id 123456789 --date 起始 --end-date 结束
```

口径警告（详见 [SKILL.md](SKILL.md)）：
- 日期窗口只支持 **1 / 7 / 15 / 30 天**，其余宽度服务端 `code=1003` 拒绝，CLI 会先在本地报错。
- 生意参谋商品板块反复出现「日/7天/30天档」与「实时档」是两个不同接口的坑：`item-sku-list`、
  `item-360` 的销售总览走认日期的那套（2026-08-05 已从误录的 `/cc/live/` 实时接口改正，recent7 与
  recent30 两次真实调用验证过数值不同）；`item-list` 同理，已从不认 `indexCode` 的
  `/cc/item/portal/itemList.json` 换成 `/cc/item/view/top.json`。**`item-sku-list` 的实时档没丢，
  用 `--live` 显式切换**（现有库存/售罄率/库存可售天数只有这个实时接口才有，与 `--by` 互斥）。
- `item-refund` 是**退款事件归属，不是退货率**；表里的 `payAmtRfdRate` / `ordRfdRate` 近 7 天仍在爬升，别用近 7 天下结论。
  「退款原因」表 2026-08-06 已修好（真凶是 `rfdIntervalLevel` 猜成了 `ALL`，正确值 `99`），现在带「内部原因/消费者原因」分类。
- `item-360` 的 `*Cmpt` 口径未核实，不是同行绝对值。
- `item-profile` **只认单日**（多日区间服务端回 `code=0` 但数据恒空，CLI 发请求前就拦）。三个人群
  口径通常只有 `itmUv`（访问人群）有数据——平台规则是「人群样本量小于 300 人不统计客群画像」，
  而单日口径攒不够人数，所以 `payByrCnt` / `appSearchUv` 只有大流量爆款才出得来。`brand_prefer`
  有品牌名但数值全 0（页面同样为空，非 CLI 问题）。

### 页面级模块（阶段3，不带 `--item-id`）
| 子命令 | 用途 |
|---|---|
| `spu-list` | 商品集分析（**只认单日**，多日区间服务端只回一句 `param check error`，CLI 本地先拦） |
| `item-relate` | 连带分析：主商品 + 关联商品。**不认单日**（服务端只回 `code=1002 "4004:"`，一个字不提日期），默认给近 7 天 |
| `video-list` | 视频分析：曝光/点击/播放/完播/成交 |
| `macro-monitor` | 宏观监控：全店商品实时大盘（**实时快照，`--date` 不生效**） |
| `problem-alarm` | 问题预警：质量问题/缺货/高价限流商品计数 + 缺货明细（实时） |
| `interval-analysis` | 商品区间分析：动销商品按价格带/件数/金额切开各占多少。**价格带视角只认单日**（多日服务端回 `code=1002 "4000:"`，CLI 本地先拦）。区间边界是**店铺在页面上自己配的**，配得不对会出现多行区间名与数值完全相同 —— 命令会检测并指路页面上那个「编辑」按钮 |

### 首页大盘（v0.5+）
| 子命令 | 对应 sycm 页面 |
|---|---|
| `home-overview --date YYYY-MM-DD` | 首页/数据概览（当日支付/访客/转化/退款率/加购）|
| `home-table --date 起 --end-date 止` | 首页/数据概览「表格」：4 个 Tab 完整 **32 项**多日并排 + 每格较上一周期 |
| `home-trend` | 首页/数据概览趋势 |
| `grow-factor` | 首页/增长因子（广告引导/直播/新品/会员成交额）|

### 多店铺登录态（v0.5+）
| 子命令 | 用途 |
|---|---|
| `export-profile <店名>` | 把当前 Chrome 登录态保存成命名 profile |
| `--store <店名>`（放在子命令前）| 用指定店铺的登录态执行任意命令 |
| `profiles` | 查看已保存的店铺 + 登录态新鲜度 |

### 通用工具
| 子命令 | 用途 |
|---|---|
| `menu [--all] [--raw]` | 读取当前账号的生意参谋菜单，作为页面/接口继续枚举的站点地图 |
| `api <path> -p k=v` | 通用 API 探测器，调任何 sycm 接口 |

网络错误和 HTTP 5xx 默认最多重试 2 次；可用 `SYCM_RETRIES=N` 调整。业务错误会返回非零退出码。

详细 schema、字段定义、参数风格区别（sycm-v1 vs cc-v2）见 [SKILL.md](SKILL.md)。

### 逐笔退款溯源

```bash
# 某日完成的全部退款：逐笔保留订单付款、退款申请和退款完结时间
scripts/sycm.sh refund-all-list --date 2026-07-17 --by case-end --out /tmp/refunds.json

# 汇总这些退款来自哪些付款日、属于哪种退款场景、间隔多久
scripts/sycm.sh refund-origin-analysis --date 2026-07-17
```

`refund-all-list` 的时间口径还可选 `case-create`（退款申请日）和 `order-pay`（原订单付款日）。逐笔记录可回答“这笔退款原来什么时候付款”，但不能单独算真实退货率。真实退货率必须以同一付款批次的支付订单/件数为分母，并只保留最终发生 `退货退款` 的订单/件。

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

### 本地数据与隐私

- Cookie 和命名店铺 Profile 只保存在本机；`.runtime/`、`.taobao-cli/profiles/`、`.env*`、运行 JSON、缓存和私钥都不得提交。
- `--raw` 和 `--out` 可能包含买家昵称、客服昵称、订单 ID、商品 ID 与聊天正文。分享给第三方或 AI 前先脱敏。
- AI 分析默认只展示匿名商品代号和聚合结果；只有用户明确允许时才读取必要的聊天正文。
- Excel 下载地址只接受无内嵌账号密码的 HTTPS URL；浏览器 CDP 读取只允许连接本机地址。

## 开发与验证

```bash
# 单元测试（隔离安装测试与运行依赖）
uv run --with pytest --with browser-cookie3 --with curl-cffi \
  --with websocket-client python -m pytest -q

# Skill 结构校验（在安装了 Codex skill-creator 的机器上）
python ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py .

# 登录态和最小只读探针
scripts/sycm.sh doctor

# 商品域冒烟：19 个命令挨个打默认参数，判「能否跑通 + 有没有数据行」
scripts/smoke-item.sh <商品ID>

# 隐私扫描：敏感词 + 12 位以上真实 ID + 运行时数据文件是否进 git
scripts/privacy-scan.sh
```

**单元测试防不住「一开始就理解错」。** 测试的 fixture 是人手敲的正确参数，命令自己的
默认值坏掉照样全绿——v0.9 就是这么抓出两个「默认调用必挂」的 bug 的。所以：

- 冒烟脚本一律**不带参数**跑每个命令，专抓默认路径
- 输出分 `OK / EMPTY / FAIL` 三档，**`EMPTY`（跑通但零数据行）是最值钱的信号**：
  页面上那块要是有数，就说明参数猜错了——服务端收下不报错、然后回你一张空表
- 完整验收流程见 [docs/plans/2026-08-07-验收测试方案.md](docs/plans/2026-08-07-验收测试方案.md)
  （L0 环境 → L1 冒烟 → L2 逐格对账 → L3 复核已知软肋 → L4 实战有用性）

发布前还应执行静态检查、依赖漏洞扫描和 Git 历史密钥扫描；真实店铺输出始终写入仓库外的临时目录。

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

**取数主力走字段字典。** 仓库根目录 [`fields.json`](fields.json) 是机器可读字段字典（字段码 → 中文名 / 适用命令 / 口径备注），AI 先查字典再用 `--fields` 选列取数，遇到字典没有的字段有一套「三招」发现方法论自己去查。这部分是给机器看的操作规范，写在 [SKILL.md](SKILL.md) 的「字段字典与发现方法论」一节，README 不重复。

```bash
# 只要指定几列，而不是整页 32 项
~/.claude/skills/sycm-cli/scripts/sycm.sh home-table --fields payAmt,uv,payRate --date 2026-07-13 --end-date 2026-07-19
```

## 更新记录
### v0.9（2026-08-07）—— 商品板块全覆盖

商品板块从 5 个命令做到 **19 个命令 / 9 个页面 / 22 个模块**，字典 89 → 182 条，
192 个单元测试。

#### 新增命令（14 个）

- **单品 360 补齐剩余模块**：`item-detail`（详情逐屏 11 个楼层 + 同行均值/优秀）、
  `item-price`（本款价格定位 + 类目价格带大盘）、`item-title`（逐词搜索引导，点名零引导
  死词 + 推荐词）、`item-content`（内容/视频带货）、`item-service`（服务体验 9 项，每项带
  同类平均）、`item-bundle`（关联搭配）、`item-profile`（客群画像 **10 个维度**，`--all`
  一次跑完）、`item-loss-risk`（潜在流失风险，带按店铺汇总）
- **页面级**：`spu-list`、`item-relate`、`video-list`、`macro-monitor`、
  `interval-analysis`、`problem-alarm`

#### 修好的老 bug

- **`item-refund` 的退款原因表空了两天** —— v0.8.2 里记成「未确定」。真凶是
  `rfdIntervalLevel` 被猜成了 `ALL`，页面实际发 `99`。同样的参数，`ALL` → 0 行、
  `99` → 8 行。**服务端收下不报错，只是回你一张空表。** 顺带补上页面上有、我没渲染的
  「流失至竞店人数」`lossByrCnt` —— 这一列直接告诉你多少人退完就去买了别家。
- **`item-refund` 的 SKU 表被服务端截断，还谎报总数**：
  `/cc/refund/item/sku/list.json` **无视 pageSize，每页封顶 5 行**
  （`pageSize=100` → 5 行；`pageSize=5` 翻三页 → 12 行）。原来只发一次请求、把
  「本页行数」当「总行数」打印。**被砍掉的 7 行里有一个 SKU 退款率 100%。**
  已改为按 `recordCount` 翻页，表头改报服务端总数。
- **`item-content` / `item-relate` 的默认参数直接报错**：前者 `dateType` 硬写
  `recent30` 却配单日 `dateRange`（`code=1003`）；后者单日必挂
  （`code=1002 "4000:"`）而默认就是昨天单日。**两个都是「不带参数跑就挂」。**
- **`item-loss-risk` 把「没数据」误报成「日期传错了」** —— `any()` 在 0 行时也是
  False，于是走到「多日区间会丢指标，请用单日」那句上，可用户传的就是单日。
- **日期渲染吃本机时区**：`statDate` 是北京时间零点的毫秒时间戳，用本机时区换算会在
  UTC+8 以西的机器上**整体倒退一天**（伦敦 → 前一天 17:00）。已固定按 +08:00 换算。
- `item-360` 的比率不再打裸小数（`0.006628…` → `0.66%`）；`item-content` 的
  `children` 信封不再被渲染成一整行横杠；`interval-analysis` 去掉一列自造的无意义
  「件单价占比」（那是拿两档单价相加当分母）。
- 9 个中文字段名按页面原话改正：有效回复人数→**有效接待人数**、问大家声量→**问大家
  原声量**、搭配支付件数→**预测连带支付件数**、对比值→**同类商品平均** 等。

#### 展示层统一

改造前一半命令的表头是 `attrValue` / `payAmtRatio` / `itemSkuRfdAmt` 这种字段码，
比率是 `0.003964321110009911` 这种裸小数，日期是 `1785945600000` 毫秒时间戳。

中文名和展示格式 `fields.json` 里本来就有（`cn` + `fmt` 两列），**渲染层查字典即可**：

```
改造前  _path / uv / pv / cartByrCnt / 0.0017301038062283738
改造后  来源路径 / 访客数 / 浏览量 / 加购人数 / 0.17%
```

字典没收录的字段**原样打字段码，不猜中文名**。

#### 查清但决定不做的

- `/domain/oneQuery.json` 通用网关：**结论=证伪**，指标词汇不可外推，不能替代逐个封装
- `item-list` 的 `indexCode` 形同虚设 —— 传多传少都回同一组固定 41 字段，
  原计划「8→30 指标分批取并合并」的前提不成立
- **AI 价格区间分析**：接口只回元数据，真报告要在页面点「诊断分析」现场生成 = 写操作，
  超出只读边界
- 商品链路 21 条隐藏路由侦查完，**只有 `problem_alarm` 有独立数据**，
  其余是下钻页 / 外链 / 已下线 / 本店无数据

#### 新增验收工具

- **`scripts/smoke-item.sh <商品ID>`**：19 个命令挨个**打默认参数**跑一遍，分
  `OK / EMPTY / FAIL` 三档。`EMPTY`（跑通但零数据行）是最值钱的信号 ——
  页面上那块要是有数，就说明参数猜错了。
- `scripts/privacy-scan.sh` 加强：除敏感词外，新增「12 位以上真实商品 ID/userId」
  和「运行时数据文件进 git」两条检查
- [docs/plans/2026-08-07-验收测试方案.md](docs/plans/2026-08-07-验收测试方案.md)：
  五层验收流程（L0 环境 → L1 冒烟 → L2 逐格对账 → L3 复核已知软肋 → L4 实战有用性）

#### 三条方法论（都是踩出来的）

1. **「核验过」必须包含「不带任何参数跑一遍默认调用」。** `item-content` 和
   `item-relate` 两个 bug 同一个成因：核验时手敲了正确的日期区间，绕开了坏掉的默认值。
   测试也挡不住 —— 测试的 fixture 同样是手敲的正确参数。**名字里有 `default` 的测试，
   不代表它真的走了默认路径。**
2. **数字对不上时，第一嫌疑是比对方式，不是接口。** `item-content` 的「商品点击次数」
   被记了两天「与页面对不上」，还被降级成 `candidate`。真相是页面那一块有
   **TOP直播 / TOP短视频 / TOP图文** 三个标签，命令走的 video 接口只对应短视频那一个 ——
   当初拿了另一个标签的数字在比。逐格重比：**7 行 × 5 列 35 个格子全中。**
3. **用 `innerText` 读页面比对时，相邻列会被拼成一个数。** `item-relate` 差点被误判成
   「差 7 倍」——页面文字里的 `23.39%` 其实是「关联支付人数 2」+「关联购买率 3.39%」
   粘在一起。判据：CLI 的两个相邻数字拼起来是否正好等于页面那一串。

#### 核验状态

18 个商品域命令逐个与页面比对：**14 个数字逐格核对一致**，3 个部分核对，1 个无指标可核。
详见 [全量清单第八节](docs/plans/2026-08-05-商品板块-全量清单.md)。

#### 仍未解决 / 已知边界（明写在这里，别当没有）

| 项 | 说明 |
|---|---|
| `item-price` / `item-title` 的数值 | 页面主体是图表和鼠标悬停提示，**数值不落在文本里**，逐格核对做不了。分档、分词、推荐词本身核过 |
| `item-content` 的覆盖范围 | 只含页面的「**TOP短视频**」标签，**TOP直播 / TOP图文 两个标签没做** |
| `interval-analysis` 的分档 | 区间边界是**店铺在页面上自己配的**（每栏右上角有「编辑」）。配得不对时会出现多行区间名和数值完全相同 —— 命令会检测并指路那个按钮，但改配置得你自己去页面点 |
| `item-refund` 三张子表人数合不上 | **不是 bug**：`rfdIdentifyType=alg_identify` 会给一笔退款打多个原因标签（实测原因表退款单数 168、属性表 122，两表分母 `payOrdCnt` 都是 211）。**各行不可相加**，要唯一人数看属性表。命令已在输出里写明 |
| `item-refund` 的子原因 | 每行退款原因还带 `children`（描述不符 / 材质问题 / 做工问题等），命令暂不展开，需要时用 `--raw` |
| `item-360` 的字段名 | 打的是**英文字段码不是中文名** —— 这些码的中文名没跟页面核过，**不猜** |
| `item-360` 的 `*Cmpt` | 口径未核实，**不是同行绝对值**，别当同行对比解读 |

### v0.8.2（2026-08-05）
- **`item-list` 换接口**：之前的 `/cc/item/portal/itemList.json` 不认 `indexCode`
  （实测传多少个都只回 `itmUv`/`payAmt`/`payRate` 3 个指标），换成商品排行页
  「日/7天/30天」档实际调用的 `/cc/item/view/top.json` 后，单次调用能拿到 41
  个字段；默认展示 12 项（支付/访客/加购/收藏/停留/跳出/搜索引导/退款），其余
  用 `--raw` 看。旧接口在全仓库范围内确认无其它调用点，已删除，不留兼容层。
- **`item-sku-list` 新增 `--live`**：找回之前被换掉的实时库存快照接口
  （`/cc/live/v2/item/sale/sku/list.json`），拿现有库存 `currentStockCnt`、
  售罄率 `sellRate`、库存可售天数 `stockDays`——这三个字段只有实时接口有，
  日期口径接口拿不到。`--live` 会忽略 `--date`/`--end-date` 并在输出里明确
  提示，且与 `--by` 互斥（属性聚合接口没有实时版本）。
- **`item-refund` 的退款原因空表加说明**：`rfdReasonName` 那张表长期返回 0
  行，同一次请求里 SKU/属性两张兄弟表都有真实数据。排查过 `rfdIdentifyType`
  / `caseScene` / `refundDateType` / 日期窗口等多种组合，均为合法的
  `code=0` 空结果，没能定位具体原因，结论按「未确定」处理——命令现在会在
  空表下面打印这句说明，不再是一张没有任何解释的空表。
- **纠正 v0.8 的接口误判**：`item-sku-list`、`item-360` 的销售总览之前录到的
  `/cc/live/...` 系接口确实忽略 `--date`，但那是因为侦查时网页时间选择器停在
  「实时」档；生意参谋销售分析页其实有两套接口，切到「日/7天/30天」档走的是
  另一套不带 `live/` 的接口，正常按日期返回。已换成认日期的
  `/cc/item/sale/sku/list.json`、`/cc/item/sale/overview.json`，recent7 与
  recent30 两次真实调用验证过数值不同。下面 v0.8 条目里"记录两个 `/cc/live/`
  接口忽略 `--date`"的结论已作废，保留只为存档。
- 新增 `item-sku-list --by <属性名>`：按尺码/颜色分类等属性聚合销售（对应网页
  「属性分析」表），走 `/cc/item/sale/sku/attrDetail.json`。

### v0.8（2026-08-05）
- 新增单品五件套（只读）：`item-search` / `item-360` / `item-sku-list` / `item-flow-source` / `item-refund`
- 商品域字段入 `fields.json`；各属性退款表补属性值列
- cc 系日期窗口只支持 1/7/15/30 天，其余宽度在本地就报错（服务端一律 `code=1003`）
- 记录两个 `/cc/live/` 接口忽略 `--date` 的实时口径（实测）

### v0.7（2026-07-20）
- **字段字典 `fields.json`**：数据概览 62 个原始字段全部入册（32 已破译 + 30 中文名待破译），每条带适用命令、数值格式、口径备注（含退款率「近 7 天仍在爬升、禁止下结论」等坑规矩）。
- **`home-table` 万能选列**：`--fields a,b,c` 只取指定列、`--all-fields` 吐全 62 项；发现新字段的「三招方法论」+ 写回规矩写进 SKILL.md。
- **指定 Chrome profile**：`SYCM_CHROME_PROFILE="Profile 1"` 环境变量，登录态不在 Default 身份时也能读到。

### v0.6（2026-07-19）
- **AI 经营分析 Skill**：新增标准全景、日体检、周复盘、测款、退货归因、广告 ROI、客服质检七个模块及严格输出口径。
- **逐笔退款溯源**：新增 `refund-all-list` 和 `refund-origin-analysis`，可从退款完结日追到原订单付款日，并区分退货退款、未发货退款、未收货退款和已收货仅退款。
- **口径纠错**：禁止用当日完结的历史订单退款除以当日成交；新品总览/趋势的日期能力按真实请求结果标注。
- **安全加固**：限制 CDP 为本机地址、Excel 下载为 HTTPS，并补充分页去重和不安全 URL 测试。

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
