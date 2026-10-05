---
name: sycm-cli
description: 使用 sycm.taobao.com 的已登录本地浏览器读取淘宝/天猫自营店铺数据，生成标准报表并执行经营分析。覆盖首页大盘、销售、商品、新品、退款、接待、评价、客服对话、Excel 导出和多店铺登录态。当用户提到生意参谋、sycm、店铺数据、标准报表、店铺体检、日检、周复盘、测款、退货归因、客服质检、商品 360、新品追踪、下载店铺 Excel 或让 AI 分析店铺时使用。
author: Rakel
homepage: https://rakel.top
---

# sycm-cli — 生意参谋数据与店铺分析 Skill

> 本 Skill 作者：Rakel · 个人网站：https://rakel.top

**适用人群**：淘宝/天猫店铺商家自己拉取自己店铺的客服聊天、评价、销售、商品等经营数据，用于内部分析。

**前置条件**：
- Chrome 已登录 sycm.taobao.com
- 已装取数桥插件（共用插件，别的店铺数据工具装过就不用再装）：Windows 必须；Mac 可选，不装就直接读 Chrome 的登录
- 已装 `uv`（或 Python 3.10+）

## 首次使用（拿到这个 skill 后第一件事，AI 先做这个）

1. 运行 `scripts/sycm.sh doctor`（Windows：`scripts\sycm.cmd doctor`）。看到 `probe = ok` 就装好了，跳到下一节。
2. 提示「没有连上浏览器插件」或插件「太旧」：带用户照 `extension/README.md` 装插件——`chrome://extensions` 打开开发者模式，「加载已解压的扩展程序」选本目录的 `extension/unpacked`（把这个文件夹的完整路径告诉用户）。别的工具装过、版本够新就不用再装。
3. 提示没登录：请用户在同一个 Chrome 里打开 https://sycm.taobao.com 登录（账号密码由用户自己输入，你不要代填），再运行一次 doctor。

## 一句话用法

```bash
scripts/sycm.sh fetch-recent --date YYYY-MM-DD --limit 10 --out chats.json
```

输出 `chats.json` 包含某日前 N 个会话的元数据 + 全部消息内容，可直接喂给 LLM 做客服分析。

## 工作机制

纯本地运行，用浏览器里已经登录的账号：

1. **装了插件**（Windows 必须）：命令行在本机 127.0.0.1 临时开一个小服务，插件在用户已登录的生意参谋页面里替它发只读请求，结果交回命令行。不读 cookie、不用专用浏览器。
2. **Mac 没装插件**：用 `browser_cookie3` 从 Chrome 直读 cookie，`curl_cffi` 直调 sycm 接口。
3. 不导出 cookie、不改浏览器设置、不关闭 Chrome 的安全保护。

请求形态尽量贴近正常人工浏览，但仍然必须控制频率并遵守下面的安全护栏。

## AI 执行原则

- 先确认店铺 profile、日期范围和用户要的报表/分析，再调用只读命令。
- 优先使用已验证的子命令；除非用户明确要求侦查新接口，不使用 `api` 猜路径或参数。
- 将真实数据写到本地临时文件，不写入 Skill、Git 或可分发文档。
- 默认对买家昵称、客服昵称、订单 ID、商品 ID 和聊天正文脱敏。只有用户明确要求对话分析时才读取必要正文。
- 每个结论附上数据来源、日期和字段名；数据不足时标记“不能判断”，不用经验补数。
- 不将“当日完结的历史订单退款”除以“当日成交”生成商品退款率。无法建立同一订单队列时，只报告官方字段口径或“当日完结退款金额/笔数”。
- 追溯某日完结退款时，优先执行 `refund-origin-analysis --date <D>`；它按 `ordPayTime` 找到原付款日并区分退款场景，但本身仍不是退货率。

## 模块 1：标准全景报表

当用户说“把现在能拿到的数据全部展开”、“做一份给其他 AI 分析的报表”或“给每张表一个真实范例”时，执行本模块。

### 范围

按五个数据域组织，不将一张多行表压缩成一个指标：

| 数据域 | 必查命令 |
|---|---|
| 总览大盘 | `home-overview`, `home-table`, `home-trend`, `grow-factor` |
| 商品与新品 | `item-list`, `cate-list`, `new-product-overview`, `new-product-list`, `new-product-trend`, `order-overview`, `order-trend`, `order-distribution`, `order-recommend` |
| 销售与售后 | `sale-shop-list`, `sale-item-list`, `refund-item-list` |
| 客户与客服 | `reception-list`, `evaluation-list`, `sale-cs-list`, `inquiry-loss-list`, `slow-rsps-list` |
| 内容与直播 | `preheating-metrics`, `live-guide-overview`, `live-guide-trend` |

`fetch-recent` 的聊天正文不默认进入全景报表；只报告可用会话数和字段结构，避免不必要暴露买家信息。

### 执行

1. 运行 `scripts/sycm.sh doctor`；失败则停止，告知用户登录态问题。
2. 运行 `scripts/sycm.sh --help` 保存当前命令面，防止报表清单落后于代码。
3. 对上表每个命令只取一个最小真实样本；列表类使用 `--limit 1`，趋势类使用最小有效日期范围。
4. 保存完整输出到本地临时目录，在对话中只展示脱敏范例。
5. 命令返回空表时仍保留该行，标记“0 条/当日无数据”；不把空表说成接口不可用。
6. 命令失败时记录错误类型（登录、权限、风控、参数、网络），不猜造样例。

### 输出合同

首先输出覆盖摘要：检查日期、店铺 profile、已成功/空表/失败命令数。然后每个数据域输出一张表：

| 报表 | 命令 | 日期口径 | 记录数 | 关键字段 | 脱敏真实样例 | 口径/限制 | 状态 |
|---|---|---|---:|---|---|---|---|

硬性要求：

- “真实样例”只取一行或一个汇总对象，但必须来自本次真实请求。
- “关键字段”写中文名和原始 field code，便于其他 AI 继续分析。
- 不少列已验证命令；不用“等”省略剩余报表。
- 本模块只呈现数据，不做经营归因。需要分析时，再进入对应的日检、周复盘或专项模块。

## 分析模块

当用户要求日体检、周复盘、测款、退货归因、广告 ROI 或客服质检时，读取 [references/analysis-workflows.md](references/analysis-workflows.md) 中对应模块的全部指令，严格按其口径、输出合同和停止条件执行。

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
scripts/sycm.sh sale-shop-list --date YYYY-MM-DD --limit 10
scripts/sycm.sh evaluation-list --date YYYY-MM-DD --limit 20 --out eval.json
scripts/sycm.sh reception-list --date YYYY-MM-DD --raw   # 输出原始 JSON
```

### 商品大类 (v0.4+) —— 商品排行 / 商品 360 / 品类 360 / 新品追踪

走的是 sycm 商品板块的**新接口（cc/* 系列，cc-v2 风格）**，与上面的旧 csp 接口参数完全不同：
- 日期参数：`dateRange="YYYY-MM-DD|YYYY-MM-DD"` + `dateType=day|recent7|recent15|recent30`
- response 里字段值常是 `{value, cycleCrc, syncCrc}` 嵌套对象（CLI 已自动提取 `.value` 展示）

| 子命令 | 对应 sycm 页面 | 关键字段 | 备注 |
|---|---|---|---|
| `item-list` | 商品/商品排行 (`/cc/item_rank`) 或 商品 360 (`/cc/item_archives`) | 商品标题、支付金额/买家数/件数/转化率/客单价、访客数、加购件数、收藏人数、平均停留时长、详情页跳出率、搜索引导访客数、成功退款金额（12 项，其余 29 个字段用 `--raw` 看）| 走 `/cc/item/view/top.json`（历史档接口）；旧接口 `/cc/item/portal/itemList.json` 只在网页「实时」档才用，且不认 `indexCode`(实测传多少个都只回 3 个指标)，已弃用 |
| `cate-list` | 商品/品类 360 (`/cc/new_cate_archives`) | cateName、payAmt、itmUv、payRate | 返回的是当日全行业品类数据（含 children 树）|
| `new-product-list` | 商品/新品追踪 → 列表 (`/cc/new_item_analysis`) | 商品、publishNewTime、payAmtNew、shopUvNew | 接 `--cate-id` 限定类目 |
| `new-product-overview` | 商品/新品追踪 → 顶部汇总卡 | newItmCnt、shopUvNew、payAmtNew、addCartCntNew | 不是 list，返回汇总对象 |
| `new-product-trend` | 商品/新品追踪 → 趋势图 | self/industry 两组时序数据 | 建议加 `--raw` 拿全 |

日期能力以实测为准：overview 只确认单日；trend 的单日调用返回截至该日的固定 30 日序列；overview/trend 显式 7/30 日区间会报 1003。list 的 7/30 日调用虽成功，但曾返回完全相同结果，未确认前不要宣传为两个独立窗口。

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

**字段值是嵌套对象，加 `--raw` 才能拿到对比指标**（cycleCrc=环比、syncCrc=同比）。摘要模式只显示 `.value`。

### 单品五件套 (v0.8+) —— 这个款为什么不行

回答「这个款为什么不行、哪个尺码在退、流量从哪来」。全部只读，都走 cc-v2 风格接口。

先用 `item-search` 拿到 `itemId`，其余四个命令都接 `--item-id <商品ID>`；也可以直接用
`--search <货号/标题关键词>` 代替，**命中唯一才继续，命中多个会列出候选并以退出码 1 停下**（不猜）。

| 子命令 | 对应 sycm 页面 | 产出 | 日期口径 |
|---|---|---|---|
| `item-search <关键词>` | 商品 360 搜索框 | 商品ID、货号、价格、库存、标题 | 目录搜索，无日期参数 |
| `item-360` | 商品 360 顶部 | 核心指标（本店值+环比+`cmpt`对比值）+ 销售总览 | 都吃 `--date` |
| `item-sku-list` | 商品 360 / 销售分析 / SKU销售明细 | 各 SKU 组合的加购件数、支付金额/件数/买家数；`--by <属性名>` 时改出按属性聚合表；`--live` 时改出现有库存/售罄率/库存可售天数（与 `--by` 互斥）| 默认吃 `--date`；`--live` 是当前快照，忽略 `--date` |
| `item-flow-source` | 商品 360 / 流量来源 | 来源树（多级）：uv、pv、收藏、加购、支付买家/金额、转化率 | 吃 `--date` |
| `item-refund` | 商品 360 / 退款 | 一条命令三张表：退款原因分布、各 SKU 退款、各属性退款（含属性值） | 吃 `--date`，按**原订单付款时间** |
| `item-profile` | 商品 360 / 客群洞察 / **客群画像** | 买这个款的人是谁：人群标签/年龄/性别/新老客/省/市/品牌偏好/类目偏好/预测消费层级/淘气值 共 10 个维度 | **只认单日**，多日区间会被拒 |
| `item-loss-risk` | 商品 360 / 客群洞察 / **客群细分** | 潜在流失风险：你这个款的客户预测会流向哪些商品（**含友商**），带按店铺汇总 | 人气值**只有单日有**，多日会静默丢掉该列 |
| `item-detail` | 商品 360 / 详情分析 | 核心概况 11 个指标，每个都带**同行均值/同行优秀** + 详情页逐屏（11 个楼层，两级树）看买家看到哪屏走的 | 吃 `--date` |
| `item-price` | 商品 360 / 价格分析 | 本款价格定位（挂牌价 / 实际件单价 / 所属价格带）+ 类目各价格带大盘，**标出本款所在档** | 吃 `--date` |
| `item-title` | 商品 360 / 标题优化 | 标题每个词带来多少搜索访客，**直接点名零引导的死词** + 推荐词（类目/属性/品牌/长尾） | 吃 `--date` |
| `item-bundle` | 商品 360 / 关联搭配 | 买了这个款的人还买了什么：系统推荐 + 卖家自选（未配置时会说明是没配，不是取不到） | 吃 `--date` |
| `item-content` | 商品 360 / 内容分析 | 关联视频/内容带来多少种草点击、粉丝点击、收藏、加购、支付（汇总 + 逐条内容） | **默认近 30 天**，内容效果看单日没意义 |
| `item-service` | 商品 360 / 服务体验 | 售前咨询/售后首次解决率/有效回复/主动评价/问大家声量/成功退款，每项带对比值与环比 | 吃 `--date` |

公共参数：`--item-id` / `--search` / `--date` / `--end-date` / `--limit` / `--page` / `--raw` / `--out`。

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

`--by <属性名>` 不传就出 SKU 组合明细（`skuName` 是"颜色分类:xx;尺码:xx"这种组合值）；传了就改走
按属性聚合的接口，出该属性维度下每个取值的汇总（`attrValue` 列）。属性名取值来自商品自身定义的
属性（常见的是"尺码"“颜色分类”），不写死枚举——服务端不认的属性名会自己报错，不会静默返回空表。

**口径警告（分析前必看）**

- **日期窗口只支持 1 / 7 / 15 / 30 天**。`--date` 与 `--end-date` 的间隔必须恰好是这几个宽度之一，
  其余宽度服务端一律 `code=1003` 拒绝（2026-08-05 实测，cc/flow/csp 三族一致），CLI 会先在本地报错。
  `recentN` 是**相对 `dateRange`** 的，不是相对今天（同日实测：7 天窗返回值等于窗口内七个单日之和）。
- **生意参谋商品板块反复出现同一类接口分裂：日/7天/30天档和「实时」档走的是两个完全不同的
  接口**，只在某一档录到的接口签名不能代表另一档。已踩过三次：`item-sku-list`、`item-360` 的
  销售总览最初侦查时页面停在「实时」档，录成 `/cc/live/...` 系列（写死当天，忽略传入日期），
  已改正为不带 `live/` 的日期口径接口（2026-08-05 用 recent7/recent30 两次真实调用对照过，数值
  不同）；`item-list` 也一样，最初录到的 `/cc/item/portal/itemList.json` 不认 `indexCode`（传多
  少个都只回 3 个指标），页面日期档实际走的是 `/cc/item/view/top.json`，换过去后单次调用能拿到
  41 个字段。**`item-sku-list` 的实时档没有丢，用 `--live` 显式切换**——现有库存 `currentStockCnt`
  / 售罄率 `sellRate` / 库存可售天数 `stockDays` 只有实时接口才有，认日期的接口拿不到这三个字段
  （加了 `indexCode` 也会被静默丢弃），`--live` 和 `--by` 互斥。
- **`item-refund` 是退款事件归属，不是退货率。** 三张表都按原订单付款时间（`refundDateType=pay`）。
  真实退货率要用同一付款批次的支付订单数作分母，CLI 不替你算，也不要自己拿这些数去算。
- **`item-refund` 的「退款原因」表已修好（2026-08-06）。** 它曾长期返回 0 行，真凶是
  `rfdIntervalLevel` 传了猜的 `"ALL"` —— 服务端照收、不报错、静默返空；页面实际传的是 **`99`**。
  现在能正常拿到 8 类原因，且带 `rfdReasonTypeCn`（**内部原因 / 消费者原因**）——先看这一列，
  内部原因才是自己能改的。金额字段是 `itemRfdAmt`，`itemSucRfdAmt` 这个名字在响应里不存在。
- **退款率字段近 7 天还没长完。** 各 SKU 表里的 `payAmtRfdRate` / `ordRfdRate` 是平台自算的支付时间
  口径退款率，实测 T-6 仍在爬升。`--date` 默认昨天正落在禁区里，别用近 7 天的退款率下结论。
- **`item-360` 的 `*Cmpt` 不是同行绝对值。** 实测本店 payAmt / uv 都是三四位数时，对应的
  `*Cmpt` 全落在 0~1 区间，量级完全对不上。具体口径未核实，别当同行对比读。
- **`item-profile` 只认单日**（2026-08-06 实测）。传 `recent7` / `recent30` 服务端照样回
  `code=0`，但 data 恒为空数组——又一次「参数照收、结果静默变空」。CLI 在发请求前就拦掉多日区间。
- **`item-profile` 的三个人群口径里通常只有 `itmUv`（访问人群）有数据 —— 原因是样本量门槛。**
  页面原文：「本店商品人群样本量小于 300 人，不统计客群画像」（2026-08-06 核对）。
  `payByrCnt`（成交人群）与 `appSearchUv`（搜索人群）的人数一般远达不到 300，所以恒空。
  致命的是本接口**只认单日**，没法靠拉长窗口把人数攒过门槛——**这两个画像实际上只有
  单日就能跑到 300+ 的大流量爆款才出得来**。不是缺参数，也不等于该商品没有成交人群。
- **`brand_prefer` 维度有标签没数值**：回得出品牌名，但访客数全 0、占比全空。命令会点明这是
  取不到数，不是「没人偏好这些品牌」。
- **`new_old` 的 `Y`=新客户、`N`=老客户**（2026-08-06 用页面「新老占比」环形图核对）。CLI 显示成
  「新客户(Y)」，中文与原码并存。
- **`item-loss-risk` 的「预测流失人气」只有单日有。** 多日区间时行还在、`customerCnt` 列被服务端
  静默拿掉——是本项目第六次遇到「参数照收、结果悄悄缩水」。命令会显式提示，别把没有数字的表当
  成正常结果读。
- **`item-loss-risk` 的 `crowdType` 目前只核实了 `ptl-loss`。** 页面「流失客户」「潜在客户」那些
  框应该还有别的值，但服务端不吐白名单、前端 39 个 JS bundle 里也搜不到，**没拿到就没写进来**。
- **`item-detail` 的 `rivalAvg`/`rivalGood` 是真的同行对比**（同行均值 / 同行优秀），量级与本店值
  同数量级、可直接比较。这与 `item-360` 那个量级对不上、口径不明的 `*Cmpt` **不是一回事**，别混用。
- **`item-detail` 的 `byrType=all` 是从页面录来的，不能猜。** 服务端对瞎编的 `byrType` / `detailType`
  不报错、静默返回空——猜错会得到一个永远空着还看不出毛病的命令。同类硬编码值还有
  `level1LossStatus=cate-not-pay`、`indexes=itemLossUvIndex`（注意是 `indexes` 不是 `indexCode`）。
- **`item-price` 的挂牌价与实际件单价要一起看。** 实测同一商品挂牌 210.99、实际件单价 158.10，
  差 25%（活动/优惠）。只看其中一个都会把价格定位判断错。
- **`item-price` 的 `tradeGrowthRate` 是字符串区间**（如「35190% ~ 35200%」），服务端已格式化，
  不是数字，别拿去做算术。`SupplyRatioIndex` 大写 S 开头是服务端原样，不是笔误。
- **`item-title` 的零引导词是「缺列」不是 0。** 没带来搜索的词，行里根本没有 `guideSeUv` 键。
  CLI 打 `-` 不打 0 —— 0 会被读成「有统计只是量少」，实际是这个词一次搜索都没引来，是标题里的
  死字。命令会直接把死词数和词表点出来，这是本模块唯一能直接执行的结论。
- **`item-content` 的商品 ID 走 `keyword` 参数，不是 `itemId`。** 传成 itemId 服务端只回
  「请求参数非法」，看报错想不到是这个。另外还要 `accountRole=guanghe-all` 和 `indexCode`。
  返回里 `children` 包了一层 `{data:[...]}` 信封才是逐条内容，直接当行渲染会出一整行横杠。
- **`item-service` 的 `needCycleCrc` 必须放在 `extMap` 里**，不是独立 query 参数。当独立参数传时
  服务端不报错、直接回空 dict —— 曾据此误判「这个 domainCode 取不到数」。
- **单品诊断模块没有单独命令**：它只有两个接口，`/cc/diagnose/coreIndex.json` 已经在 `item-360`
  里，`/cc/diagnose/getIndexAttention.json` 是「关注指标」的用户配置（本店未配，返回 null），
  不是数据。所以看单品诊断直接用 `item-360`。
- **看 `item-loss-risk` 要先看按店铺汇总那行。** 客户流向自家其它款（正常，选品重叠）和流向友商
  （要紧张）是两件完全不同的事，混在一张 50 行的表里看不出来。

### 页面级模块（阶段3，店铺级，不带 `--item-id`）

| 子命令 | 对应 sycm 页面 | 产出 | 日期口径 |
|---|---|---|---|
| `spu-list` | 商品/商品集分析 | 各商品集的支付金额/件数/件单价/含商品数 | **只认单日**（多日回 `param check error`，指不到日期上，CLI 本地先拦） |
| `item-relate` | 商品/连带分析 | 主商品 + 它的关联商品（关联支付人数/购买率/访客数） | 吃 `--date`，默认 `device=2` |
| `video-list` | 商品/素材分析/视频分析 | 各商品视频的曝光/点击/曝光点击率/有效播放/完播率/当日成交 | 吃 `--date` |
| `macro-monitor` | 商品/宏观监控 | 全店商品实时大盘 12 项（支付/访客/加购/收藏/转化率），每项带环比 | **实时快照，`--date` 不生效** |
| `problem-alarm` | 商品/重点商品/问题预警（隐藏路由） | 质量问题/缺货/高价限流商品计数 + 缺货明细 | 实时 |
| `interval-analysis` | 商品/宏观监控/商品区间分析 | 动销商品按价格带/支付件数/支付金额切开，各段商品数与占比（`--by` 切视角） | 吃 `--date` |

```bash
scripts/sycm.sh spu-list    --date YYYY-MM-DD
scripts/sycm.sh item-relate --date 起始 --end-date 结束 --limit 5
scripts/sycm.sh video-list  --date 起始 --end-date 结束 --limit 20
scripts/sycm.sh macro-monitor   # 实时，不用传日期
scripts/sycm.sh problem-alarm   # 实时，不用传日期
scripts/sycm.sh interval-analysis --date YYYY-MM-DD --by ordPqt   # 你的货集中在哪个价位
```

这三个的参数都是从页面请求录来的，有几个反直觉的点（都已固定在代码里）：
- 商品集 `spuType=**def**` 不是 `all`
- 连带分析关联侧字段名带 `relate` 前缀（`relatePayByrCnt`），排序参数是
  `mainOrderBy` + `relateOrderBy` + `relateOrder`，**没有** `order`/`orderBy`；
  只传 `mainOrderBy` 会 `code=600007` 且**消息为空**
- 视频分析一次返回上千条（本店实测 1441），命令会报总数，别把一页当全部
- **`problem-alarm` 的「质量问题商品」只有计数、拿不到明细**：页面上点进去是「请在新打开的
  页面中查看」，明细在千牛体检中心，不在 sycm。命令会打这句，别当成 CLI 少做了一块。
  接口路径里服务端把 problem 拼成了 `prolem`，不是笔误。
- **宏观监控是实时快照，`--date` 完全不生效**：实测 day / recent7 / recent30 三档返回的
  `payAmt` 一模一样。接口路径里服务端把 macro 拼成了 `marcro`，不是笔误。

### 首页大盘 (v0.5+) —— 数据概览 / 增长因子（老板每天看的那块）

sycm **首页 `/portal/home.htm`** 顶部那块官方口径大盘，独立的 `/portal/...` 只读 GET，返回 `self`(本店)/`rivalAvg`(同行平均)/`rivalGood`(同行优秀) 三档对标。均接 `--date YYYY-MM-DD --raw --out file`。

| 子命令 | 对应板块 | 关键字段 |
|---|---|---|
| `home-overview` | 首页/数据概览（按日） | payAmt(支付金额)、netPaymentAmount(净支付)、uv(访客)、payByrCnt(支付买家)、payRate(转化率)、rfdSucAmt(退款额)、payAmtRfdRate(金额退款率)、cartByrCnt(加购)、buyAmtRatio(复购占比) |
| `home-table` | 首页/数据概览「表格」视图（多日并排） | 支付/意向/履约售后/推广 4 组完整 32 项 + 每格较上一周期，就是页面点「表格」那张多天对比表 |
| `home-trend` | 首页/数据概览趋势（按日固定窗口） | 同上字段的时序数组 |
| `grow-factor` | 首页/增长因子 | newPortalAdPayAmt(广告引导成交)、portalLivePayAmt(直播)、newItmPayAmt(新品)、mbrPayAmt(会员)、totalPromoSpend、tROI |

```bash
scripts/sycm.sh home-overview --date YYYY-MM-DD          # 昨天的支付/访客/转化/退款率/加购
scripts/sycm.sh home-table    --date 起始 --end-date 结束  # 多日并排大表(默认最近6天)，含较上一周期
scripts/sycm.sh grow-factor   --date YYYY-MM-DD           # 广告引导/直播/新品/会员各贡献多少成交
scripts/sycm.sh refund-origin-analysis --date YYYY-MM-DD  # 该日完结退款来自哪些付款日/退款场景
scripts/sycm.sh refund-all-list --date YYYY-MM-DD --by case-end --raw  # 逐笔含订单号和原付款时间
scripts/sycm.sh home-overview --date YYYY-MM-DD --raw     # 拿全 self/rivalAvg/rivalGood + cycleCrc 环比
```

指标值是 `{value, cycleCrc}` 结构，摘要模式显示值，`--raw` 拿环比。**用"日"口径取稳定汇总，别用实时(实时数据盘中会跳)。**

`home-table` 已收**页面「数据概览」完整 32 项**（支付10/意向7/履约售后10/推广5），中文名照抄页面、字段码用「较上一周期」百分比做唯一键反查锁定（2026-07-18 对全展开截图逐格核对，全中）。默认显示较上一周期，`--no-crc` 关掉；`--raw` 出每日全 62 字段 JSON。

易错字段码对照（都踩过坑/靠 crc 反查才定的，别再猜）：
- 推广费：关键词=`p4pExpendAmt` / 精准人群=**`cubeAmt`**(非 zzExpendAmt) / 智能场景=`feedCharge` / 全站=`adStrategyAmt` / 淘宝客=`tkExpendAmt`
- 退款：签收退款率=**`realPayrealRfdRate`**(≈个位数%，非 `sucRefundRate`≈65%) / 金额退款率=`payAmtRfdRate` / 订单退款率=`ordRfdRate` / 退款处理时长(天)=`rfdFinshDur`
- 老客：复购金额=`rePurchasePayAmount`(=olderPayAmt 同值) / 复购人数=`payOldByrCnt`(=hasPurchasedUbyCnt 同值) / 复购率=`hasPurchaseUbyCntRate`
- 其他：客单价=`payPct`(=支付金额/支付买家数) / 支付子订单数=`subPayOrdSubCnt` / 平均停留时长=`stayTime` / 旺旺人工响应时长(秒)=`wwReplyManualAvgTimeLen` / 平台判责率=`slrRespRate` / 物流到货时长(小时)=`avgSignTimeHh` / 24小时揽收及时率=`gotInTime24hRate` / 咨询率=`consultRate`

**为什么靠 crc 反查而不是扒前端字典**：接口(overview / getTableData)只回英文字段码+数值，中文名在首页子应用 `op-home`(诊出版本 2.1.54)前端里，其 CDN 包名由 diamond 运行时拼、猜不到(试了 8 种 aligenius/* 全 404)，Claude 自己浏览器没登录跑不了那段配置。最终靠用户发的完整截图 + 「较上一周期」百分比唯一键，把 32 个中文名逐个锁到字段码。

### 多店铺登录态（v0.5+）—— 一台机器管多个店

默认用浏览器里实时的登录（单店）。要管多个店，把每个店的登录态存成命名 profile（**仅 Mac**：Windows 读不到 Chrome 的登录，换店就在 Chrome 里换账号登录）：

```bash
# 1. 在 Chrome 登录 A 店的 sycm，存下来
scripts/sycm.sh export-profile 示例主店
# 2. 之后任何命令加 --store 切换（放在子命令前）
scripts/sycm.sh --store 示例主店 home-overview --date YYYY-MM-DD
scripts/sycm.sh profiles                    # 看已存哪些店 + 新鲜度
```

- profile 存在 `~/.taobao-cli/profiles/`(0600 权限，含长效登录凭据，**勿提交 git**)。
- **qianniu-cli 读同一目录，一份 profile 两个工具通用**（都用 taobao.com 登录）。
- 长效 cookie 失效（几周）后，重新在浏览器登录该店再 `export-profile` 一次即可。

### Excel 一键下载（v0.3+）—— 商品数据 / 评价 / 销售等导出

任何上面的 list preset 都能用 `excel` 子命令**一行下载 Excel 文件**到本地（默认 `~/Downloads/sycm-exports/`）。
内部走 sycm 自带的"申请导出 → 排队生成 → 拿 OSS 临时链接 → 自动下"四步，全自动。

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

OSS 临时链接 1 小时有效；过期需重新跑命令。

### 通用接口探测（高级）

```bash
scripts/sycm.sh api <path> --param key=val --param key2=val2
```

用来探索还没封装为子命令的接口。例如：
```bash
scripts/sycm.sh api ww/consultation/detail/list \
  -p startDate=YYYYMMDD -p endDate=YYYYMMDD -p dateType=day \
  -p dateRange=day -p orderBy=startTime -p pageNo=1 -p pageSize=10
```

## 安全护栏的环境变量

| 变量 | 作用 |
|---|---|
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

**软建议**（不停止，只在 stderr 提示）：
- 请求间隔随机 1.8 ~ 3.5 秒（接近人工）
- 累计 200 次请求时打一次提醒（风控按"短时高频"判定，不按"总量"，所以 200 不是上限只是个提示点）
- 如需硬性兜底（防脚本跑飞），设 `SYCM_REQUEST_LIMIT=N`

作者自己的店每天都在用，正常范围内的查询基本没遇到过风控；淘宝的风控通常只是弹一个验证提醒。**触发 `RiskTriggered` 时停下，请用户在浏览器里打开生意参谋过一下验证，再继续**，不要连着重试。

## AI 代理调用示例

用户："帮我看下昨天客服都聊了什么"：

```bash
DATE=$(date -v-1d +%Y-%m-%d)
scripts/sycm.sh fetch-recent --date $DATE --limit 10 --out /tmp/sycm-$DATE.json

# 然后读 /tmp/sycm-$DATE.json，逐个会话做分析
```

用户："分析下今天客服的尺码推荐是否准确"：

1. 拉今天的 fetch-recent
2. 过滤 messages 里包含"穿什么码 / 身高 / 体重 / XL / L 码"等关键词的会话
3. 分析每个会话客服推荐的尺码合理性，输出报告

## 字段字典与发现方法论（v0.6+，AI 取数主力走这里）

**主力不是背命令，是查字典。** `tb/platforms/sycm/fields.json` 是机器可读字段字典，每条 = `字段码 → {cn 中文名, scope 适用命令, fmt 格式, status, note 口径备注}`。数据概览 62 个原始字段全部入册（32 个已破译 `verified` + 30 个中文名待破译 `candidate`）。

**标准取数动线：**
1. **先读 `fields.json`** 找字段码 + 它的 `note`（口径警告）
2. **用 `--fields` 选列取数**：`home-table --fields payAmt,uv,payRate --date 起 --end-date 止`；想要 62 个全字段用 `--all-fields`
3. 预设命令（`home-overview`/`home-table` 等）只是常用查询的快捷方式，不是唯一入口

`status: candidate` 的字段中文名尚未破译（`cn` 暂等于字段码），用前先验证；`note` 里的口径警告**必须遵守**（见下方坑规矩）。

### 坑规矩（口径警告，写数前必看）

- **退款率（支付时间口径，`payAmtRfdRate`/`ordRfdRate`/`payShopRfdAmt`）**：近 7 天数值仍在爬升（实测 T-6 仍未长完），**分析禁止用近 7 天下结论**。看真实退货率要等旧日期结算，或用店主自己的现金回收账本。
- **签收退款率（`realPayrealRfdRate`）**：**T-3 才出值，两周以上才稳定**，近几天显示 `-` 是正常的。

> 配套工具：**alimama-cli**（万相台广告投放数据）同样有 `fields.json` 字典，店铺体检 + 广告复盘两个一起用。

---

## 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `doctor` 报"未找到淘宝登录态" | Chrome 没登录 sycm 或被另一个 Chrome 锁定 cookie 文件 | 打开 Chrome 登录 sycm.taobao.com 一次；登录态在别的 Chrome 身份时设 `SYCM_CHROME_PROFILE="Profile 1"` |
| `list` 返回 0 条 | 漏传 `orderBy=startTime` 参数 | CLI 已内置，正常情况不会遇到 |
| `RiskTriggered: 滑块` | sycm 弹了验证 | 停下，请用户在浏览器里打开生意参谋过一下验证，再继续 |
| HTTP 5810 | session 超时 | 重新打开 Chrome 登录 sycm |
| 「没有连上浏览器插件」 | 插件没装、被停用，或 Chrome 没开 | 照 `extension/README.md` 装好；插件每 30 秒检查一次，等一会儿再试 |
| 插件「太旧」或「文件夹不见了」 | 装的是旧版，或当初加载的文件夹被删了 | `chrome://extensions` 移除旧的取数桥，再加载本目录的 `extension/unpacked` |
| Windows 报 `AppData\Roaming\uv\python: 拒绝访问` | AI 沙箱只允许访问工作区 | 运行 `scripts\sycm.cmd doctor`；Python、依赖和运行数据都放在本目录的 `.runtime/` 里 |

## 文件清单

- `scripts/sycm.sh` / `scripts/sycm.cmd` — 入口（Mac / Windows）
- `tb/platforms/sycm/` — 生意参谋的命令（`cli.py`）、商品板块（`item.py`）、字段字典（`fields.json`）
- `tb/core/` — 共用取数底座：插件桥、登录、请求和护栏
- `extension/unpacked` — 取数桥插件；`extension/README.md` 是安装说明
- `references/analysis-workflows.md` — 分析模块的规则
- `requirements.txt` — Python 依赖（browser-cookie3, curl-cffi, websocket-client）

## 局限性

- 只覆盖了"旺旺咨询明细"（接待明细页）。其他 180+ 接口待按需扩展
- 详情接口每页最多 10 条消息，CLI 自动翻页处理
- 列表 `pageSize` 实测最大约 20，过大会被服务端截断
- Mac 不装插件时读 Chrome Default 资料的 cookie，登录在别的资料时设 `SYCM_CHROME_PROFILE="Profile 1"`；Windows 只走插件
