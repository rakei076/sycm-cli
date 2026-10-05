"""统一连接器：所有请求都从这里走。

- 默认只发 GET；平台声明 allow_post 才能发 POST。路径名字像写操作的直接拦掉；写操作只认 write_allow 里精确登记的接口。
- 每个请求自动带平台的公共参数（如达摩盘的 csrfId）；登录准备动作一次运行只做一次。
- 四道检查：登录失效（403 / 空 / 非 JSON）、风控词、平台业务报错（Platform.check_payload）、该有数据却是空列表。
- 请求之间随机间隔；单次运行请求数上限（平台声明）。
"""
from __future__ import annotations

import json
import random
import time
from typing import Any

from .errors import ApiFailed, EmptyResult, LoginExpired, RetryRequest, RiskStopped, TbError, WriteBlocked
from .platform import Platform

TIMEOUT = 60
RETRIES = 2

__all__ = ["Client", "TbError", "LoginExpired", "ApiFailed", "EmptyResult", "RiskStopped", "WriteBlocked"]


def _dig(data: Any, path: str) -> Any:
    for part in path.split("."):
        if isinstance(data, dict):
            data = data.get(part)
        elif isinstance(data, list) and part.isdigit() and int(part) < len(data):
            data = data[int(part)]
        else:
            return None
    return data


class Client:
    def __init__(self, platform: Platform, cookies: dict[str, str] | None = None, session: Any = None,
                 delay: tuple[float, float] | None = None):
        if cookies is None:
            from .auth import load_cookies
            cookies = load_cookies(platform)
        if session is None:
            from curl_cffi import requests
            session = requests.Session(impersonate="chrome")
            for k, v in cookies.items():
                session.cookies.set(k, v, domain=platform.session_cookie_domain)
        self.platform = platform
        self.cookies = cookies
        self.session = session
        self.delay = delay if delay is not None else platform.delay
        self.login_retry_wait = 5.0
        self.state: dict[str, Any] = {}   # 平台钩子的存放处（如 csrfId）
        self._who: dict | None = None
        self._last = 0.0
        self.request_count = 0

    @property
    def login_hint(self) -> str:
        return f"请在浏览器里打开 {self.platform.login_page} 确认已登录（必要时刷新页面或重新登录），然后重试。"

    # ---- cookie ----
    def cookie(self, name: str) -> str | None:
        """读一个登录 cookie：插件模式向浏览器要（每次现读，令牌换发后立刻看到新值），否则读本地副本。"""
        reader = getattr(self.session, "cookie", None)
        if reader is not None:
            return reader(name)
        return self.cookies.get(name)

    def set_cookie(self, name: str, value: str) -> None:
        self.cookies[name] = value
        jar = getattr(self.session, "cookies", None)
        if jar is not None and hasattr(jar, "set"):
            jar.set(name, value, domain=self.platform.session_cookie_domain)

    # ---- 底层 ----
    def _guard(self) -> None:
        p = self.platform
        limit = p.env("REQUEST_LIMIT")
        if limit and limit.isdigit() and self.request_count >= int(limit):
            raise TbError(f"达到自定义硬上限 {p.env_prefix}_REQUEST_LIMIT={limit}，停止。", stage="安全护栏",
                          hint=f"如要继续：unset {p.env_prefix}_REQUEST_LIMIT 或调大它。")
        if p.warn_after is not None and self.request_count == p.warn_after and not self.state.get("warned"):
            self.state["warned"] = True
            import sys
            print(f"⚠️  已发出 {p.warn_after} 次请求 — 大批量正常，但建议留意：风控通常按“短时高频”判断而不是“总量”，"
                  "请求之间的间隔已经足够。继续运行。", file=sys.stderr)
        if p.max_requests is not None and self.request_count >= p.max_requests:
            raise TbError(f"单次运行已达 {p.max_requests} 次请求上限，自动停止。", stage="安全护栏",
                          hint="分几次运行，或缩小范围。")

    def send(self, url: str, params: dict[str, Any], label: str, headers: dict[str, str] | None = None, *,
             body: Any = None, method: str = "GET", retries: int = RETRIES) -> Any:
        """发一次请求并做四道检查（平台钩子也用它）。method="POST" 时 body 按 JSON 发；写操作传 retries=0，绝不自动重发。"""
        p = self.platform
        self._guard()
        if self.request_count and self.delay[1] > 0:
            wait = random.uniform(*self.delay) - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                merged = {"Referer": p.referer, "Accept": "application/json, text/plain, */*", **(headers or {})}
                if method == "POST":
                    resp = self.session.post(url, params=params, json=body if body is not None else {}, timeout=TIMEOUT,
                                             headers={"Content-Type": "application/json", **merged})
                else:
                    resp = self.session.get(url, params=params, timeout=TIMEOUT, headers=merged)
            except Exception as exc:  # 网络错误重试
                if getattr(exc, "no_retry", False):  # 浏览器插件超时/被拒：重试没意义
                    raise TbError(str(exc), endpoint=label, stage="浏览器插件",
                                  hint=f"确认 Chrome 开着且插件已启用；{p.display}响应慢时可以再试一次。") from None
                last_exc = exc
                time.sleep(1 + attempt)
                continue
            if resp.status_code >= 500 and attempt < retries:
                time.sleep(1 + attempt)
                continue
            break
        else:
            raise TbError(f"网络请求失败：{last_exc}", endpoint=label, stage="发送请求", hint="检查网络后重试。")
        self.request_count += 1
        self._last = time.time()

        if resp.status_code == 403:
            raise LoginExpired("登录已失效（HTTP 403）。", endpoint=label, stage="登录检查", hint=self.login_hint)
        text = resp.text or ""
        if not text.strip():
            raise LoginExpired("平台返回了空内容，通常是没登录或登录已过期。", endpoint=label, stage="登录检查", hint=self.login_hint)
        try:
            payload = json.loads(text)
        except ValueError:
            raise LoginExpired("平台返回的不是数据而是网页，通常是登录或 csrf 失效。", endpoint=label,
                               stage="登录检查", hint=self.login_hint) from None
        if resp.status_code >= 400:
            raise ApiFailed(f"HTTP {resp.status_code}", endpoint=label, stage="发送请求")
        decoded = json.dumps(payload, ensure_ascii=False)
        for w in p.risk_words:
            if w in decoded and not any(x in decoded for x in p.risk_exempt):
                raise RiskStopped(f"平台返回内容里出现「{w}」，已立即停止，避免触发风控。", endpoint=label,
                                  stage="风控检查", hint=f"先在浏览器里正常打开{p.display}完成验证，过一段时间再运行。")
        if p.check_payload:
            p.check_payload(self, payload, resp, label)
        return payload

    # ---- 对外 ----
    def whoami(self) -> dict:
        """登录后的准备动作（平台没有就什么都不做）。刚登录完的头几秒平台会话可能还没生效，失败时等几秒重试一次。"""
        if self._who is None:
            prepare = self.platform.prepare
            if prepare is None:
                self._who = {}
            else:
                try:
                    self._who = prepare(self)
                except (ApiFailed, LoginExpired):
                    time.sleep(self.login_retry_wait)
                    self._who = prepare(self)
        return self._who

    def _build(self, host: str, path: str, params: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, str]]:
        """平台的 build_request 可以只接管一部分 host（返回 None 表示走默认做法）。"""
        p = self.platform
        built = p.build_request(self, host, path, params) if p.build_request else None
        if built is not None:
            return built
        q = dict(p.common_params(self)) if p.common_params else {}
        q.update(params)
        return p.hosts[host] + path, q, {}

    def post(self, host: str, path: str, body: Any = None, params: dict[str, Any] | None = None, *,
             name: str = "", raw: bool = False, headers: dict[str, str] | None = None, write: bool = False) -> Any:
        """发 POST（平台要声明 allow_post）。读取类 POST 名字像写操作的一律拒绝；
        写操作只有 write=True 且路径在 Platform.write_allow 里才放行，不自动重试，并且永不走浏览器插件（插件只读）。"""
        p = self.platform
        if not p.allow_post:
            raise TbError(f"{p.display}没有开放 POST。", stage="只读检查")
        if host not in p.hosts:
            raise TbError(f"未知的 host：{host}（只能是 {' 或 '.join(p.hosts)}）")
        if not path.startswith("/"):
            path = "/" + path
        bare = path.split("?")[0]
        label = name or f"{host} {bare}"
        if write:
            if bare not in p.write_allow:
                raise WriteBlocked("这个写接口不在允许清单里，已拒绝。", endpoint=label, stage="只读检查")
            if getattr(self.session, "read_only", False):
                raise WriteBlocked("现在是通过浏览器插件取数，插件只读，不能执行这个操作。", endpoint=label, stage="只读检查",
                                   hint=f"请在{p.display}网页里手动操作；或设置 {p.env_prefix}_MODE=cookies 改为直接读 Chrome 的 cookie 后重试（仅 Mac）。")
        elif p.write_re.search(bare):
            raise WriteBlocked("这个接口看起来是写操作，读取通道已拒绝调用。", endpoint=label, stage="只读检查")
        self.whoami()
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        url, q, built_headers = self._build(host, path, clean)
        payload = self.send(url, q, label, {**built_headers, **(headers or {})}, body=body, method="POST",
                            retries=0 if write else RETRIES)
        return payload if raw else (payload.get("data", payload) if isinstance(payload, dict) else payload)

    def get(self, host: str, path: str, params: dict[str, Any] | None = None, *,
            list_path: str | None = None, name: str = "", raw: bool = False,
            headers: dict[str, str] | None = None) -> Any:
        hosts = self.platform.hosts
        if host not in hosts:
            raise TbError(f"未知的 host：{host}（只能是 {' 或 '.join(hosts)}）")
        if not path.startswith("/"):
            path = "/" + path
        label = name or f"{host} {path}"
        if self.platform.write_re.search(path):
            raise WriteBlocked("这个接口看起来是写操作，本工具只读，已拒绝调用。", endpoint=label, stage="只读检查")
        self.whoami()
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        for attempt in range(2):
            url, q, built_headers = self._build(host, path, clean)
            try:
                payload = self.send(url, q, label, {**built_headers, **(headers or {})})
            except RetryRequest:   # 平台钩子已修好状态（如换了令牌），重新构造请求再发一次
                if attempt:
                    raise TbError("重发后平台仍要求重发，已停止。", endpoint=label, stage="重试")
                continue
            break
        data = payload.get("data", payload) if isinstance(payload, dict) else payload
        if list_path:
            target = _dig(data, list_path)
            if target is None or (isinstance(target, (list, dict)) and len(target) == 0):
                raise EmptyResult("平台返回成功，但该有的数据是空的。", endpoint=label, stage="数据检查",
                                  hint="日期超出了数据范围，或参数不对；可以先运行 doctor 看最新数据日期。")
        return payload if raw else data
