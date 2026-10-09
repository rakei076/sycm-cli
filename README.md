# 生意参谋 sycm-cli

![License](https://img.shields.io/github/license/rakei076/sycm-cli)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Stars](https://img.shields.io/github/stars/rakei076/sycm-cli?style=social)
![Last Commit](https://img.shields.io/github/last-commit/rakei076/sycm-cli)

sycm-cli 是一款读取生意参谋店铺数据的工具，可帮助你和 AI 助手查看首页大盘、商品、交易退款和客服对话等经营数据，并完成日检、周复盘、单品诊断、测款和退货归因。工具在你的电脑上运行，使用你在 Chrome 中已登录的生意参谋账号。

> 本 Skill 作者：Rakel · 个人网站：https://rakel.top

## 使用须知

- **仅读取本店数据**：工具使用你的登录状态，只能读取当前登录店铺的数据。
- **只读访问**：工具不会下单、改价、回复或删除任何内容。

## 安装

安装约需 5 分钟，只需进行一次。

**在 Codex 里使用**：请用 MCP 接入（见下面「接入 AI 助手」一步），让 Codex 通过 MCP 取数，不要让它在终端里直接运行脚本。Codex 的沙箱默认不让联网、也不让在本机开端口，在终端里跑脚本，第一次装依赖和连插件都会被拦下；MCP 服务由 Codex 单独启动，不受这个限制。接入命令（`mcp install`）请在你自己打开的终端里运行一次（Windows 用 PowerShell 或命令提示符），然后完全退出 Codex 再打开。Codex 的「完全访问」在 Windows 上有时不生效，不要依赖它。

1. **安装 Python 运行环境**：推荐安装 [uv](https://docs.astral.sh/uv/)。Mac 运行 `brew install uv`；Windows 在 PowerShell 中运行 `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`，然后重新打开终端。你也可以直接使用 Python 3.10 及以上版本。
2. **安装取数桥插件（只有 Windows 需要）**：
   - **Mac**：跳过这一步。工具直接读取你在 Chrome 中的登录状态，Chrome 里登录着就能用。
   - **Windows**：必须安装。Windows 版 Chrome 会加密登录状态，工具读不到，只能通过「taobao-cli 取数桥」插件取数。安装方法见 [extension/README.md](extension/README.md)，约需 2 分钟。插件由各店铺数据工具共用，为其他工具装过的不用再装。
3. **登录生意参谋**：在 Chrome 中打开 <https://sycm.taobao.com> 并登录，保持登录状态。
4. **检查安装**：运行 `scripts/sycm.sh doctor`（Windows：`scripts\sycm.cmd doctor`）。看到 `probe = ok` 即表示工具安装完成。
5. **接入 AI 助手**：运行 `scripts/sycm.sh mcp install`（Windows：`scripts\sycm.cmd mcp install`），通过 MCP 把本工具接入电脑上的 Claude Code、Codex、Cursor 和 Claude Desktop。MCP 是让 AI 助手直接调用本工具的接口。重新打开 AI 客户端，看到「shopdata-sycm」的工具（doctor、commands、run、guide）即表示接入完成。之后可以直接对 AI 助手说「看下昨天店铺怎么样」。

**提示**：你也可以把整个文件夹放进 AI 助手的 Skill 目录（Claude Code 为 `~/.claude/skills/sycm-cli`）来使用本工具。

### Mac 和 Windows 的区别

| | Mac | Windows |
|---|---|---|
| 取数桥插件 | 不需要 | 必须安装 |
| 怎么读取数据 | 直接读取 Chrome 中的登录状态。读不到时（例如刚重启过 Chrome），如果装了插件，自动改用插件 | 只通过插件，在你已登录的 Chrome 中读取 |
| 多店铺登录存档 | 支持 | 不支持，换店铺请在 Chrome 中换账号登录 |
| 命令 | `scripts/sycm.sh` | `scripts\sycm.cmd` |

两个系统都一样：在 Chrome 中登录要用的后台。工具读不到 AI 助手自带浏览器（例如 Codex 内置浏览器）里的登录，取数时也不要让 AI 助手改用它。

## 功能

| 场景 | 说明 |
|---|---|
| 标准报表 | 完整列出当前可以读取的全部数据，不遗漏任何一张报表 |
| 日检 | 检查昨天是否有需要立即处理的异常 |
| 周复盘 | 分析本周的变化来自流量、转化还是客单价 |
| 单品诊断报告 | 生成七页网页报告，分析商品销售不佳的原因，内容包括定性、两条硬伤、首末对比、趋势、同店对标和下滑归因，并给出 45 天「量·率·速」方案、目标模拟器和执行跟踪表；方案开始后，每周可用一条命令复盘。诊断时会查阅搜索词、详情页、SKU、退款、人群和达摩盘的同类爆款打法作为证据。网页可以离线打开、发给他人，支持生成强脱敏版 |
| 测款 | 判断哪些新品值得继续推广 |
| 退货归因 | 找出退货较多的商品及其退货原因 |
| 客服质检 | 检查客服是否真正回答了买家的问题 |

每次分析都会注明数据日期、所用命令和字段口径，并把建议收敛为一到两个可以立即执行的动作。分析规则见 [references/analysis-workflows.md](references/analysis-workflows.md)，单品诊断报告的生成方法见 [references/item-report-guide.md](references/item-report-guide.md)。

## 命令参考

请在本文件夹中运行命令。Windows 请把 `scripts/sycm.sh` 换成 `scripts\sycm.cmd`。常用参数如下：

- **`--help`**：查看命令的参数说明。
- **`--raw`**：输出原始 JSON。
- **`--out 文件`**：把结果写入文件。

| 场景 | 命令 |
|---|---|
| 首页大盘 | `home-overview` `home-trend` `home-table` `grow-factor` |
| 首页客单 | `order-overview` `order-trend` `order-distribution` `order-recommend` |
| 商品排行与 360 | `item-list` `item-search` `item-360` `cate-list` `spu-list` `interval-analysis` |
| 单品诊断报告 | `item-report`：先取数，再由 AI 助手写分析，最后用 `--analysis` 生成网页；`--mask` 生成脱敏版，`--track` 用于每周复盘 |
| 单品细看 | `item-sku-list` `item-flow-source` `item-profile` `item-detail` `item-price` `item-title` `item-bundle` `item-relate` `item-content` `item-service` `item-loss-risk` `video-list` |
| 全店监控 | `macro-monitor` `problem-alarm` |
| 新品 | `new-product-list` `new-product-overview` `new-product-trend` |
| 交易与退款 | `sale-shop-list` `sale-item-list` `refund-item-list` `refund-all-list` `refund-origin-analysis` `item-refund` |
| 客服 | `fetch-recent` `list` `detail` `reception-list` `sale-cs-list` `inquiry-loss-list` `slow-rsps-list` `evaluation-list` |
| 直播与预热 | `live-guide-overview` `live-guide-trend` `preheating-metrics` |
| 导出 Excel | `excel` `excel-tasks` |
| 工具 | `doctor` `menu` `api` `export-profile` `profiles` |

字段的中文名和口径统一取自 `tb/platforms/sycm/fields.json`。字典中没有的字段会原样输出字段码，不推测中文名。

### 管理多个店铺

此功能仅支持 Mac。在 Chrome 中登录某个店铺后，可以把该店铺的登录状态保存下来，之后用 `--store` 指定店铺：

```bash
scripts/sycm.sh export-profile A店      # 在 Chrome 登录 A 店后，把登录存下来
scripts/sycm.sh profiles                # 看存了哪些
scripts/sycm.sh --store A店 home-overview
```

**重要**：保存的登录状态位于本机用户目录的 `.taobao-cli/profiles/` 中，等同于账号密码，请勿复制给他人。

**注意**：Windows 无法读取 Chrome 的登录状态，因此不能保存登录状态。如需切换店铺，请在 Chrome 中退出当前店铺，再登录另一个店铺。

## 安全与风控

作者的店铺每天都在使用本工具。在正常范围内查询时，基本没有遇到过风控；即使触发，淘宝通常也只会弹出验证提醒，在浏览器中完成验证即可。

| 项目 | 说明 |
|---|---|
| 请求间隔 | 每两次请求之间随机等待 1.8～3.5 秒 |
| 请求数提醒 | 单次运行达到 200 个请求时提醒一次，不会停止；如需硬上限，可设置 `SYCM_REQUEST_LIMIT` |
| 风控词 | 返回内容中出现「滑块 / 验证码 / 操作过于频繁 / 请重新登录 / 异常请求 / 风控」时立即停止 |
| 写操作 | 名称像写操作的接口一律拒绝调用 |

## 常见问题

| 现象 | 处理方法 |
|---|---|
| 提示没有登录、登录已失效（退出码 2） | 在 Chrome 中打开 sycm.taobao.com 重新登录，然后再次运行命令 |
| 提示「没有连上浏览器插件」 | 请确认 Chrome 和插件均已开启。插件每 30 秒检查一次，请稍候再试。详见 [extension/README.md](extension/README.md) |
| 提示插件「太旧」或「文件夹不见了」 | 在 `chrome://extensions` 中移除旧的取数桥插件，再加载本工具自带的 `extension/unpacked` |
| 提示触发风控（退出码 3） | 工具会先停止运行。请在浏览器中正常打开生意参谋，按提示完成验证，然后再次运行 |
| 返回 0 条，但确定有数据 | 请检查日期。很多命令默认查询昨天的数据 |

## 相关工具

同一作者还提供万相台、千牛、达摩盘、1688 订单统计、竞品评价洞察、广告诊断报告等店铺数据工具。这些工具共用同一个取数桥插件，安装一次即可。

介绍和获取方式：<https://rakel.top/tools/>

## 协议

MIT。仅供店铺经营者查询自家数据，请遵守平台规则。


## 联系作者

有想法、有需求，欢迎加微信找我，并注明来意。想要帮你装好、按你的需求定制，或者想用千牛、达摩盘等更多工具，也可以直接问。

- 微信：扫下方二维码加好友
- X / Twitter：[@Rakel076](https://x.com/Rakel076)

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
