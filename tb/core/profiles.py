"""多店铺登录态：把一份淘宝登录 cookie 存成命名 profile（0600，仅本机），之后用 --store 复用。
淘宝系各平台共用同一个目录（登录态是通用的），一份 profile 各平台都能用。
profile 只用于「命令行读 cookie」的取数方式；插件模式用的是浏览器里当前登录的那个店。"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from .platform import Platform

PROFILE_DIR = Path(os.environ.get("TAOBAO_CLI_PROFILE_DIR", str(Path.home() / ".taobao-cli" / "profiles")))


def _profile_path(name: str) -> Path:
    if not name or any(sep in name for sep in ("/", "\\", "..")) or name.startswith("."):
        raise ValueError(f"store 名只能是简单名字，不含路径分隔符：{name!r}")
    return PROFILE_DIR / f"{name}.json"


def save_profile(name: str, cookies: dict[str, str]) -> Path:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(PROFILE_DIR, 0o700)
    except OSError:
        pass
    path = _profile_path(name)
    payload = {"store": name, "domain": "taobao.com", "saved_at": datetime.now().isoformat(timespec="seconds"),
               "cookies": cookies}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def load_profile(plat: Platform, name: str) -> dict[str, str]:
    path = _profile_path(name)
    if not path.exists():
        raise RuntimeError(f"登录态 profile 不存在：{name}\n"
                           f"先在 Chrome 登录该店，再跑：tb {plat.name} export-profile {name}")
    cookies = json.loads(path.read_text(encoding="utf-8")).get("cookies") or {}
    missing = [c for c in plat.login_cookies if c not in cookies]
    if missing:
        raise RuntimeError(f"profile {name} 缺 {'、'.join(missing)}（保存时可能未登录），请重新 export-profile。")
    return cookies


def list_profiles() -> list[dict[str, Any]]:
    if not PROFILE_DIR.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(PROFILE_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({"store": p.stem, "saved_at": data.get("saved_at"), "cookies": data.get("cookies") or {}})
    return out
