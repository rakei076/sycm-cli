---
name: shopdata
version: "1.6.2"
description: 店铺数据全家桶是一套读取淘宝、天猫店铺数据的工具集，包含生意参谋、达摩盘、千牛、万相台和竞品评价五个工具，借用本机 Chrome 中已登录的后台读取自家店铺数据。可完成日检、周复盘、单品诊断报告（七页网页、45 天量率速方案和执行跟踪表）、同店对标、竞品对比、人群资产体检、人群画像、评价巡检、退款售后、广告报表和竞品评价洞察。全部为只读操作。触发场景：用户提到生意参谋 / sycm / 店铺数据 / 日检 / 周复盘 / 单品诊断 / 这个款为什么卖不动 / 增长方案 / 测款 / 退货归因 / 客服质检 / 达摩盘 / dmp / 人群资产 / 人群画像 / 竞品对比 / 竞品分析 / 同店对标 / 市场机会 / 千牛 / 评价 / 差评 / 退款 / 售后 / 待发货 / 万相台 / 阿里妈妈 / 广告 / 推广 / ROI / 关键词推广 / 人群推广 / 全站推广 / 竞品评价 / 问大家 / 买家秀 / 消费者声音。
---

# 店铺数据全家桶 shopdata

shopdata 是一套读取店铺数据的工具集，包含生意参谋、达摩盘、千牛、万相台和竞品评价五个工具。五个工具共用一个 Python 环境、一个取数桥插件和一个 MCP 服务（shopdata）。

**重要**：下文所有路径都从本包的根目录算起。

## 选择工具

| 任务 | 工具 | 命令 | 完整说明（使用前先读完） |
|---|---|---|---|
| 店铺大盘、商品、交易、退款、客服；日检、周复盘、测款、退货归因、广告 ROI、客服质检；单品诊断报告 | 生意参谋 | `scripts/sycm.sh` | `tools/sycm.md` |
| 人群资产体检、人群画像、竞品对比、同店对标报告（达摩盘口径）、单品洞察、竞争店铺、市场榜单 | 达摩盘 | `scripts/dmp.sh` | `tools/dmp.md` |
| 评价巡检、差评、退款售后、待发货、商品、物流履约、流量诊断 | 千牛 | `scripts/qianniu.sh` | `tools/qianniu.md` |
| 广告报表、在投计划、单元开关状态、场景大盘、账户余额 | 万相台 | `scripts/alimama.sh` | `tools/alimama.md` |
| 竞品的评价、问大家和买家秀，痛点归因报告（需要买家账号） | 竞品评价 | `scripts/voc.sh` | `tools/voc.md` |

全部功能和对应命令见 `功能清单.md`。在 Windows 上，把 `scripts/<工具>.sh` 换成 `scripts\<工具>.cmd`。已接入 MCP（shopdata）时，使用其中的 doctor、commands、run、guide 工具，`platform` 填 sycm、dmp、qianniu、alimama 或 voc。

## 使用规则

- **先读工具说明**：每个工具的安全规则、数据口径和报错处理都在 `tools/<工具>.md`。第一次使用某个工具，或要生成整份报告之前，先读完对应的说明再操作。
- **自定义分析要求优先**：用户团队自己的报告要求（月报、周报、汇报格式等）保存在「分析要求」文件夹（运行 `scripts/tb.sh guide --where` 查看位置；Mac 为 `~/.taobao-cli/分析要求/`，Windows 为 `%LOCALAPPDATA%\taobao-cli\分析要求\`）。生成报告前，先用 guide 工具（终端：`scripts/tb.sh guide`）查看是否有对应的自定义要求：有则按其执行，没有再使用通用分析方法；同名时以自定义要求为准。用户需要新增或修改要求时，将其写成 .md 文件保存到该文件夹，不要修改工具内的 `references/` 和本文件，否则升级时会被覆盖。
- **先读分析方法**：生成整份报告之前，先读对应的分析方法（MCP 中对应 guide 工具）：
  - 生意参谋日检、周复盘、测款、退货归因、广告 ROI、客服质检：`references/analysis-workflows.md`
  - 单品诊断报告：`references/item-report-guide.md`
  - 达摩盘人群资产体检：`references/analysis-guide.md`；人群画像：`references/portrait-guide.md`；竞品对比：`references/compete-item-guide.md`；竞品投放计划与预算：`references/rival-plan-guide.md`；竞品分析报告：`references/compete-report-guide.md`
- **常见问题照文档答**：用户问会不会被封号、稳不稳定、怎么连接、支持哪些 AI 助手、在 Codex 里提示站点限制、数据安不安全、怎么反馈问题时，先读 `常见问题.md`（MCP 中用 guide 工具查看主题「常见问题」），照着回答，不要自己猜。
- **先检查环境**：出现问题时，先运行 `scripts/<工具>.sh doctor`。取数桥插件的安装和排错见 `extension/README.md`。
- **取数方式**：Mac 不需要插件，工具直接读取 Chrome 中的登录状态；读不到登录且装了「taobao-cli 取数桥」插件时，自动改用插件。Windows 必须安装插件。无论哪个系统，取数都只用本工具的命令：不要用 AI 助手自带的浏览器（例如 Codex 内置浏览器）打开后台，也不要另写脚本抓取。竞品评价例外，两个系统都只通过插件取数。
- **工具模块**：一共五个工具，包里可能只装了其中几个，只有打开的才能用（`scripts/tb.sh modules` 查看）。用户要的数据属于没打开的工具时，告诉他可以打开（没装的会自动下载），征得同意后用 MCP 的 modules 工具（终端：`scripts/tb.sh modules enable <模块>`）打开，再提醒他完全退出 AI 助手重开。下载失败时把提示里的手动下载方法转告用户。和用户的问题无关时不要推荐。
- **多个账号**：用户要求读取某个店铺或账号的数据时，先用 account 工具（action=list）找到账号名称，再在读取时指定账号：MCP 中填写 run 的 account 参数，终端使用 `scripts/tb.sh --account <账号名称> <平台> <命令>`。工具会在同一条命令中完成切换和读取。不要先调用 use 再读取：两步之间账号可能被其他调用切换，导致读取到其他店铺的数据。浏览器同一时间只能登录一个账号，不要同时发起不同账号的读取。命令提示账号发生变化、店铺不一致或由两个取数桥插件处理时，本次数据已作废：不要使用，按提示处理后重新运行。一个登录账号可以查看多个店铺时，生意参谋可能返回其他店铺的数据，工具会自动重试，仍不一致时报错并给出店铺编号；用户确认要查看其他店铺时，在 run 中填写 shop 参数（终端：`--shop <店铺编号>`）。切换后提示账号已过期时，请用户点击浏览器中的插件图标重新登录，不要代替用户登录。
- **反馈问题**：用户反馈读取出错或数据不符时，使用 MCP 的 log 工具：action=list 查看最近几次运行的账号、店铺编号和错误，action=export 将日志打包到桌面（终端：`scripts/tb.sh log export`），并请用户将生成的 zip 文件发送给开发者。
- **Codex 沙箱**：在 Codex 中一律用 MCP 工具取数，不要在终端里运行脚本——Codex 的沙箱默认不让联网、不让开本机端口，脚本会报「依赖下载失败」或「当前环境不允许在本机开端口」。MCP 还没接入时，请用户在自己打开的终端里运行 `mcp install`，再完全退出并重开 Codex。不要把「改成完全访问」当作解决办法（在 Windows 上有时不生效），不要自己另找运行环境，也不要改用你自带的浏览器取数。

## 组合用法

### 单品诊断

1. **取达摩盘竞品对比**：运行 `scripts/dmp.sh compete-item --item <本品ID> --days 30 --out reports/竞品对比.json`。不写 `--rival` 时，使用达摩盘推荐的同类成功商品；本品必须是本店商品。
2. **取生意参谋数据**：运行 `scripts/sycm.sh item-report --item-id <本品ID> --compete reports/竞品对比.json`。默认取最近 14 天，前 7 天和后 7 天对比，约需两三分钟。
3. **补充证据**：以下数据能取到的都取，结果写进归因的 `evidence` 和 `gaps`。
   - **千牛差评原文**：`scripts/qianniu.sh review-list --product-id <本品ID> --days 30`（追评加 `--feed-type append`）。
   - **万相台投放情况**：`scripts/alimama.sh promo-units --item <本品ID>` 查看商品在哪些计划中、是否开启；`scripts/alimama.sh report-item --date <开始> --end-date <结束> --search <本品ID>` 查看花费、ROI、点击率和转化率。
   - **竞品买家关注点**：使用竞品评价工具（见 `tools/voc.md`）。该工具需要买家账号且运行时间较长，使用前先征得用户同意。
4. **生成报告**：按 `references/item-report-guide.md` 写分析，运行 `scripts/sycm.sh item-report --analysis <分析文件>` 生成七页网页和执行跟踪表；需要发给他人时加 `--mask`。
5. **每周复盘**：方案开始后，每周运行 `scripts/sycm.sh item-report --track --analysis <分析文件>`。

### 同店对标

- **访客口径**：与生意参谋一致，使用单品诊断报告中的「同店对标」页。
- **单独一页对标表**：运行 `scripts/dmp.sh item-bench --item <本品ID>`。该报告使用达摩盘口径：浏览量；转化率 = 成交笔数 ÷ 浏览量，低于生意参谋的转化率。向用户说明这一点。

### 竞品分析

- **本品对竞品**：运行 `scripts/dmp.sh compete-item --item <本品ID> --rival <竞品ID>`，可查看经营、推广、流量结构、投资结构、客群、平台诊断、同类成功商品和打爆路径。竞品数据只提供区间。
- **竞品分析报告（网页）**：运行 `scripts/dmp.sh compete-report --item <本品ID> --rival <竞品ID>,…` 取数，按 `references/compete-report-guide.md` 写结论，再用 `--analysis` 出网页。版式固定，不要自己生成网页。
- **竞品投放计划和预算**：运行 `scripts/dmp.sh rival-plan --item <本品ID> --rival <竞品ID>`，可查看竞品开了哪些推广场景和方案、各占多少花费，并估算期间和日均预算。预算是估算值，只看量级；分析方法见 `references/rival-plan-guide.md`。
- **竞争店铺**：`scripts/dmp.sh get market.compete.detection` 查看与本店争夺同一批人群的店铺；`market.compete.monitor` 查看已关注竞店近 7 天的数据。
- **市场**：`market.rank.price-range`、`market.rank.properties`、`market.opportunity.items` 分别查看类目价格带、热门属性和市场机会商品。
- **竞品买家评价**：使用竞品评价工具，给一个关键词，采集竞品的评价、问大家和买家秀，生成痛点报告（见 `tools/voc.md`）。
- **客户流失去向**：`scripts/sycm.sh item-loss-risk` 查看本品的客户预计会流向哪些商品，包括其他店铺的商品。

### 店铺体检

- **经营**：生意参谋日检、周复盘（`references/analysis-workflows.md`）。
- **人群**：运行 `scripts/dmp.sh report` 生成人群资产体检，判断是收割过度还是拉新不足。
- **售后和口碑**：千牛评价巡检、退款、待发货。
- **投放**：运行 `scripts/alimama.sh charge-summary`、`report-campaign`，并结合生意参谋的广告 ROI 模块。

## 安全规则

- **只读**：全部为只读操作，不会修改店铺。
- **遇到验证立即停止**：出现滑块、验证码或「操作过于频繁」时，立即停止并告知用户，不要重试，也不要尝试绕过。
- **数据留在本机**：真实店铺数据只保存在本机，不要发送到其他地方。
