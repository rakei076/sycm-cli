"""平台描述：底座（tb.core）只认这个对象，各平台的差异全部写在这里。"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class Platform:
    name: str                        # "dmp"
    display: str                     # "达摩盘"
    hosts: dict[str, str]            # 名字 -> 基础地址，如 {"main": "https://dmp.taobao.com/api_2"}
    login_page: str
    launch_url: str                  # 插件取数用的「发射台」页面：平台域名下极轻的同域小文档（如 robots.txt）
    login_cookies: tuple[str, ...]   # 必须全部存在才算已登录
    cookie_domains: tuple[str, ...]  # 同名 cookie 由后面的域覆盖前面的
    referer: str
    expired_hints: tuple[str, ...]   # 平台业务报错里表示「登录过期」的关键词
    write_re: re.Pattern             # 路径像写操作就拒绝
    env_prefix: str                  # "DMP"
    session_cookie_domain: str = ".taobao.com"
    allow_post: bool = False                            # 是否允许 client.post
    bridge_posts: tuple[str, ...] = ()                  # 走插件时允许的只读 POST 接口（精确路径）；插件 SITES 里的 POSTS 必须一样
    write_allow: tuple[str, ...] = ()                   # 唯一允许的写接口（精确路径）；只有 client.post(write=True) 能调，且不自动重试
    risk_words: tuple[str, ...] = ("滑块", "验证码", "操作过于频繁", "请重新登录", "异常请求")
    risk_exempt: tuple[str, ...] = ()                   # 响应里出现这些词就不按风控词判断（如「618」活动文案里带「风控」）
    delay: tuple[float, float] = (0.8, 1.6)             # 请求之间的随机间隔（秒）
    max_requests: int | None = None                     # 单次运行请求数上限（硬停）
    warn_after: int | None = None                       # 请求数到这个数时在终端提醒一次（不停）；<PREFIX>_REQUEST_LIMIT=数字 可另加硬上限
    readable_cookies: tuple[str, ...] = ()              # 允许经插件桥读取的浏览器 cookie 名（如 mtop 令牌）
    prepare: Callable[[Any], dict] | None = None        # 登录后的准备动作（如取 csrfId），返回登录用户信息
    common_params: Callable[[Any], dict] | None = None  # 每个请求都要带的公共参数
    # 自定义请求构造：(client, host, path, params) -> (url, query, extra_headers)；默认 = hosts[host]+path，公共参数 + params
    build_request: Callable[[Any, str, str, dict], tuple[str, dict, dict]] | None = None
    # 业务层检查：(client, payload, resp, label)，失败时抛 tb.core.errors 里的错误；要重发时抛 RetryRequest
    check_payload: Callable[[Any, Any, Any, str], None] | None = None

    def env(self, name: str, default: str | None = None) -> str | None:
        return os.environ.get(f"{self.env_prefix}_{name}", default)

    @property
    def hello_app(self) -> str:
        return f"{self.name}-cli"

    def state_dir(self) -> Path:
        """状态目录（如 1688 的本地订单库）。优先级：<PREFIX>_STATE_DIR > TB_STATE_ROOT/<name> > 默认。"""
        override = self.env("STATE_DIR")
        if override:
            return Path(override).expanduser()
        root = os.environ.get("TB_STATE_ROOT")
        if root:
            return Path(root).expanduser() / self.name
        if os.name == "nt":
            base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Local")
            return Path(base) / f"{self.name}-cli"
        return Path.home() / f".{self.name}-cli"
