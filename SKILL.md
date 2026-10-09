---
name: sycm-cli
version: "1.3.6"
description: sycm-cli 是一款读取生意参谋店铺数据的工具，借助本地浏览器中已登录的 sycm.taobao.com 账号获取淘宝/天猫自营店铺数据，生成标准报表并执行经营分析。支持首页大盘、销售、商品、新品、退款、接待、评价、客服对话、Excel 导出和多店铺登录态，可生成单品诊断报告（网页，含首末对比、同店对标和 45 天「量·率·速」增长方案）。当用户提到生意参谋、sycm、店铺数据、标准报表、店铺体检、日检、周复盘、单品诊断、商品为什么卖不动、增长方案、测款、退货归因、客服质检、商品 360、新品追踪、下载店铺 Excel 或让 AI 分析店铺时使用。
author: Rakel
homepage: https://rakel.top
---

# 生意参谋 sycm-cli

sycm-cli 是一款读取生意参谋店铺数据的工具，可帮助你为用户生成标准报表、执行经营分析和生成单品诊断报告。工具在用户的电脑上运行，使用用户在 Chrome 中已登录的生意参谋账号，所有操作均为只读。

> 本 Skill 作者：Rakel · 个人网站：https://rakel.top

**适用人群**：淘宝/天猫店铺商家读取本店的客服聊天、评价、销售、商品等经营数据，用于内部分析。

**前置条件**：

- **登录**：Chrome 已登录 sycm.taobao.com。
- **取数方式（先看系统）**：Mac 不需要插件，工具直接读取 Chrome 中的登录状态；读不到登录且装了「taobao-cli 取数桥」插件时，自动改用插件。Windows 必须安装插件。无论哪个系统，取数都只用本工具的命令：不要用 AI 助手自带的浏览器（例如 Codex 内置浏览器）打开后台，也不要另写脚本抓取。
- **Codex 沙箱**：在 Codex 中一律用 MCP 工具取数，不要在终端里运行脚本——Codex 的沙箱默认不让联网、不让开本机端口，脚本会报「依赖下载失败」或「当前环境不允许在本机开端口」。MCP 还没接入时，请用户在自己打开的终端里运行 `mcp install`，再完全退出并重开 Codex。不要把「改成完全访问」当作解决办法（在 Windows 上有时不生效），不要自己另找运行环境，也不要改用你自带的浏览器取数。
- **运行环境**：已安装 `uv`（或 Python 3.10+）。

## 首次使用

拿到本 Skill 后，先按以下步骤检查环境。

0. **确认是否已接入 MCP**：如果你的工具列表中已有 `shopdata-sycm` 的 doctor、commands、run、guide，说明已接入 MCP（让 AI 助手直接调用本工具的接口）。请直接用这几个工具取数，无需运行下面的脚本。

   **注意**：在 Codex 中运行脚本时，如果提示「没有连上浏览器插件」，且原因是沙箱拦截了本机端口，请让用户在终端运行 `scripts/sycm.sh mcp install`（Windows：`scripts\sycm.cmd mcp install`），重新打开 Codex 后改用 MCP 工具。不要改用你自带的浏览器取数。
1. **运行自检**：运行 `scripts/sycm.sh doctor`（Windows：`scripts\sycm.cmd doctor`）。看到 `probe = ok` 即表示环境检查通过，可以跳到下一节。
2. **安装取数桥插件（Windows 必做；Mac 一般不用）**：如果提示「没有连上浏览器插件」或插件「太旧」，请引导用户按 `extension/README.md` 安装插件：在 `chrome://extensions` 中打开「开发者模式」，点击「加载已解压的扩展程序」，选择本目录的 `extension/unpacked`，并把这个文件夹的完整路径告诉用户。用户已为其他工具安装过插件且版本足够新时，无需重复安装。
3. **登录生意参谋**：如果提示未登录，请让用户在同一个 Chrome 中打开 https://sycm.taobao.com 并登录，然后再运行一次 doctor。看到 `probe = ok` 即表示准备完成。

   **重要**：账号密码由用户自己输入，你不要代填。

## 基本用法

以下命令读取某日前 N 个旺旺咨询会话，并保存为 `chats.json`：

```bash
scripts/sycm.sh fetch-recent --date YYYY-MM-DD --limit 10 --out chats.json
```

`chats.json` 包含这些会话的元数据和全部消息内容，可以直接交给 LLM 做客服分析。

## 工作原理

工具完全在本地运行，使用浏览器中已登录的账号：

- **插件**：Windows 只用此方式；Mac 读不到登录且装了插件时也会用。命令行在本机 127.0.0.1 临时启动一个小服务，插件在用户已登录的生意参谋页面中代为发送只读请求，再把结果交回命令行。此方式不读取 cookie，也不需要专用浏览器。
- **Mac 默认**：用 `browser_cookie3` 从 Chrome 直接读取 cookie，再用 `curl_cffi` 直接调用生意参谋接口。
- **不改动浏览器**：不导出 cookie，不修改浏览器设置，不关闭 Chrome 的安全保护。

请求形态尽量接近正常的人工浏览，但仍须控制频率，并遵守下文的安全护栏。

## 执行原则

- **先确认需求**：先确认店铺 profile、日期范围和用户需要的报表或分析，再调用只读命令。
- **优先使用已验证的子命令**：除非用户明确要求侦查新接口，不要用 `api` 猜测路径或参数。
- **真实数据只存本地**：把真实数据写入本地临时文件，不要写入 Skill、Git 或可分发的文档。
- **默认脱敏**：默认对买家昵称、客服昵称、订单 ID、商品 ID 和聊天正文脱敏。只有用户明确要求分析对话时，才读取必要的正文。
- **结论注明出处**：每个结论都附上数据来源、日期和字段名。数据不足时标记“不能判断”，不要用经验补数。
- **不跨期计算退款率**：不要用“当日完结的历史订单退款”除以“当日成交”得出商品退款率。无法建立同一订单队列时，只报告官方字段口径或“当日完结退款金额/笔数”。
- **追溯退款来源**：追溯某日完结的退款时，优先运行 `refund-origin-analysis --date <D>`。它按 `ordPayTime` 找到原付款日并区分退款场景，但结果本身仍不是退货率。

## 模块 1：标准全景报表

当用户说“把现在能拿到的数据全部展开”“做一份给其他 AI 分析的报表”或“给每张表一个真实范例”时，执行本模块。

### 范围

按五个数据域组织报表，不要把一张多行表压缩成一个指标：

| 数据域 | 必查命令 |
|---|---|
| 总览大盘 | `home-overview`, `home-table`, `home-trend`, `grow-factor` |
| 商品与新品 | `item-list`, `cate-list`, `new-product-overview`, `new-product-list`, `new-product-trend`, `order-overview`, `order-trend`, `order-distribution`, `order-recommend` |
| 销售与售后 | `sale-shop-list`, `sale-item-list`, `refund-item-list` |
| 客户与客服 | `reception-list`, `evaluation-list`, `sale-cs-list`, `inquiry-loss-list`, `slow-rsps-list` |
| 内容与直播 | `preheating-metrics`, `live-guide-overview`, `live-guide-trend` |

`fetch-recent` 的聊天正文默认不进入全景报表，只报告可用会话数和字段结构，以免不必要地暴露买家信息。

### 执行步骤

1. **检查登录**：运行 `scripts/sycm.sh doctor`。失败时停止，并告知用户登录状态有问题。
2. **保存命令面**：运行 `scripts/sycm.sh --help`，保存当前命令面，防止报表清单落后于代码。
3. **取最小样本**：对上表每个命令只取一个最小的真实样本。列表类使用 `--limit 1`，趋势类使用最小的有效日期范围。
4. **保存输出**：把完整输出保存到本地临时目录，对话中只展示脱敏后的范例。
5. **保留空表**：命令返回空表时仍保留该行，标记“0 条/当日无数据”。不要把空表说成接口不可用。
6. **记录失败**：命令失败时记录错误类型（登录、权限、风控、参数、网络），不要编造样例。

### 输出合同

先输出覆盖摘要：检查日期、店铺 profile，以及成功、空表、失败的命令数。然后为每个数据域输出一张表：

| 报表 | 命令 | 日期口径 | 记录数 | 关键字段 | 脱敏真实样例 | 口径/限制 | 状态 |
|---|---|---|---:|---|---|---|---|

**硬性要求**：

- **真实样例**：只取一行或一个汇总对象，且必须来自本次真实请求。
- **关键字段**：写出中文名和原始 field code，便于其他 AI 继续分析。
- **列全命令**：不要漏列已验证的命令，不要用“等”省略剩余报表。
- **只呈现数据**：本模块不做经营归因。需要分析时，再进入对应的日体检、周复盘或专项模块。

## 分析模块

当用户要求日体检、周复盘、测款、退货归因、广告 ROI 或客服质检时，先读完 [references/analysis-workflows.md](references/analysis-workflows.md) 中对应模块的全部指令，再严格按其中的口径、输出合同和停止条件执行。

## 生成单品诊断报告

单品诊断报告是本工具用 `item-report` 生成的七页网页报告。当用户说「诊断一下这个商品」「这个款为什么卖不动」「做个单品分析报告 / 增长方案」时，按以下步骤操作：

1. **取数**：运行 `scripts/sycm.sh item-report --item-id <商品ID>`，约需两三分钟，数据存为 `reports/item-<ID>-<日期>-<天数>d.data.json`。
   - **`--days 7/15/30`**：查看最近 2×N 天，用前 N 天和后 N 天对比。默认 7，即最近 14 天。
   - **`--compete 竞品对比.json`**：有达摩盘工具时，先运行 `dmp compete-item --item <商品ID> --out 竞品对比.json`（不指定竞品时，使用达摩盘推荐的同类成功商品），再加上此参数。竞品数据在写归因时作为证据。
2. **写分析**：读完 [references/item-report-guide.md](references/item-report-guide.md)，再按其中的方法和格式写分析，存为同名的 `.analysis.json`。
3. **生成网页**：运行 `scripts/sycm.sh item-report --analysis <分析文件>`，生成单文件网页和一份表格（.xlsx：执行跟踪、动作清单、每日数据、两个周期对比、同店对标、流量来源、SKU）。如需发给他人，加 `--mask` 生成脱敏版，同时附带一份仅供用户自己查看的代号对照（.mapping.txt）。
4. **每周复盘**：方案开始后，每周运行一次 `scripts/sycm.sh item-report --track --analysis <分析文件>`。程序逐天用实际数与每日门槛对比，生成一份填好实际数的跟踪表。复盘的写法见指南第七节。

网页共七页：

| 页面 | 内容 |
|---|---|
| 诊断总览 | 结论摘要、定性、两条硬伤、同店对标一句话、首末对比 |
| 趋势图表 | 支付金额和转化率、访客和搜索引导访客、本品对店铺大盘，以及每日明细 |
| 同店对标 | 和本品同一级类目的商品、同店最佳、店铺主力商品前 12 |
| 下滑归因 | 按影响权重排序，附证据和对应动作 |
| 45 天方案 | 量·率·速目标、阶段路线图、每日门槛、动作清单、风险 |
| 目标模拟器 | 拖动访客、转化率、客单价，测算日均支付金额与基线和方案目标的关系 |
| 数据缺口 | 补数清单、口径 |

流量来源、标题词、详情页、SKU、退款、访客画像和达摩盘数据不单独成页。这些数据保存在数据文件中，供你写归因和动作时作为证据。

## 子命令

### 旺旺咨询接待

以下命令读取旺旺咨询会话，包括完整的对话内容。

| 子命令 | 用途 |
|---|---|
| `doctor` | 检查能否读取 cookie、登录状态是否有效 |
| `list --date YYYY-MM-DD [--page N --size N]` | 读取某日的咨询会话列表（不含消息内容） |
| `detail <dataId>` | 读取单个会话的全部消息（自动翻页） |
| `fetch-recent --date YYYY-MM-DD --limit N [--out file]` | **主要命令**：一条命令读取会话列表和全部详情，获得完整数据 |

### 常用日维度列表

以下命令自 v0.2 起提供，每个子命令都支持 `--date YYYY-MM-DD --limit N --raw --out file`：

| 子命令 | 对应生意参谋页面 | 字段 |
|---|---|---|
| `reception-list` | 服务/接待明细 | 开始/结束时间、买家、客服、是否回复 |
| `evaluation-list` | 服务/售后评价（邀评明细） | 接待时间、邀评时间、买家、客服、来源 |
| `sale-shop-list` | 商品/销售分析 | 商品 ID/标题、店铺销售额、客服销售额、静默销售额 |
| `sale-item-list` | 交易/订单明细 | 订单时间、订单金额、买家、客服、是否静默 |
| `sale-cs-list` | 客服销售明细（旺旺销售） | 订单时间、买家、客服 |
| `inquiry-loss-list` | 服务/询单流失 | 开始/结束时间、买家、客服 |
| `slow-rsps-list` | 服务/慢响应 | 日期、开始/结束时间、买家、客服 |

示例：

```bash
scripts/sycm.sh sale-shop-list --date YYYY-MM-DD --limit 10
scripts/sycm.sh evaluation-list --date YYYY-MM-DD --limit 20 --out eval.json
scripts/sycm.sh reception-list --date YYYY-MM-DD --raw   # 输出原始 JSON
```

### 商品大类

以下命令自 v0.4 起提供，覆盖商品排行、商品 360、品类 360 和新品追踪。它们使用生意参谋商品板块的**新接口（cc/* 系列，cc-v2 风格）**，参数与上文的旧 csp 接口完全不同：

- **日期参数**：`dateRange="YYYY-MM-DD|YYYY-MM-DD"` + `dateType=day|recent7|recent15|recent30`。
- **返回值**：response 中的字段值常为 `{value, cycleCrc, syncCrc}` 嵌套对象，CLI 已自动提取 `.value` 展示。

| 子命令 | 对应生意参谋页面 | 关键字段 | 备注 |
|---|---|---|---|
| `item-list` | 商品/商品排行（`/cc/item_rank`）或商品 360（`/cc/item_archives`） | 商品标题、支付金额/买家数/件数/转化率/客单价、访客数、加购件数、收藏人数、平均停留时长、详情页跳出率、搜索引导访客数、成功退款金额（12 项，其余 29 个字段用 `--raw` 查看） | 使用 `/cc/item/view/top.json`（历史档接口）。旧接口 `/cc/item/portal/itemList.json` 只在网页「实时」档使用，且不识别 `indexCode`（实测无论传多少个都只返回 3 个指标），已弃用 |
| `cate-list` | 商品/品类 360（`/cc/new_cate_archives`） | cateName、payAmt、itmUv、payRate | 返回当日全行业的品类数据（含 children 树） |
| `new-product-list` | 商品/新品追踪 → 列表（`/cc/new_item_analysis`） | 商品、publishNewTime、payAmtNew、shopUvNew | 可用 `--cate-id` 限定类目 |
| `new-product-overview` | 商品/新品追踪 → 顶部汇总卡 | newItmCnt、shopUvNew、payAmtNew、addCartCntNew | 返回汇总对象，不返回列表 |
| `new-product-trend` | 商品/新品追踪 → 趋势图 | self/industry 两组时序数据 | 建议加 `--raw` 获取完整数据 |

**注意**：日期能力以实测为准。overview 只确认支持单日；trend 的单日调用返回截至该日的固定 30 日序列；overview 和 trend 显式传入 7/30 日区间会报 1003。list 的 7/30 日调用虽然成功，但曾返回完全相同的结果，确认前不要描述为两个独立窗口。

示例：

```bash
# 看昨天销售前 10 商品 (商品排行)
scripts/sycm.sh item-list --date YYYY-MM-DD --limit 10

# 看品类 360（全行业品类销售）
scripts/sycm.sh cate-list --date YYYY-MM-DD --limit 5

# 新品追踪 (3 个子接口)
scripts/sycm.sh new-product-overview --date YYYY-MM-DD           # 总览
scripts/sycm.sh new-product-list --date YYYY-MM-DD --limit 10    # 列表
scripts/sycm.sh new-product-trend --date YYYY-MM-DD --raw        # 趋势
```

**提示**：字段值是嵌套对象，加 `--raw` 才能获取对比指标（cycleCrc 为环比，syncCrc 为同比）。摘要模式只显示 `.value`。

### 单品分析

以下命令自 v0.8 起提供，用于回答「这个款为什么不行、哪个尺码在退、流量从哪来」。全部只读，均使用 cc-v2 风格接口。

先用 `item-search` 获取 `itemId`，其余命令都接 `--item-id <商品ID>`。也可以直接用 `--search <货号/标题关键词>` 代替：**只有唯一命中时才继续；命中多个时会列出候选，并以退出码 1 停止**，不做猜测。

| 子命令 | 对应生意参谋页面 | 产出 | 日期口径 |
|---|---|---|---|
| `item-search <关键词>` | 商品 360 搜索框 | 商品 ID、货号、价格、库存、标题 | 目录搜索，无日期参数 |
| `item-360` | 商品 360 顶部 | 核心指标（本店值 + 环比 + `cmpt` 对比值）和销售总览 | 都支持 `--date` |
| `item-sku-list` | 商品 360 / 销售分析 / SKU 销售明细 | 各 SKU 组合的加购件数、支付金额/件数/买家数；加 `--by <属性名>` 时改为输出按属性聚合的表；加 `--live` 时改为输出现有库存/售罄率/库存可售天数（与 `--by` 互斥） | 默认支持 `--date`；`--live` 为当前快照，忽略 `--date` |
| `item-flow-source` | 商品 360 / 流量来源 | 来源树（多级）：uv、pv、收藏、加购、支付买家/金额、转化率 | 支持 `--date` |
| `item-refund` | 商品 360 / 退款 | 一条命令输出三张表：退款原因分布、各 SKU 退款、各属性退款（含属性值） | 支持 `--date`，按**原订单付款时间**统计 |
| `item-profile` | 商品 360 / 客群洞察 / **客群画像** | 购买该商品的人群：人群标签/年龄/性别/新老客/省/市/品牌偏好/类目偏好/预测消费层级/淘气值，共 10 个维度 | **只支持单日**，多日区间会被拒绝 |
| `item-loss-risk` | 商品 360 / 客群洞察 / **客群细分** | 潜在流失风险：预测本商品的客户会流向哪些商品（**含友商**），附按店铺汇总 | 人气值**仅单日提供**，多日时该列会被静默去掉 |
| `item-detail` | 商品 360 / 详情分析 | 核心概况 11 个指标，每项都带**同行均值/同行优秀**；详情页逐屏数据（11 个楼层，两级树）显示买家在哪一屏离开 | 支持 `--date` |
| `item-price` | 商品 360 / 价格分析 | 本商品的价格定位（挂牌价 / 实际件单价 / 所属价格带）和类目各价格带大盘，**标出本商品所在档** | 支持 `--date` |
| `item-title` | 商品 360 / 标题优化 | 标题中每个词带来的搜索访客数，**直接列出零引导词**，并给出推荐词（类目/属性/品牌/长尾） | 支持 `--date` |
| `item-bundle` | 商品 360 / 关联搭配 | 购买本商品的人还买了什么：系统推荐和卖家自选（未配置时会注明未配置，与读取失败区分） | 支持 `--date` |
| `item-content` | 商品 360 / 内容分析 | 关联视频和内容带来的种草点击、粉丝点击、收藏、加购、支付（汇总和逐条内容） | **默认近 30 天**，内容效果看单日没有意义 |
| `item-service` | 商品 360 / 服务体验 | 售前咨询/售后首次解决率/有效回复/主动评价/问大家声量/成功退款，每项带对比值与环比 | 支持 `--date` |

**公共参数**：`--item-id` / `--search` / `--date` / `--end-date` / `--limit` / `--page` / `--raw` / `--out`。

```bash
# 1. 先拿商品 ID（支持标题关键词、商品ID、商品URL、货号）
scripts/sycm.sh item-search 连衣裙 --limit 3

# 2. 单品总体面貌（核心指标 + 销售总览，都按 --date）
scripts/sycm.sh item-360 --item-id 123456789 --date YYYY-MM-DD

# 3. 哪个 SKU 组合卖得动（近 30 天，--date 与 --end-date 相隔 30 天）
scripts/sycm.sh item-sku-list --item-id 123456789 --date 起始 --end-date 结束 --limit 10

# 3b. 换个视角：哪个尺码/颜色卖得动（网页「属性分析」表，同一份数据按属性聚合）
scripts/sycm.sh item-sku-list --item-id 123456789 --date 起始 --end-date 结束 --by 尺码

# 3c. 现在该补哪个 SKU 的货（现有库存/售罄率/库存可售天数，当前快照，--date 不生效）
scripts/sycm.sh item-sku-list --item-id 123456789 --live --limit 10

# 4. 访客从哪来、哪个渠道转化差
scripts/sycm.sh item-flow-source --item-id 123456789 --date YYYY-MM-DD --limit 10

# 5. 为什么退、哪个 SKU / 哪个尺码退得多（近 30 天）
scripts/sycm.sh item-refund --item-id 123456789 --date 起始 --end-date 结束 --limit 10

# 12. 这个款的服务/售后有没有拖后腿
scripts/sycm.sh item-service --item-id 123456789 --date 起始 --end-date 结束

# 11. 哪条视频真的带货
scripts/sycm.sh item-content --item-id 123456789 --date 起始 --end-date 结束

# 10. 买了这个款的人还买了什么（配套餐用）
scripts/sycm.sh item-bundle --item-id 123456789 --date YYYY-MM-DD

# 9. 标题哪几个字是白占的
scripts/sycm.sh item-title --item-id 123456789 --date YYYY-MM-DD

# 8. 这个价位段值不值得待 —— 本款所在档的盘子多大、涨得多快
scripts/sycm.sh item-price --item-id 123456789 --date YYYY-MM-DD

# 7. 详情页哪一屏在掉人 + 跟同行比差在哪
scripts/sycm.sh item-detail --item-id 123456789 --date YYYY-MM-DD --limit 20

# 6b. 客户要跑去哪（含友商；人气值只有单日有）
scripts/sycm.sh item-loss-risk --item-id 123456789 --date YYYY-MM-DD --limit 20

# 6. 买这个款的是谁（默认人群标签；--all 一次跑完 10 个维度）
scripts/sycm.sh item-profile --item-id 123456789 --date YYYY-MM-DD
scripts/sycm.sh item-profile --item-id 123456789 --date YYYY-MM-DD --by province
scripts/sycm.sh item-profile --item-id 123456789 --date YYYY-MM-DD --all --limit 5

# 也可以不带 ID，直接按货号搜（命中唯一才继续）
scripts/sycm.sh item-sku-list --search A1001 --by 颜色分类
```

不传 `--by <属性名>` 时，输出 SKU 组合明细（`skuName` 为“颜色分类:xx;尺码:xx”这样的组合值）。传入后改用按属性聚合的接口，输出该属性下每个取值的汇总（`attrValue` 列）。属性名来自商品自身定义的属性（常见的有“尺码”“颜色分类”），代码中不写死枚举。服务端不识别的属性名会直接报错，不会静默返回空表。

#### 单品命令口径警告

分析前请先阅读以下内容。

- **日期窗口只支持 1 / 7 / 15 / 30 天**：`--date` 与 `--end-date` 的间隔必须恰好是其中一种宽度，其他宽度服务端一律以 `code=1003` 拒绝（2026-08-05 实测，cc/flow/csp 三族一致），CLI 会先在本地报错。`recentN` **相对 `dateRange`** 计算，与今天无关（同日实测：7 天窗口的返回值等于窗口内七个单日之和）。
- **日期档与「实时」档使用不同接口**：生意参谋商品板块多次出现同一类接口分裂，日 / 7 天 / 30 天档与「实时」档使用两个完全不同的接口，只在其中一档录到的接口签名不能代表另一档。此问题已出现三次：`item-sku-list` 和 `item-360` 的销售总览在最初侦查时页面停在「实时」档，录成了 `/cc/live/...` 系列（写死当天，忽略传入的日期），现已改为不带 `live/` 的日期口径接口（2026-08-05 用 recent7/recent30 两次真实调用对照，数值不同）；`item-list` 同理，最初录到的 `/cc/item/portal/itemList.json` 不识别 `indexCode`（无论传多少个都只返回 3 个指标），页面日期档实际使用 `/cc/item/view/top.json`，切换后单次调用可获得 41 个字段。
- **`item-sku-list` 保留实时档，用 `--live` 显式切换**：现有库存 `currentStockCnt`、售罄率 `sellRate`、库存可售天数 `stockDays` 只有实时接口提供，按日期查询的接口无法获得这三个字段（加了 `indexCode` 也会被静默丢弃）。`--live` 和 `--by` 互斥。
- **`item-refund` 统计的是退款事件归属，不能当作退货率**：三张表都按原订单付款时间统计（`refundDateType=pay`）。真实退货率要以同一付款批次的支付订单数作为分母。CLI 不计算退货率，你也不要用这些数自行计算。
- **`item-refund` 的「退款原因」表已修复（2026-08-06）**：该表曾长期返回 0 行，原因是 `rfdIntervalLevel` 传了猜测的 `"ALL"`，服务端照收、不报错，静默返回空结果；页面实际传的是 **`99`**。现在可以正常获取 8 类原因，并带有 `rfdReasonTypeCn`（**内部原因 / 消费者原因**）。请先看这一列，内部原因才是店铺自己能改进的。金额字段是 `itemRfdAmt`，响应中不存在 `itemSucRfdAmt` 这个字段名。
- **退款率字段近 7 天仍在累积**：各 SKU 表中的 `payAmtRfdRate` / `ordRfdRate` 是平台自行计算的支付时间口径退款率，实测 T-6 仍在上升。`--date` 默认为昨天，正处于这一区间。不要用近 7 天的退款率下结论。
- **`item-360` 的 `*Cmpt` 不能当作同行绝对值**：实测本店 payAmt / uv 为三四位数时，对应的 `*Cmpt` 全部落在 0~1 区间，量级完全不符。具体口径尚未核实，不要当作同行对比解读。
- **`item-profile` 只支持单日**（2026-08-06 实测）：传 `recent7` / `recent30` 时，服务端仍返回 `code=0`，但 data 始终为空数组，又一次出现「参数照收、结果静默变空」。CLI 在发送请求前会拦截多日区间。
- **`item-profile` 通常只有 `itmUv`（访问人群）有数据**：三个人群口径中，另外两个受样本量门槛限制。页面原文为「本店商品人群样本量小于 300 人，不统计客群画像」（2026-08-06 核对）。`payByrCnt`（成交人群）与 `appSearchUv`（搜索人群）的人数一般远低于 300，因此始终为空。由于本接口**只支持单日**，无法通过拉长窗口让人数达到门槛，**这两个画像实际上只有单日人数可达 300+ 的大流量爆款才能生成**。结果为空不代表缺少参数，也不代表该商品没有成交人群。
- **`brand_prefer` 维度只有标签、没有数值**：能返回品牌名，但访客数全为 0，占比全为空。命令会注明这是无法取数，与「没人偏好这些品牌」不同。
- **`new_old` 的 `Y`=新客户、`N`=老客户**（2026-08-06 用页面「新老占比」环形图核对）：CLI 显示为「新客户(Y)」，中文与原码并存。
- **`item-loss-risk` 的「预测流失人气」仅单日提供**：多日区间时行仍在，但 `customerCnt` 列会被服务端静默去掉。这是本项目第六次遇到「参数照收、结果悄悄缩水」。命令会显式提示，不要把没有数字的表当作正常结果解读。
- **`item-loss-risk` 的 `crowdType` 目前只核实了 `ptl-loss`**：页面「流失客户」「潜在客户」等选项应该还对应其他值，但服务端不返回白名单，前端 39 个 JS bundle 中也搜索不到。**未获取到的值没有写入**。
- **`item-detail` 的 `rivalAvg`/`rivalGood` 是真实的同行对比**（同行均值 / 同行优秀）：与本店值处于同一数量级，可以直接比较。它与 `item-360` 中量级不符、口径不明的 `*Cmpt` **含义不同**，不要混用。
- **`item-detail` 的 `byrType=all` 录自页面，不能猜测**：服务端对编造的 `byrType` / `detailType` 不报错，只静默返回空结果；猜错会得到一个始终为空、又看不出问题的命令。同类硬编码值还有 `level1LossStatus=cate-not-pay`、`indexes=itemLossUvIndex`（注意参数名是 `indexes`，不是 `indexCode`）。
- **`item-price` 的挂牌价与实际件单价要一起看**：实测同一商品挂牌价 210.99、实际件单价 158.10，相差 25%（活动/优惠）。只看其中一个会误判价格定位。
- **`item-price` 的 `tradeGrowthRate` 是字符串区间**（如「35190% ~ 35200%」）：服务端已格式化为文本，不能用于计算。`SupplyRatioIndex` 以大写 S 开头，是服务端原样返回的字段名，请勿更正。
- **`item-title` 的零引导词表现为「缺列」，数值不是 0**：没有带来搜索的词，所在行中没有 `guideSeUv` 键。CLI 显示 `-` 而不显示 0，因为 0 会被理解为「有统计只是量少」，实际情况是这个词没有引来任何一次搜索，在标题中不起作用。命令会直接列出零引导词的数量和词表，这是本模块唯一可以直接执行的结论。
- **`item-content` 的商品 ID 通过 `keyword` 参数传递，不用 `itemId`**：传成 itemId 时服务端只返回「请求参数非法」，从报错中很难看出原因。此外还需要 `accountRole=guanghe-all` 和 `indexCode`。返回结果中，`children` 外面包了一层 `{data:[...]}` 信封，里面才是逐条内容；直接当作行渲染会得到一整行横杠。
- **`item-service` 的 `needCycleCrc` 必须放在 `extMap` 中**：不能作为独立的 query 参数。作为独立参数传入时，服务端不报错，直接返回空 dict，曾因此误判为「这个 domainCode 取不到数」。
- **单品诊断模块没有单独命令**：该模块只有两个接口。`/cc/diagnose/coreIndex.json` 已包含在 `item-360` 中；`/cc/diagnose/getIndexAttention.json` 是「关注指标」的用户配置（本店未配置，返回 null），不含数据。查看单品诊断请直接用 `item-360`。
- **查看 `item-loss-risk` 时先看按店铺汇总的行**：客户流向自家其他商品（属正常现象，选品重叠）和流向友商（需要警惕）是两种完全不同的情况，混在一张 50 行的表中无法区分。

### 店铺级页面模块

以下命令属于阶段 3 的页面级模块，均为店铺级命令，不带 `--item-id`。

| 子命令 | 对应生意参谋页面 | 产出 | 日期口径 |
|---|---|---|---|
| `spu-list` | 商品/商品集分析 | 各商品集的支付金额/件数/件单价/含商品数 | **只支持单日**（多日返回 `param check error`，报错中不提示日期问题，CLI 会在本地先拦截） |
| `item-relate` | 商品/连带分析 | 主商品及其关联商品（关联支付人数/购买率/访客数） | 支持 `--date`，默认 `device=2` |
| `video-list` | 商品/素材分析/视频分析 | 各商品视频的曝光/点击/曝光点击率/有效播放/完播率/当日成交 | 支持 `--date` |
| `macro-monitor` | 商品/宏观监控 | 全店商品实时大盘 12 项（支付/访客/加购/收藏/转化率），每项带环比 | **实时快照，`--date` 不生效** |
| `problem-alarm` | 商品/重点商品/问题预警（隐藏路由） | 质量问题/缺货/高价限流商品计数和缺货明细 | 实时 |
| `interval-analysis` | 商品/宏观监控/商品区间分析 | 动销商品按价格带/支付件数/支付金额分段，显示各段商品数与占比（用 `--by` 切换视角） | 支持 `--date` |

```bash
scripts/sycm.sh spu-list    --date YYYY-MM-DD
scripts/sycm.sh item-relate --date 起始 --end-date 结束 --limit 5
scripts/sycm.sh video-list  --date 起始 --end-date 结束 --limit 20
scripts/sycm.sh macro-monitor   # 实时，不用传日期
scripts/sycm.sh problem-alarm   # 实时，不用传日期
scripts/sycm.sh interval-analysis --date YYYY-MM-DD --by ordPqt   # 你的货集中在哪个价位
```

`spu-list`、`item-relate`、`video-list` 三个命令的参数均录自页面请求，其中几处与直觉不符，均已固定在代码中：

- **商品集**：`spuType=**def**`，不是 `all`。
- **连带分析**：关联侧字段名带 `relate` 前缀（`relatePayByrCnt`），排序参数是 `mainOrderBy` + `relateOrderBy` + `relateOrder`，**没有** `order`/`orderBy`；只传 `mainOrderBy` 会返回 `code=600007`，且**消息为空**。
- **视频分析**：一次返回上千条（本店实测 1441），命令会报告总数，不要把一页当作全部。

两个实时命令的注意事项：

- **`problem-alarm` 的「质量问题商品」只有计数，无法获取明细**：在页面上点进去显示「请在新打开的页面中查看」，明细位于千牛体检中心，不在生意参谋中。命令会输出这句提示，这不代表 CLI 缺少功能。接口路径中的 `prolem` 是服务端对 problem 的原样拼写，请勿更正。
- **宏观监控是实时快照，`--date` 完全不生效**：实测 day / recent7 / recent30 三档返回的 `payAmt` 完全相同。接口路径中的 `marcro` 是服务端对 macro 的原样拼写，请勿更正。

### 首页大盘

以下命令自 v0.5 起提供，读取生意参谋**首页 `/portal/home.htm`** 顶部的数据概览和增长因子，即店铺经营者每天查看的官方口径大盘。这些命令使用独立的 `/portal/...` 只读 GET 接口，返回 `self`（本店）、`rivalAvg`（同行平均）、`rivalGood`（同行优秀）三档对标，均支持 `--date YYYY-MM-DD --raw --out file`。

| 子命令 | 对应板块 | 关键字段 |
|---|---|---|
| `home-overview` | 首页/数据概览（按日） | payAmt（支付金额）、netPaymentAmount（净支付）、uv（访客）、payByrCnt（支付买家）、payRate（转化率）、rfdSucAmt（退款额）、payAmtRfdRate（金额退款率）、cartByrCnt（加购）、buyAmtRatio（复购占比） |
| `home-table` | 首页/数据概览「表格」视图（多日并排） | 支付/意向/履约售后/推广 4 组完整 32 项，每格附较上一周期的变化，即页面上点击「表格」后显示的多日对比表 |
| `home-trend` | 首页/数据概览趋势（按日固定窗口） | 同上字段的时序数组 |
| `grow-factor` | 首页/增长因子 | newPortalAdPayAmt（广告引导成交）、portalLivePayAmt（直播）、newItmPayAmt（新品）、mbrPayAmt（会员）、totalPromoSpend、tROI |

```bash
scripts/sycm.sh home-overview --date YYYY-MM-DD          # 昨天的支付/访客/转化/退款率/加购
scripts/sycm.sh home-table    --date 起始 --end-date 结束  # 多日并排大表(默认最近6天)，含较上一周期
scripts/sycm.sh grow-factor   --date YYYY-MM-DD           # 广告引导/直播/新品/会员各贡献多少成交
scripts/sycm.sh refund-origin-analysis --date YYYY-MM-DD  # 该日完结退款来自哪些付款日/退款场景
scripts/sycm.sh refund-all-list --date YYYY-MM-DD --by case-end --raw  # 逐笔含订单号和原付款时间
scripts/sycm.sh home-overview --date YYYY-MM-DD --raw     # 拿全 self/rivalAvg/rivalGood + cycleCrc 环比
```

指标值为 `{value, cycleCrc}` 结构，摘要模式显示值，`--raw` 可获取环比。

**重要**：请用“日”口径获取稳定的汇总数据，不要用实时数据。实时数据在盘中会变动。

`home-table` 已收录**页面「数据概览」的完整 32 项**（支付 10 / 意向 7 / 履约售后 10 / 推广 5）。中文名照抄页面，字段码以「较上一周期」百分比作为唯一键反查确定（2026-07-18 对照全部展开的截图逐格核对，全部一致）。默认显示较上一周期的变化，可用 `--no-crc` 关闭；`--raw` 输出每日全部 62 个字段的 JSON。

**易错字段码对照**：以下字段码都曾出错，均通过 crc 反查确定，请勿猜测。

- **推广费**：关键词=`p4pExpendAmt` / 精准人群=**`cubeAmt`**（非 zzExpendAmt）/ 智能场景=`feedCharge` / 全站=`adStrategyAmt` / 淘宝客=`tkExpendAmt`
- **退款**：签收退款率=**`realPayrealRfdRate`**（≈个位数%，非 `sucRefundRate`≈65%）/ 金额退款率=`payAmtRfdRate` / 订单退款率=`ordRfdRate` / 退款处理时长（天）=`rfdFinshDur`
- **老客**：复购金额=`rePurchasePayAmount`（=olderPayAmt 同值）/ 复购人数=`payOldByrCnt`（=hasPurchasedUbyCnt 同值）/ 复购率=`hasPurchaseUbyCntRate`
- **其他**：客单价=`payPct`（=支付金额/支付买家数）/ 支付子订单数=`subPayOrdSubCnt` / 平均停留时长=`stayTime` / 旺旺人工响应时长（秒）=`wwReplyManualAvgTimeLen` / 平台判责率=`slrRespRate` / 物流到货时长（小时）=`avgSignTimeHh` / 24 小时揽收及时率=`gotInTime24hRate` / 咨询率=`consultRate`

**字段码的确定方法**：接口（overview / getTableData）只返回英文字段码和数值，中文名在首页子应用 `op-home`（诊断出的版本为 2.1.54）的前端代码中。该应用的 CDN 包名由 diamond 在运行时拼接，无法推测（试过 8 种 aligenius/* 均返回 404）；Claude 自己的浏览器未登录，无法运行那段配置。最终依据用户提供的完整截图和「较上一周期」百分比唯一键，把 32 个中文名逐一对应到字段码。

### 多店铺登录态

此功能自 v0.5 起提供，用于在一台电脑上管理多个店铺。默认使用浏览器中实时的登录状态（单店）。如需管理多个店铺，可以把每个店铺的登录状态保存为命名 profile。

**注意**：此功能仅支持 Mac。Windows 无法读取 Chrome 的登录状态，切换店铺时请在 Chrome 中换账号登录。

```bash
# 1. 在 Chrome 登录 A 店的 sycm，存下来
scripts/sycm.sh export-profile 示例主店
# 2. 之后任何命令加 --store 切换（放在子命令前）
scripts/sycm.sh --store 示例主店 home-overview --date YYYY-MM-DD
scripts/sycm.sh profiles                    # 看已存哪些店 + 新鲜度
```

- **存放位置**：profile 存放在 `~/.taobao-cli/profiles/`（0600 权限），其中含有长效登录凭据，**请勿提交到 git**。
- **与 qianniu-cli 共用**：**qianniu-cli 读取同一目录，一份 profile 两个工具通用**（都使用 taobao.com 登录）。
- **重新保存**：长效 cookie 失效后（通常为几周），在浏览器中重新登录该店铺，再运行一次 `export-profile` 即可。

### 导出 Excel

此功能自 v0.3 起提供。上文任意 list preset 都可以用 `excel` 子命令**以一行命令下载 Excel 文件**到本地（默认保存在 `~/Downloads/sycm-exports/`），可导出商品数据、评价、销售等。命令内部自动完成生意参谋自带的四步：申请导出、排队生成、获取 OSS 临时链接、自动下载。

```bash
# 下昨天的商品销售 Excel (最高频用法)
scripts/sycm.sh excel sale-shop-list

# 下指定日期范围 + 指定输出位置
scripts/sycm.sh excel evaluation-list --date YYYY-MM-DD --end-date YYYY-MM-DD --out /tmp/eval.xlsx

# 下旺旺接待对话明细
scripts/sycm.sh excel reception-list --date YYYY-MM-DD

# 看最近的导出任务列表（含失败/排队中的）
scripts/sycm.sh excel-tasks
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

**注意**：OSS 临时链接 1 小时内有效，过期后需重新运行命令。

### 通用接口探测

此为高级功能，用于探索尚未封装为子命令的接口：

```bash
scripts/sycm.sh api <path> --param key=val --param key2=val2
```

示例：

```bash
scripts/sycm.sh api ww/consultation/detail/list \
  -p startDate=YYYYMMDD -p endDate=YYYYMMDD -p dateType=day \
  -p dateRange=day -p orderBy=startTime -p pageNo=1 -p pageSize=10
```

## 输出格式

`fetch-recent` 输出以下结构的 JSON：

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

**判断发言方**：优先用列表中的客服昵称匹配 `userNickFrom`；无法匹配时按买家处理。

## 安全护栏

CLI 内置两层护栏。

**硬约束**：确认是风险信号时才停止，日常使用不会误触发。

- **风控词**：响应中含有 `滑块` / `验证码` / `操作过于频繁` / `请重新登录` 时立即停止运行，提示「平台返回内容里出现「…」，已立即停止」（`RiskStopped`，退出码 3）。
- **连续失败**：连续 2 次 HTTP 失败时立即终止。连续失败通常是登录状态过期或网络中断。

**软建议**：不会停止运行，只在 stderr 中提示。

- **请求间隔**：随机 1.8 ~ 3.5 秒，接近人工操作。
- **请求数提醒**：累计 200 次请求时提醒一次。风控按“短时高频”判定，不按“总量”判定，因此 200 只是提示点，并非上限。
- **硬上限**：如需防止脚本失控，可设置 `SYCM_REQUEST_LIMIT=N`。

作者的店铺每天都在使用本工具，正常范围内的查询基本没有遇到过风控；淘宝的风控通常只会弹出验证提醒。

**重要**：因风控停止（退出码 3）时请停止操作，请用户在浏览器中打开生意参谋完成验证后再继续，不要连续重试。

### 环境变量

| 变量 | 作用 |
|---|---|
| `SYCM_REQUEST_LIMIT=N` | 可选的硬上限：请求达到 N 次时停止。默认不设置，仅用于防止脚本失控 |

## 调用示例

**示例 1**：用户说“帮我看下昨天客服都聊了什么”。

```bash
DATE=$(date -v-1d +%Y-%m-%d)
scripts/sycm.sh fetch-recent --date $DATE --limit 10 --out /tmp/sycm-$DATE.json

# 然后读 /tmp/sycm-$DATE.json，逐个会话做分析
```

**示例 2**：用户说“分析下今天客服的尺码推荐是否准确”。

1. **读取对话**：运行今天的 fetch-recent。
2. **筛选会话**：筛选 messages 中包含“穿什么码 / 身高 / 体重 / XL / L 码”等关键词的会话。
3. **分析并输出**：逐个分析会话中客服推荐尺码的合理性，并输出报告。

## 字段字典

此功能自 v0.6 起提供，是你取数的主要方式：取数时以查字典为主，无需记忆命令。`tb/platforms/sycm/fields.json` 是机器可读的字段字典，每条记录为 `字段码 → {cn 中文名, scope 适用命令, fmt 格式, status, note 口径备注}`。数据概览的 62 个原始字段已全部收录（32 个已破译 `verified` + 30 个中文名待破译 `candidate`）。

**标准取数流程**：

1. **查字典**：先读 `fields.json`，找到字段码和它的 `note`（口径警告）。
2. **选列取数**：用 `--fields` 选列取数，例如 `home-table --fields payAmt,uv,payRate --date 起 --end-date 止`；需要全部 62 个字段时用 `--all-fields`。
3. **按需使用预设命令**：预设命令（`home-overview`/`home-table` 等）只是常用查询的快捷方式，并非唯一入口。

`status: candidate` 的字段中文名尚未破译（`cn` 暂时等于字段码），使用前请先验证。`note` 中的口径警告**必须遵守**（见下方「字段口径警告」）。

### 字段口径警告

写入数据结论前必须阅读以下内容。

- **退款率（支付时间口径，`payAmtRfdRate`/`ordRfdRate`/`payShopRfdAmt`）**：近 7 天的数值仍在上升（实测 T-6 仍未累积完整），**分析时禁止用近 7 天的数据下结论**。查看真实退货率需要等较早日期结算完成，或使用店主自己的现金回收账本。
- **签收退款率（`realPayrealRfdRate`）**：**T-3 才有数值，两周以上才稳定**，近几天显示 `-` 属于正常情况。

**提示**：配套工具 **alimama-cli**（万相台广告投放数据）同样带有 `fields.json` 字典，店铺体检和广告复盘可以搭配使用。

## 常见问题

| 现象 | 原因 | 处理方法 |
|---|---|---|
| `doctor` 提示“未找到淘宝登录态” | Chrome 未登录生意参谋，或 cookie 文件被另一个 Chrome 锁定 | 打开 Chrome 登录一次 sycm.taobao.com；登录状态在其他 Chrome 身份中时，设置 `SYCM_CHROME_PROFILE="Profile 1"` |
| `list` 返回 0 条 | 漏传 `orderBy=startTime` 参数 | CLI 已内置该参数，正常情况下不会出现 |
| 提示「平台返回内容里出现「滑块」，已立即停止」 | 生意参谋弹出了验证 | 停止操作，请用户在浏览器中打开生意参谋完成验证后再继续 |
| HTTP 5810 | session 超时 | 重新打开 Chrome 登录生意参谋 |
| 「没有连上浏览器插件」 | 插件未安装、已停用，或 Chrome 未打开 | 按 `extension/README.md` 安装插件。插件每 30 秒检查一次，请稍候再试 |
| 插件「太旧」或「文件夹不见了」 | 安装的是旧版本，或加载插件时使用的文件夹已被删除 | 在 `chrome://extensions` 中移除旧的取数桥插件，再加载本目录的 `extension/unpacked` |
| Windows 报 `AppData\Roaming\uv\python: 拒绝访问` | AI 助手的沙箱只允许访问工作区 | 运行 `scripts\sycm.cmd doctor`。Python、依赖和运行数据都存放在本目录的 `.runtime/` 中 |

## 文件清单

- **入口脚本**：`scripts/sycm.sh` / `scripts/sycm.cmd`（Mac / Windows）。
- **生意参谋命令**：`tb/platforms/sycm/`，包括命令（`cli.py`）、商品板块（`item.py`）和字段字典（`fields.json`）。
- **共用取数底座**：`tb/core/`，包括与取数桥插件的连接、登录、请求和护栏。
- **取数桥插件**：`extension/unpacked`；安装说明见 `extension/README.md`。
- **分析规则**：`references/analysis-workflows.md`，即分析模块的规则。
- **单品诊断报告指南**：`references/item-report-guide.md`。
- **Python 依赖**：`requirements.txt`（browser-cookie3、curl-cffi、websocket-client）。

## 已知限制

- **接口覆盖**：已登记的命令见上文的命令参考；没有登记的生意参谋页面，可以用 `api` 命令只读探测。
- **消息分页**：详情接口每页最多 10 条消息，CLI 会自动翻页。
- **列表分页**：列表 `pageSize` 实测最大约 20，过大时会被服务端截断。
- **Chrome 资料**：Mac 不装插件时读取 Chrome Default 资料的 cookie，登录在其他资料中时设置 `SYCM_CHROME_PROFILE="Profile 1"`；Windows 只通过插件取数。
