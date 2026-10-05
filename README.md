# 生意参谋 sycm-cli

![License](https://img.shields.io/github/license/rakei076/sycm-cli)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Stars](https://img.shields.io/github/stars/rakei076/sycm-cli?style=social)
![Last Commit](https://img.shields.io/github/last-commit/rakei076/sycm-cli)

> 本 Skill 作者：Rakel · 个人网站：https://rakel.top

让你的 AI 直接读自家店铺的生意参谋数据：首页大盘、商品、交易退款、客服对话，做日检、周复盘、测款和退货归因。全部只读，在你自己的电脑上运行，用你浏览器里已经登录的账号。

## 两条规矩

- **只查你自己的店。** 用的是你自己的登录，拿不到也不该拿别人家的数据。
- **全程只读。** 不下单、不改价、不回复、不删除；名字像写操作的接口一律拒绝调用。

## 安装（约 5 分钟，只需一次）

1. **装 Python 运行环境。** 推荐装 [uv](https://docs.astral.sh/uv/)：Mac 运行 `brew install uv`；Windows 在 PowerShell 里运行 `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`，然后重开终端。也可以直接用 Python 3.10 以上。
2. **装取数桥插件。** 见 [extension/README.md](extension/README.md)，约 2 分钟。插件是共用的，别的店铺数据工具装过就不用再装。Windows 必须装；Mac 可以不装，不装就直接读 Chrome 里的登录。
3. **登录。** 用 Chrome 打开 <https://sycm.taobao.com> 登录，保持登录。
4. **自检。** 运行 `scripts/sycm.sh doctor`（Windows：`scripts\sycm.cmd doctor`），看到 `probe = ok` 就装好了。
5. **交给 AI。** 把整个文件夹放进 AI 助手的 Skill 目录（Claude Code 是 `~/.claude/skills/sycm-cli`），然后直接对它说「看下昨天店铺怎么样」。

## 能让 AI 做什么

| 场景 | 它回答什么 |
|---|---|
| 标准报表 | 现在能拿到哪些数据，一张不漏地列出来 |
| 日检 | 昨天有没有要马上处理的异常 |
| 周复盘 | 这周的变化来自流量、转化还是客单价 |
| 测款 | 哪些新品值得继续推 |
| 退货归因 | 哪些款退得多、为什么退 |
| 客服质检 | 客服有没有真正回答买家的问题 |

每次分析都会写明数据日期、用的哪条命令、字段是什么口径，建议收敛到一两个能马上做的动作。分析规则在 [references/analysis-workflows.md](references/analysis-workflows.md)。

## 命令

在本文件夹里运行（Windows 把 `scripts/sycm.sh` 换成 `scripts\sycm.cmd`）。加 `--help` 看每个命令的参数，加 `--raw` 拿原始 JSON，加 `--out 文件` 写进文件。

| 场景 | 命令 |
|---|---|
| 首页大盘 | `home-overview` `home-trend` `home-table` `grow-factor` |
| 首页客单 | `order-overview` `order-trend` `order-distribution` `order-recommend` |
| 商品排行与 360 | `item-list` `item-search` `item-360` `cate-list` `spu-list` `interval-analysis` |
| 单品细看 | `item-sku-list` `item-flow-source` `item-profile` `item-detail` `item-price` `item-title` `item-bundle` `item-relate` `item-content` `item-service` `item-loss-risk` `video-list` |
| 全店监控 | `macro-monitor` `problem-alarm` |
| 新品 | `new-product-list` `new-product-overview` `new-product-trend` |
| 交易与退款 | `sale-shop-list` `sale-item-list` `refund-item-list` `refund-all-list` `refund-origin-analysis` `item-refund` |
| 客服 | `fetch-recent` `list` `detail` `reception-list` `sale-cs-list` `inquiry-loss-list` `slow-rsps-list` `evaluation-list` |
| 直播与预热 | `live-guide-overview` `live-guide-trend` `preheating-metrics` |
| 导出 Excel | `excel` `excel-tasks` |
| 工具 | `doctor` `menu` `api` `export-profile` `profiles` |

字段中文名和口径统一取自 `tb/platforms/sycm/fields.json`；字典里没有的字段原样输出字段码，不猜中文名。

### 一台电脑管多个店（仅 Mac）

```bash
scripts/sycm.sh export-profile A店      # 在 Chrome 登录 A 店后，把登录存下来
scripts/sycm.sh profiles                # 看存了哪些
scripts/sycm.sh --store A店 home-overview
```

存下来的登录在本机用户目录的 `.taobao-cli/profiles/` 里，等同于账号密码，不要拷给别人。

Windows 上读不到 Chrome 的登录，存不了档；换店就在 Chrome 里退出、换另一个店登录。

## 安全护栏

**关于风控**：作者自己的店每天都在用。只要是正常范围内的查询，基本没遇到过风控；就算碰上，淘宝也只是弹一个验证提醒，在浏览器里过一下就好。

| 护栏 | 值 |
|---|---|
| 请求间隔 | 每两次请求之间随机停 1.8～3.5 秒 |
| 请求数提醒 | 一次跑到 200 个请求时提醒一次（不停）；要硬上限可设 `SYCM_REQUEST_LIMIT` |
| 风控词 | 返回里出现「滑块 / 验证码 / 操作过于频繁 / 请重新登录 / 异常请求 / 风控」立即停 |
| 写操作 | 名字像写操作的接口一律拒绝 |

## 故障排查

| 现象 | 处理 |
|---|---|
| 提示没有登录、登录已失效（退出码 2） | 在 Chrome 里打开 sycm.taobao.com 重新登录，再运行 |
| 提示「没有连上浏览器插件」 | Chrome 要开着、插件要开着；插件每 30 秒检查一次，等一会儿再试。详见 [extension/README.md](extension/README.md) |
| 提示插件「太旧」或「文件夹不见了」 | 在 `chrome://extensions` 移除旧的取数桥，再加载本工具自带的 `extension/unpacked` |
| 提示触发风控（退出码 3） | 工具会先停下。在浏览器里正常打开生意参谋，按提示过一下验证，再运行就行 |
| 返回 0 条但确定有数据 | 检查日期；很多命令默认查昨天 |

## 更多工具

同一个作者还做了万相台、千牛、达摩盘、1688 订单统计、竞品评价洞察、广告诊断报告等店铺数据工具，都共用这一个取数插件，装一次就够。

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
