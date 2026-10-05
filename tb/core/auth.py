"""读取淘宝登录态（淘宝系各后台共用阿里通用登录）。

- macOS / Linux：browser_cookie3 直接读 Chrome 里的 cookie。
- Windows：读不到（新版 Chrome 把 cookie 的钥匙锁在浏览器里），只能走浏览器插件（见 transport.py）。
不导出 cookie，不改浏览器设置。
"""
from __future__ import annotations

import platform
from pathlib import Path

import browser_cookie3

from .platform import Platform


class NotLoggedIn(RuntimeError):
    pass


def _has_login(plat: Platform, cookies: dict[str, str]) -> bool:
    """真正登录 = 平台要求的登录 cookie 全部存在（淘宝系：cookie2 和 unb）。
    cookie2 是「会话级」的，浏览器一关就丢；淘宝给访客（停在登录页）也会发一个 cookie2，所以只有它不算登录。
    unb（用户 ID）是持久的，浏览器重启后还在，但没有本次会话的 cookie2 也不算登录。"""
    return all(name in cookies for name in plat.login_cookies)


def _merge(plat: Platform, items: list[tuple[str, str, str]]) -> dict[str, str]:
    """items: (domain, name, value)。按域优先级合并：同名 cookie 由后面的域覆盖前面的。"""
    cookies: dict[str, str] = {}
    for tier in plat.cookie_domains:
        for domain, name, value in items:
            if tier in domain:
                cookies[name] = value
    return cookies


def _chrome_cookie_file(plat: Platform) -> str | None:
    prof = plat.env("CHROME_PROFILE")
    if not prof:
        return None
    return str(Path.home() / "Library/Application Support/Google/Chrome" / prof / "Cookies")


def _not_logged_in(plat: Platform) -> NotLoggedIn:
    return NotLoggedIn(
        f"未找到{plat.display}的登录。请在 Chrome 里打开并登录 {plat.login_page} 后重试。"
        f'若登录的是别的 Chrome 资料，设置环境变量 {plat.env_prefix}_CHROME_PROFILE="Profile 1" 后重试。'
    )


def load_cookies(plat: Platform) -> dict[str, str]:
    if platform.system() == "Windows":
        raise NotLoggedIn(f"Windows 上读不到 Chrome 的登录信息，只能通过浏览器插件取{plat.display}的数据。"
                          "请按 extension/README.md 安装取数桥插件。")
    try:
        jar = browser_cookie3.chrome(cookie_file=_chrome_cookie_file(plat))
    except browser_cookie3.BrowserCookieError:
        raise _not_logged_in(plat) from None
    cookies = _merge(plat, [(c.domain or "", c.name, c.value) for c in jar])
    if not _has_login(plat, cookies):
        raise _not_logged_in(plat)
    return cookies
