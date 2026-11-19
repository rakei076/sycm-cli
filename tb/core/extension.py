"""本机装没装取数桥插件：不用等插件来连，直接读浏览器资料里的扩展登记。

Chrome / Edge 每个资料目录下的 Secure Preferences（旧版本在 Preferences）里有 extensions.settings，
按插件 ID 记着：从哪个文件夹加载（path）、有没有被停用（disable_reasons）。顺着文件夹读 manifest.json 就有版本号。
只读这几项，不碰别的设置。读不到（权限、格式变了）就当没找到，由连接时的握手兜底。
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .bridge import EXTENSION_IDS, MIN_EXTENSION_VERSION, version_tuple


@dataclass(frozen=True)
class Installed:
    browser: str            # "Chrome" / "Edge"
    profile: str            # 资料目录名，如 "Default"、"Profile 1"
    path: str | None        # 插件从哪个文件夹加载
    enabled: bool
    version: str | None     # 读不到 manifest（文件夹被删/移走）时为 None

    @property
    def usable(self) -> bool:
        return self.enabled and version_tuple(self.version) >= version_tuple(MIN_EXTENSION_VERSION)


def _roots() -> list[tuple[str, Path]]:
    home = Path.home()
    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
        return [("Chrome", local / "Google" / "Chrome" / "User Data"), ("Edge", local / "Microsoft" / "Edge" / "User Data")]
    if sys.platform == "darwin":
        sup = home / "Library" / "Application Support"
        return [("Chrome", sup / "Google" / "Chrome"), ("Edge", sup / "Microsoft Edge")]
    return [("Chrome", home / ".config" / "google-chrome"), ("Edge", home / ".config" / "microsoft-edge")]


def _manifest_version(folder: Path) -> str | None:
    try:
        return json.loads((folder / "manifest.json").read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError):
        return None


def find_installed(ids: frozenset[str] = EXTENSION_IDS, roots: list[tuple[str, Path]] | None = None) -> list[Installed]:
    found: dict[tuple[str, str, str], Installed] = {}
    for browser, root in roots if roots is not None else _roots():
        if not root.is_dir():
            continue
        for prefs in sorted(root.glob("*/Secure Preferences")) + sorted(root.glob("*/Preferences")):
            try:
                settings = json.loads(prefs.read_text(encoding="utf-8")).get("extensions", {}).get("settings", {})
            except (OSError, ValueError, AttributeError):
                continue
            for ext_id in ids:
                entry = settings.get(ext_id) if isinstance(settings, dict) else None
                key = (browser, prefs.parent.name, ext_id)
                if not isinstance(entry, dict) or key in found:
                    continue
                raw = entry.get("path")
                folder = None
                if raw:   # 手动加载的是绝对路径；商店安装的是「ID/版本」，在资料目录的 Extensions 下
                    folder = Path(raw) if Path(raw).is_absolute() else prefs.parent / "Extensions" / raw
                enabled = not entry.get("disable_reasons") and entry.get("state", 1) != 0
                found[key] = Installed(browser, prefs.parent.name, str(folder) if folder else None, enabled,
                                       _manifest_version(folder) if folder else None)
    return list(found.values())


def status(found: list[Installed]) -> tuple[bool, str]:
    """(能不能直接用, 给用户看的一句话)。能用就不提示安装。"""
    if any(x.usable for x in found):
        x = next(x for x in found if x.usable)
        return True, f"已装取数桥插件 {x.version}（{x.browser} · {x.profile}），不用再装。"
    if not found:
        return False, "这台电脑的 Chrome / Edge 里还没装取数桥插件。安装方法见 extension/README.md（约 2 分钟，装一次所有工具共用）。"
    x = found[0]
    where = f"{x.browser} · {x.profile}"
    if x.path and x.version is None:
        return False, (f"取数桥插件（{where}）当初加载的文件夹不见了：{x.path}。"
                       "在 chrome://extensions 移除它，再加载本工具自带的 extension/unpacked。")
    if not x.enabled:
        return False, f"取数桥插件（{where}）被停用了：在 chrome://extensions 里把它的开关打开。"
    return False, (f"取数桥插件（{where}）版本是 {x.version or '旧版'}，需要 {MIN_EXTENSION_VERSION} 以上："
                   "在 chrome://extensions 移除旧的，再加载本工具自带的 extension/unpacked。")
