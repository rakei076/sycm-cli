"""浏览器插件桥。

为什么要有它：Windows 上的 Chrome 把 cookie 加密了，别的程序读不到；所以 Windows 上只能走插件。
所以改成：装一个只读的浏览器插件，让它在用户日常的 Chrome 里、通过已登录的平台页面去取数，再交给命令行。

通信方式：命令行临时开一个只监听 127.0.0.1 的小服务，插件来「拉任务、交结果」。
安全：
- 只监听本机；
- 只接受带插件自己 Origin（chrome-extension://<插件 ID>）的请求，普通网页伪造不了这个来源；
- 只允许平台声明的接口地址前缀（Platform.hosts）的 GET，和逐个登记的只读 POST（Platform.bridge_posts），其余一律拒绝（插件那边也各拦一遍）；
- 写操作永不走插件（BridgeSession.read_only）。
"""
from __future__ import annotations

import json
import json as _json   # BridgeSession.post 的参数名叫 json（和 curl_cffi 一致），会遮住模块名
import queue
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlsplit

from .platform import Platform

DEFAULT_PORT_RANGE = (47831, 47840)
# 一个插件服务所有平台，所以插件 ID 只在这里登记一次。DEV_EXTENSION_ID = 随交付包发的 extension/unpacked（带固定公钥）；
# 上架商店后把商店分配的 ID 加进 EXTENSION_IDS。临时加 ID：环境变量 <PREFIX>_EXTENSION_IDS（逗号分隔）。
DEV_EXTENSION_ID = "gifdenhgccikkfbodclkdbohicghfhco"
EXTENSION_IDS = frozenset({DEV_EXTENSION_ID})
# 命令行要求的最低插件版本。插件从 0.4.0 起每次连命令行都报自己的版本（/hello、/next 的 v 参数）；不报的就是更旧的。
MIN_EXTENSION_VERSION = "0.4.0"


def version_tuple(v: str | None) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in (v or "").split("."))
    except ValueError:
        return ()


def port_range(plat: Platform) -> tuple[int, int]:
    """测试时用 <PREFIX>_BRIDGE_PORT 指定专属端口，避免和日常 Chrome 里的插件抢任务。"""
    p = plat.env("BRIDGE_PORT")
    return (int(p), int(p)) if p else DEFAULT_PORT_RANGE


def allowed_prefixes(plat: Platform) -> tuple[str, ...]:
    return tuple(base.rstrip("/") + "/" for base in plat.hosts.values())


def _dbg(plat: Platform, msg: str) -> None:
    import sys, time as _t
    if plat.env("DEBUG"):
        print(f"[bridge {_t.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


class BridgeError(RuntimeError):
    no_retry = True  # 插件超时/被拒，重试只会把等待翻倍；直接报错


class BridgeTimeout(BridgeError):
    pass


class BridgeRefused(BridgeError):
    pass


def allowed_ids(plat: Platform) -> set[str]:
    only = {x.strip() for x in (plat.env("ONLY_EXTENSION_IDS") or "").split(",") if x.strip()}
    if only:   # 测试用：只认指定的插件实例（避免日常 Chrome 里装的插件抢任务）
        return only
    extra = {x.strip() for x in (plat.env("EXTENSION_IDS") or "").split(",") if x.strip()}
    return set(EXTENSION_IDS) | extra


def _dev_build() -> str | None:
    """开发时：extension/dist/BUILD 里是最新构建号；交付包里没有这个文件，就不报。"""
    from pathlib import Path
    f = Path(__file__).resolve().parents[2] / "extension" / "dist" / "BUILD"
    try:
        return f.read_text().strip() or None
    except OSError:
        return None


class _Handler(BaseHTTPRequestHandler):
    server: "BridgeServer"

    def log_message(self, *args):  # 不往终端打日志
        pass

    def _origin_ok(self) -> bool:
        """预检（OPTIONS）：Origin 必须是允许的插件。
        真正的请求（GET/POST）：Chrome 对插件发的 GET 不带 Origin，所以要求带自定义头 X-Dmp-Bridge=<插件 ID>。
        自定义头会触发预检，普通网页要带上它必须先过预检，而预检只对插件 ID 放行，所以网页伪造不了。"""
        prefix = "chrome-extension://"
        origin = self.headers.get("Origin") or ""
        ids = allowed_ids(self.server.platform)
        if origin:
            return origin.startswith(prefix) and origin[len(prefix):] in ids
        return (self.headers.get("X-Dmp-Bridge") or "") in ids

    def _send(self, code: int, body: str = "", ctype: str = "application/json; charset=utf-8") -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        origin = self.headers.get("Origin")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Private-Network", "true")
        if data:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def do_OPTIONS(self):
        if not self._origin_ok():
            return self._send(403)
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin"))
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Access-Control-Allow-Headers", "X-Dmp-Bridge, Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()

    def do_GET(self):
        if not self._origin_ok():
            return self._send(403, '{"error":"forbidden"}')
        url = urlsplit(self.path)
        version = parse_qs(url.query).get("v", [""])[0]
        if version:   # 插件报的自己的版本
            self.server.extension_version = version
        if url.path == "/hello":
            self.server.extension_seen.set()
            hello = {"app": self.server.platform.hello_app, "version": 1}
            build = _dev_build()
            if build:
                hello["extension_build"] = build
            return self._send(200, json.dumps(hello))
        if url.path == "/next":
            self.server.extension_seen.set()
            wait = min(max(float(parse_qs(url.query).get("wait", ["20"])[0]), 0.0), 25.0)
            try:
                job = self.server.jobs.get(timeout=wait)
            except queue.Empty:
                return self._send(204)
            _dbg(self.server.platform, f"插件取走任务 {(job.get('url') or job.get('cookie'))[:80]}")
            return self._send(200, json.dumps(job))
        self._send(404)

    def do_POST(self):
        if not self._origin_ok():
            return self._send(403, '{"error":"forbidden"}')
        if urlsplit(self.path).path != "/result":
            return self._send(404)
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8", "replace")
        try:
            msg = json.loads(raw)
            job_id = msg["id"]
        except (ValueError, KeyError, TypeError):
            return self._send(400)
        waiter = self.server.pending.get(job_id)
        if waiter is None:
            return self._send(404)
        _dbg(self.server.platform, f"收到插件结果 status={msg.get('status')} error={str(msg.get('error'))[:120]} 内容长度={len(msg.get('text') or '')}")
        waiter["result"] = msg
        if msg.get("browser"):
            self.server.browser = msg["browser"]
        waiter["event"].set()
        self._send(200, "{}")


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, platform: Platform):
        self.platform = platform
        self.jobs: "queue.Queue[dict]" = queue.Queue()
        self.pending: dict[str, dict] = {}
        self.extension_seen = threading.Event()
        self.browser: str | None = None   # 插件回报的浏览器信息（第一次收到结果时记录），用来告诉用户是哪个浏览器在取数
        self.extension_version: str | None = None   # 插件报的版本；旧插件不报，保持 None
        last: Exception | None = None
        lo, hi = port_range(platform)
        for port in range(lo, hi + 1):
            try:
                super().__init__(("127.0.0.1", port), _Handler)
                break
            except OSError as ex:
                last = ex
        else:
            raise BridgeError(f"本机 {lo}–{hi} 端口都被占用了：{last}")
        self.port = self.server_address[1]
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.shutdown()
        self.server_close()

    SLOW_NOTICE_AFTER = 8.0

    def submit(self, job: dict, timeout: float) -> dict:
        """派发一个任务（取数 {"url"} 或读 cookie {"cookie"}）并等结果。launch 告诉插件从哪个平台页面发。"""
        job_id = uuid.uuid4().hex
        waiter = {"event": threading.Event(), "result": None}
        self.pending[job_id] = waiter
        _dbg(self.platform, f"派发任务 {(job.get('url') or job.get('cookie'))[:80]}")
        self.jobs.put({"id": job_id, "launch": self.platform.launch_url, **job})
        try:
            first = min(self.SLOW_NOTICE_AFTER, timeout)
            if not waiter["event"].wait(first):
                import sys
                print(f"… {self.platform.display}响应比较慢，还在等浏览器返回（网络慢时一个请求可能要十几秒）", file=sys.stderr)
                if not waiter["event"].wait(max(0.0, timeout - first)):
                    raise BridgeTimeout(f"浏览器插件在 {int(timeout)} 秒内没有返回结果。请确认 Chrome 开着、网络能打开{self.platform.display}。")
            return waiter["result"]
        finally:
            self.pending.pop(job_id, None)


class BridgeSession:
    """和 curl_cffi Session 同样的 .get / .post 接口，请求交给浏览器插件去发。
    请求头由浏览器按页面自己的规矩带（Origin、Referer、cookie），命令行传来的头不转交。"""

    read_only = True   # 插件只读：Client 据此拒绝一切写操作

    def __init__(self, server: BridgeServer):
        self.server = server

    def _url(self, url: str, params: dict | None) -> str:
        if params:
            url = url + ("&" if "?" in url else "?") + urlencode(params)
        if not url.startswith(allowed_prefixes(self.server.platform)):
            raise BridgeRefused(f"插件桥只放行{self.server.platform.display}的接口地址，拒绝：{url[:80]}")
        return url

    def _reply(self, res: dict):
        if res.get("error"):
            raise BridgeError(str(res["error"]))
        return SimpleNamespace(status_code=int(res.get("status") or 0), text=res.get("text") or "")

    def get(self, url: str, params: dict | None = None, timeout: float | None = None, headers: dict | None = None):
        return self._reply(self.server.submit({"url": self._url(url, params)}, timeout or 60))

    def post(self, url: str, params: dict | None = None, json: object = None, timeout: float | None = None,
             headers: dict | None = None):
        """只放行平台登记的只读 POST 接口（精确路径）。body 按 JSON 发。"""
        url = self._url(url, params)
        plat = self.server.platform
        if urlsplit(url).path not in plat.bridge_posts:
            raise BridgeRefused(f"插件桥只放行{plat.display}登记过的只读查询接口，拒绝：{urlsplit(url).path}")
        body = _json.dumps(json if json is not None else {}, ensure_ascii=False, separators=(",", ":"))
        return self._reply(self.server.submit({"url": url, "method": "POST", "body": body}, timeout or 60))

    def cookie(self, name: str) -> str | None:
        """让浏览器读一个 cookie（只放行平台声明的名字，如 mtop 令牌）；没有返回 None。"""
        if name not in self.server.platform.readable_cookies:
            raise BridgeRefused(f"插件桥不读这个 cookie：{name}")
        res = self.server.submit({"cookie": name}, 30)
        if res.get("error"):
            raise BridgeError(str(res["error"]))
        return res.get("value") or None
